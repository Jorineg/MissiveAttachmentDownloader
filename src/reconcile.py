"""One-time reconciliation: match existing manually-downloaded attachments to DB records.

Scans IBH-INBOX directories for files matching pending attachments by filename + size.
Matched → mark completed. Skippable → mark skipped. Unmatched → mark skipped (no local match).

Usage: python -m src.reconcile [--dry-run]
"""
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

from src import settings
from src.logging_conf import logger
from src.db import Database
from src.app import Application


def build_file_index(storage_paths: list[Path]) -> dict[tuple[str, int], list[str]]:
    """Build index of (lowercase_filename, size) → [relative_paths] from all IBH-INBOX dirs."""
    index: dict[tuple[str, int], list[str]] = defaultdict(list)
    
    for base_path in storage_paths:
        if not base_path.exists():
            logger.warning(f"Storage path does not exist: {base_path}")
            continue
        
        for project_dir in base_path.iterdir():
            if not project_dir.is_dir() or project_dir.name.startswith(('@', '.')):
                continue
            inbox = project_dir / "IBH-INBOX"
            if not inbox.exists():
                continue
            
            for file_path in inbox.rglob("*"):
                if not file_path.is_file() or file_path.name.startswith(('@', '.')):
                    continue
                try:
                    size = file_path.stat().st_size
                    key = (file_path.name.lower(), size)
                    rel = str(file_path.relative_to(base_path))
                    index[key].append(rel)
                except OSError:
                    continue
    
    return index


def reconcile(dry_run: bool = False):
    settings.validate_config()
    
    db = Database()
    app = Application()
    
    logger.info("=" * 60)
    logger.info("Attachment Reconciliation")
    logger.info(f"Storage paths: {[str(p) for p in settings.ATTACHMENT_STORAGE_PATHS]}")
    logger.info(f"Dry run: {dry_run}")
    logger.info("=" * 60)
    
    # Phase 1: Build file index from disk
    logger.info("Building file index from IBH-INBOX directories...")
    file_index = build_file_index(settings.ATTACHMENT_STORAGE_PATHS)
    logger.info(f"Indexed {sum(len(v) for v in file_index.values())} files ({len(file_index)} unique name+size combos)")
    
    # Phase 2: Fetch all pending project-linked attachments
    logger.info("Fetching pending project-linked attachments...")
    attachments = db.get_pending_attachments(limit=50000)
    logger.info(f"Found {len(attachments)} pending project-linked attachments")
    
    if not attachments:
        logger.info("Nothing to reconcile")
        return
    
    # Phase 3: Process each attachment
    stats = {"skipped_filter": 0, "matched": 0, "unmatched": 0, "errors": 0}
    
    for i, att in enumerate(attachments, 1):
        att_id = str(att["missive_attachment_id"])
        filename = att["original_filename"]
        file_size = att.get("file_size")
        project_name = att.get("project_name", "?")
        
        # Apply same skip filters as MAD
        skip_reason = app._should_skip(att)
        if skip_reason:
            stats["skipped_filter"] += 1
            if not dry_run:
                db.mark_skipped(att_id, skip_reason)
            if i <= 20 or i % 500 == 0:
                logger.info(f"[{i}] SKIP: {filename} ({skip_reason})")
            continue
        
        # Match by filename + size, only within the correct project folder
        matched_path = None
        if file_size:
            key = (filename.lower(), file_size)
            candidates = file_index.get(key, [])
            # Only accept matches in the same project
            project_prefix = project_name.lower()
            project_matches = [c for c in candidates if c.lower().startswith(project_prefix)]
            if project_matches:
                matched_path = project_matches[0]
        
        if matched_path:
            stats["matched"] += 1
            if not dry_run:
                db.mark_completed(att_id, matched_path)
            if i <= 20 or i % 200 == 0:
                logger.info(f"[{i}] MATCH: {filename} → {matched_path}")
        else:
            stats["unmatched"] += 1
            if not dry_run:
                db.mark_skipped(att_id, "reconciliation: no local match found")
            if i <= 20 or i % 200 == 0:
                logger.info(f"[{i}] NO MATCH: {filename} (project: {project_name})")
    
    # Summary
    logger.info("=" * 60)
    logger.info("Reconciliation complete")
    logger.info(f"  Skipped (filters): {stats['skipped_filter']}")
    logger.info(f"  Matched on disk:   {stats['matched']}")
    logger.info(f"  No match (skipped):{stats['unmatched']}")
    prefix = "[DRY RUN] " if dry_run else ""
    logger.info(f"{prefix}Total processed: {sum(stats.values())}")
    logger.info("=" * 60)
    
    db.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    try:
        reconcile(dry_run=dry_run)
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

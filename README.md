# Missive Attachment Downloader

A Docker-based worker that downloads email attachments from Missive to NAS storage.

## Architecture

This service is **part of a pipeline**:

1. **TeamworkMissiveConnector** syncs Missive data → inserts into `missive.attachments` → queues downloads in `email_attachment_files`
2. **MissiveAttachmentDownloader** (this service) watches the queue → downloads files to NAS
3. **FileMetadataSync** scans NAS → matches files to attachments via `local_filename`

## Features

- **Supabase REST API** - No direct DB connection needed
- **Atomic claims** - Multiple workers can run without conflicts
- **Monthly folders** - Files organized as `YYYY-MM/filename`
- **Unique filenames** - Format: `{original_name}_{attachment_id}.{ext}`
- **Retry logic** - Failed downloads automatically retry
- **Docker-ready** - Designed for NAS deployment

## Quick Start (Docker)

```bash
# Create .env from example
cp env.example .env
# Edit .env with your Supabase credentials and paths

# Run
docker-compose up -d
```

## Configuration

Create a `.env` file:

```env
# Required
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key
HOST_ATTACHMENT_PATH=/volume1/email_attachments

# Optional
POLL_INTERVAL=5          # Seconds between DB polls
BATCH_SIZE=10            # Attachments per batch
MAX_RETRIES=3            # Retry attempts before marking failed
LOG_LEVEL=INFO
BETTERSTACK_SOURCE_TOKEN=  # Optional cloud logging
```

## Filename Format

Files are saved with unique names that include the Missive attachment ID:

```
Invoice-December_0001f0d0-0c46-4036-84c7-c493a226a993.pdf
```

This enables FileMetadataSync to match files to attachments by querying:
```sql
SELECT * FROM email_attachment_files WHERE local_filename = 'Invoice-December_0001f0d0-...'
```

## Folder Structure

```
/volume1/email_attachments/
├── 2024-12/
│   ├── Invoice_abc123.pdf
│   └── Report_def456.xlsx
├── 2025-01/
│   └── Contract_ghi789.docx
```

## Database Tables

### `email_attachment_files` (public schema)

| Column | Description |
|--------|-------------|
| `missive_attachment_id` | Primary key (UUID) |
| `missive_message_id` | For linking to email |
| `original_filename` | Original name from Missive |
| `original_url` | Download URL |
| `status` | pending/downloading/completed/failed |
| `local_filename` | Unique filename after download |
| `downloaded_at` | Timestamp |

### Status Flow

```
pending → downloading → completed
              ↓
           failed (after MAX_RETRIES)
```

## Local Development

```bash
# Create venv
python3 -m venv venv
source venv/bin/activate

# Install deps
pip install -r requirements.txt

# Run
python -m src.app
```

## Monitoring

### Check pending downloads
```sql
SELECT COUNT(*) FROM email_attachment_files WHERE status = 'pending';
```

### Check failed downloads
```sql
SELECT * FROM email_attachment_files WHERE status = 'failed';
```

### View logs
```bash
docker-compose logs -f
```

## Troubleshooting

### Downloads stuck in "downloading"
The service auto-resets stuck downloads on startup. Manually:
```sql
UPDATE email_attachment_files 
SET status = 'pending', updated_at = NOW()
WHERE status = 'downloading' AND updated_at < NOW() - INTERVAL '30 minutes';
```

### Reset failed downloads
```sql
UPDATE email_attachment_files 
SET status = 'pending', retry_count = 0, error_message = NULL
WHERE status = 'failed';
```

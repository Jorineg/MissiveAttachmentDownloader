# Missive Attachment Downloader

A lightweight, polling-based service that automatically downloads email attachments from Missive and saves them to local storage with organized filenames.

## Features

- **Polling-based sync** - No webhooks required, perfect for NAS deployments
- **Automatic attachment downloads** - Fetches all attachments from Missive conversations
- **Organized filenames** - Format: `FROM_sender_at_domain.tld_TO_recipient_at_domain.tld_NAME_filename.ext`
- **Persistent queue** - Spool-based queue ensures no attachments are lost
- **Checkpoint-based sync** - Efficient incremental fetching with overlap protection
- **Betterstack integration** - Optional cloud logging support
- **Configurable date filtering** - Start syncing from a specific date

## Quick Start

### 1. Requirements

- Python 3.8 or higher
- Missive API token

### 2. Installation

```bash
# Clone or copy the project
cd MissiveAttachmentDownloader

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

Create a `.env` file with your configuration:

```env
# Required
MISSIVE_API_TOKEN=your_missive_api_token_here
ATTACHMENT_STORAGE_PATH=/absolute/path/to/attachments

# Optional
BETTERSTACK_SOURCE_TOKEN=your_betterstack_token
MISSIVE_PROCESS_AFTER=01.01.2020
POLLING_INTERVAL=60
```

**Important:** `ATTACHMENT_STORAGE_PATH` must be an absolute path.

### 4. Run

```bash
python -m src.app
```

The application will:
- ✅ Validate configuration
- ✅ Create storage directory
- ✅ Start polling for new conversations
- ✅ Download attachments automatically
- ✅ Save with organized filenames

## Configuration Reference

### Required Variables

| Variable | Description |
|----------|-------------|
| `MISSIVE_API_TOKEN` | Your Missive API token (get from Missive settings) |
| `ATTACHMENT_STORAGE_PATH` | Absolute path where attachments will be saved |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BETTERSTACK_SOURCE_TOKEN` | - | Betterstack source token for cloud logging |
| `MISSIVE_PROCESS_AFTER` | 30 days ago | Only process emails from this date onwards (format: DD.MM.YYYY) |
| `POLLING_INTERVAL` | 60 | How often to check for new conversations (seconds) |
| `TIMEZONE` | Europe/Berlin | Timezone for logging timestamps |
| `LOG_LEVEL` | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `BACKFILL_OVERLAP_SECONDS` | 120 | Time overlap to prevent missing conversations |
| `SPOOL_RETRY_SECONDS` | 60 | Wait time before retrying failed items |

## Filename Format

Attachments are saved with descriptive filenames based on sender, recipient, and original filename:

```
FROM_user_at_example.com_TO_recipient_at_company.com_NAME_invoice.pdf
```

Format breakdown:
- `FROM_` prefix followed by sender email address
- `TO_` prefix followed by recipient email address
- `NAME_` prefix followed by original attachment filename
- Email addresses use `_at_` instead of `@` for filesystem safety

## How It Works

1. **Polling**: Every 60 seconds (configurable), the app checks Missive for updated conversations
2. **Filtering**: Only conversations with attachments are queued for processing
3. **Queue**: Conversation IDs are added to a persistent spool queue
4. **Processing**: Worker thread processes queued conversations
5. **Download**: Attachments are downloaded and saved with organized names
6. **Checkpoint**: Progress is saved to prevent re-processing

## Project Structure

```
MissiveAttachmentDownloader/
├── src/
│   ├── app.py                    # Main application
│   ├── poller.py                 # Polls Missive API
│   ├── worker.py                 # Processes queue
│   ├── missive_client.py         # Missive API client
│   ├── attachment_processor.py   # Downloads & names attachments
│   ├── checkpoint.py             # Checkpoint management
│   ├── settings.py               # Configuration
│   ├── logging_conf.py           # Logging setup
│   └── queue/
│       ├── models.py             # Queue data models
│       └── spool_queue.py        # Spool directory queue
├── data/                         # Queue & checkpoints (created at runtime)
├── logs/                         # Application logs
├── requirements.txt
└── README.md
```

## Monitoring

### Logs

Application logs are written to:
- Console (stdout)
- `logs/app.log` file
- Betterstack (if configured)

### Check Queue Status

```bash
# Count queued items
ls -l data/queue/spool/missive/*.evt | wc -l

# Check retry queue
ls -l data/queue/spool/missive/*.retry | wc -l
```

### Checkpoint

Current sync progress is saved in `data/checkpoints/missive.json`

## Deployment on NAS

This application is designed to run on a NAS:

1. Install Python on your NAS (if not already available)
2. Copy the application to your NAS
3. Create a `.env` file with your configuration
4. Set `ATTACHMENT_STORAGE_PATH` to a path on your NAS storage
5. Run the application:

```bash
python -m src.app
```

### Running as a Service

You can create a systemd service (Linux NAS) or use your NAS's task scheduler:

**Systemd example:**

```ini
[Unit]
Description=Missive Attachment Downloader
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/MissiveAttachmentDownloader
ExecStart=/path/to/venv/bin/python -m src.app
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

## Reliability Features

- **Persistent queue**: Survives application restarts
- **Retry logic**: Failed downloads are automatically retried
- **Checkpoint overlap**: Prevents missing conversations during sync
- **Duplicate prevention**: Skips already-downloaded attachments
- **Idempotent operations**: Safe to re-run and restart

## Troubleshooting

### Configuration Errors

Run the configuration validator:

```bash
python -m src.settings
```

### Missing Attachments

- Check `logs/app.log` for errors
- Verify `MISSIVE_API_TOKEN` is valid
- Check `ATTACHMENT_STORAGE_PATH` permissions

### High API Usage

- Increase `POLLING_INTERVAL` to reduce API calls
- Set `MISSIVE_PROCESS_AFTER` to avoid processing old emails

## License

MIT

## Support

For issues and questions, check the application logs first. Enable debug logging with `LOG_LEVEL=DEBUG` for detailed information.



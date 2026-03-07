# GPU Monitor

Lightweight NVIDIA GPU monitor with Slack alerts. Single Python file, minimal deps.

## Features

- **Idle alert** — all GPUs < 10% for 5min → red Slack alert
- **Partial idle** — some GPUs idle while others busy → yellow warning
- **Recovery** — GPUs become active again → green notification
- **Periodic status** — active: every 10min, idle: every 30min
- **Startup notification** — know when monitor comes online
- **GPU processes** — shows which processes are using each GPU
- **Per-machine color** — auto-assigned color bar for multi-machine setups
- **Uptime tracking** — shows `up 2h30m` or `idle 15min` in status
- **Watchdog** — auto-restart on crash
- **Log rotation** — 5MB x 3 backups

## Quick Start

```bash
pip install pyyaml
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
python gpu_monitor.py           # start monitoring
python gpu_monitor.py --once    # check status once
```

Or use the start script:

```bash
bash start.sh           # start in background
bash start.sh stop      # stop
bash start.sh restart   # restart
bash start.sh status    # check if running
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SLACK_WEBHOOK_URL` | — | Slack incoming webhook URL |
| `CHECK_INTERVAL` | `60` | Seconds between GPU checks |
| `IDLE_THRESHOLD` | `10` | Alert when util below this % |
| `IDLE_MINUTES` | `5` | Minutes idle before first alert |
| `ALERT_COOLDOWN` | `30` | Minutes between repeated alerts |
| `STATUS_ACTIVE` | `10` | Report interval when active (min) |
| `STATUS_IDLE` | `30` | Report interval when idle (min) |
| `MACHINE_COLOR` | auto | Hex color for Slack messages |
| `LOG_FILE` | — | Log file path (enables rotation) |

## Multi-Machine Setup

Deploy to each machine — each gets an auto-assigned color in Slack. All report to the same webhook/channel.

# GPU Monitor

Lightweight NVIDIA GPU monitor with multi-channel alerts. Single Python file, no external dependencies.

## Features

- **Idle alert** — all GPUs < 10% for 5min → alert
- **Process crash detection** — GPUs suddenly go idle while processes were running → instant alert
- **Partial idle** — some GPUs idle while others busy → warning
- **Recovery** — GPUs become active again → notification
- **Periodic status** — active: every 10min, idle: every 30min
- **Startup notification** — know when monitor comes online
- **GPU processes** — shows which processes are using each GPU, including username
- **Power draw** — shows watts per GPU in status messages (throttle detection)
- **Per-machine color** — auto-assigned color bar for multi-machine setups
- **Uptime tracking** — shows `up 2h30m` or `idle 15min` in status
- **Prometheus `/metrics`** — expose GPU stats for Grafana/alertmanager (requires `WEB_PORT`)
- **Watchdog** — auto-restart on crash
- **Log rotation** — 5MB x 3 backups

## Supported Notification Channels

| Channel | What you need |
|---------|---------------|
| **Slack** | Incoming webhook URL |
| **Discord** | Webhook URL |
| **Telegram** | Bot token + chat ID |
| **Email** | SMTP host, credentials, recipient |
| **SMS** | Twilio account SID, auth token, phone numbers |
| **iMessage** | macOS only, recipient phone/email |
| **WeCom (企业微信)** | Webhook URL |
| **Feishu (飞书)** | Webhook URL |
| **DingTalk (钉钉)** | Webhook URL |
| **Bark** | Bark server URL (self-hosted or api.day.app) |
| **OpenClaw** | Webhook URL + secret — routes to WhatsApp, Teams, Signal, LINE, Mattermost, Matrix, Zalo, and [20+ more](https://openclaw.ai) |

Configure one or more — only channels with credentials set will be used.

## Quick Start

```bash
# Slack only
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
python gpu_monitor.py

# Discord only
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/YOUR/WEBHOOK"
python gpu_monitor.py

# Telegram only
export TELEGRAM_BOT_TOKEN="your-bot-token"
export TELEGRAM_CHAT_ID="your-chat-id"
python gpu_monitor.py

# Multiple channels at once — just set multiple env vars
python gpu_monitor.py --once   # check status once and exit
```

Or use the start script:

```bash
bash start.sh           # start in background
bash start.sh stop      # stop
bash start.sh restart   # restart
bash start.sh status    # check if running
```

## Environment Variables

### General

| Variable | Default | Description |
|----------|---------|-------------|
| `CHECK_INTERVAL` | `60` | Seconds between GPU checks |
| `IDLE_THRESHOLD` | `10` | Alert when util below this % |
| `IDLE_MINUTES` | `5` | Minutes idle before first alert |
| `ALERT_COOLDOWN` | `30` | Minutes between repeated alerts |
| `STATUS_ACTIVE` | `10` | Report interval when active (min) |
| `STATUS_IDLE` | `30` | Report interval when idle (min) |
| `MACHINE_COLOR` | auto | Hex color for Slack/Discord |
| `LOG_FILE` | — | Log file path (enables rotation) |

### Slack

| Variable | Description |
|----------|-------------|
| `SLACK_WEBHOOK_URL` | Slack incoming webhook URL |

### Discord

| Variable | Description |
|----------|-------------|
| `DISCORD_WEBHOOK_URL` | Discord webhook URL |

### Telegram

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Target chat/group/channel ID |

### Email (SMTP)

| Variable | Default | Description |
|----------|---------|-------------|
| `EMAIL_SMTP_HOST` | — | SMTP server hostname |
| `EMAIL_SMTP_PORT` | `587` | SMTP port (STARTTLS) |
| `EMAIL_USER` | — | Login username |
| `EMAIL_PASS` | — | Login password or app password |
| `EMAIL_TO` | — | Recipient(s), comma-separated |

### SMS (Twilio)

| Variable | Description |
|----------|-------------|
| `TWILIO_ACCOUNT_SID` | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_FROM` | Twilio phone number (E.164 format) |
| `TWILIO_TO` | Recipient number(s), comma-separated |

### iMessage (macOS only)

| Variable | Description |
|----------|-------------|
| `IMESSAGE_TO` | Recipient phone/email, comma-separated |

### WeCom (企业微信)

| Variable | Description |
|----------|-------------|
| `WECOM_WEBHOOK_URL` | WeCom group bot webhook URL |

### Feishu (飞书 / Lark)

| Variable | Description |
|----------|-------------|
| `FEISHU_WEBHOOK_URL` | Feishu bot webhook URL |

### DingTalk (钉钉)

| Variable | Description |
|----------|-------------|
| `DINGTALK_WEBHOOK_URL` | DingTalk group robot webhook URL |

### Bark (iOS push)

| Variable | Description |
|----------|-------------|
| `BARK_URL` | Bark server URL, e.g. `https://api.day.app/YOUR_KEY` |

### OpenClaw

| Variable | Description |
|----------|-------------|
| `OPENCLAW_WEBHOOK_URL` | Your OpenClaw webhook URL, e.g. `http://your-host:18789/hooks/wake` |
| `OPENCLAW_WEBHOOK_SECRET` | Bearer token (from OpenClaw settings), if auth is enabled |

## Prometheus Metrics

When `WEB_PORT` is set, a `/metrics` endpoint is available for Prometheus scraping:

```bash
export WEB_PORT=8080
python gpu_monitor.py
# Metrics at http://localhost:8080/metrics
```

Exposed metrics: `gpu_utilization_percent`, `gpu_memory_used_mib`, `gpu_memory_total_mib`, `gpu_temperature_celsius`, `gpu_power_watts`, `gpu_clock_sm_mhz`. All labeled with `gpu`, `name`, and `host`.

Add to your `prometheus.yml`:
```yaml
scrape_configs:
  - job_name: gpu
    static_configs:
      - targets: ['your-server:8080']
```

## GitHub Pages Dashboard

Real-time GPU dashboard hosted on GitHub Pages — no server needed.

**Setup:**

1. Enable GitHub Pages in your repo: Settings → Pages → Source: `main` branch, `/docs` folder
2. Create a fine-grained personal access token with **Contents: read and write** on that repo
3. Set env vars on each machine you want to monitor:

```bash
export GITHUB_PAGES_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
export GITHUB_PAGES_REPO=your-username/your-repo
python gpu_monitor.py
```

The monitor pushes `docs/data/{hostname}.json` every check interval. The dashboard at `https://your-username.github.io/your-repo/` auto-refreshes every 30 seconds.

Multi-machine: each machine pushes its own file. The dashboard shows all machines side-by-side with online/stale/offline badges.

### GitHub Pages env vars

| Variable | Description |
|----------|-------------|
| `GITHUB_PAGES_TOKEN` | Fine-grained token with Contents read+write |
| `GITHUB_PAGES_REPO` | Repo to push stats to, e.g. `owner/repo` |
| `WEB_PORT` | Local web dashboard port (optional, e.g. `8080`) |

## Multi-Machine Setup

Deploy to each machine — each gets an auto-assigned color in Slack/Discord and the GitHub Pages dashboard. All report to the same webhook/channel.

## Setting Up Telegram

1. Message [@BotFather](https://t.me/BotFather) → `/newbot`
2. Copy the token → `TELEGRAM_BOT_TOKEN`
3. Send a message to your bot, then visit `https://api.telegram.org/bot<TOKEN>/getUpdates` to get `TELEGRAM_CHAT_ID`

## Setting Up Chinese Notification Channels

### WeCom (企业微信)
1. Open WeCom → Group Chat → Add Group Robot
2. Copy the webhook URL → `WECOM_WEBHOOK_URL`

### Feishu (飞书 / Lark)
1. Open Feishu group → Settings → Bots → Add Bot → Custom Bot
2. Copy the webhook URL → `FEISHU_WEBHOOK_URL`

### DingTalk (钉钉)
1. Open DingTalk group → Group Settings → Bots → Add Robot → Custom
2. Set keyword (e.g. `GPU`) in security settings — include it in your messages or set `IDLE_THRESHOLD` message text
3. Copy the webhook URL → `DINGTALK_WEBHOOK_URL`

### Bark (iOS)
1. Install [Bark](https://github.com/Finb/Bark) from the App Store
2. Copy your device URL → `BARK_URL` (e.g. `https://api.day.app/YOUR_DEVICE_KEY`)

## Setting Up OpenClaw

[OpenClaw](https://openclaw.ai) is a self-hosted AI assistant. Once running, its webhook turns it into a notification router for 20+ chat platforms — WhatsApp, Teams, Signal, LINE, Mattermost, Matrix, Zalo, Nostr, Twitch, and more.

1. Install and start OpenClaw on any machine (see [openclaw.ai](https://openclaw.ai))
2. In OpenClaw settings, enable the webhook gateway and copy the URL (default: `http://localhost:18789/hooks/wake`)
3. Set a webhook secret if auth is enabled:

```bash
export OPENCLAW_WEBHOOK_URL="http://your-openclaw-host:18789/hooks/wake"
export OPENCLAW_WEBHOOK_SECRET="your-bearer-token"  # optional, if auth enabled
python gpu_monitor.py
```

GPU alerts will be delivered to whichever chat channels you configured in OpenClaw.

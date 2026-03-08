# GPU Monitor

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/gpu-monitor.svg)](https://pypi.org/project/gpu-monitor/)

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
- **19 notification channels** — Slack, Discord, Telegram, Email, SMS, iMessage, WeCom, Feishu, DingTalk, Bark, Rocket.Chat, ntfy, Gotify, Pushover, Mattermost, Teams, Google Chat, Zulip, OpenClaw (+ **80+ more via [Apprise](https://github.com/caronc/apprise)**)
- **Memory leak detection** — alert when GPU memory grows unexpectedly without process changes
- **Temperature alerting** — `GPU_TEMP_WARN` / `GPU_TEMP_CRIT` thresholds, no Prometheus required
- **Power throttle alert** — notify when GPU power draw hits 95% of its TDP limit
- **Fan speed** — `gpu_fan_speed_percent` Prometheus metric for thermal correlation
- **Alertmanager receiver** — route all Prometheus alerts to 19+ channels via `POST /webhook`
- **`--test-notify`** — verify all configured channels with one command
- **`--json`** — output current GPU stats as JSON for shell scripting (`--json | jq '.gpus[].util'`)
- **Watchdog** — auto-restart on crash
- **Log rotation** — 5MB x 3 backups

## Why gpu-monitor?

| | gpu-monitor | gpustat | nvitop | wandb |
|---|---|---|---|---|
| Background alerts | ✅ | ❌ | ❌ | ❌ |
| Multi-channel notifications | ✅ 19 + 80 via Apprise | ❌ | ❌ | Slack only |
| Zero dependencies | ✅ stdlib only | ❌ | ❌ | ❌ |
| Single file deploy | ✅ | ❌ | ❌ | ❌ |
| Prometheus `/metrics` | ✅ | ❌ | ✅ | ❌ |
| Crash detection | ✅ | ❌ | ❌ | ❌ |
| Multi-machine dashboard | ✅ GitHub Pages | ❌ | ❌ | ✅ paid |

**gpustat** and **nvitop** are great interactive tools — gpu-monitor fills the complementary role of *unattended background monitoring with instant alerts*.

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
| **ntfy** | ntfy.sh topic URL (or self-hosted), optional auth token |
| **Gotify** | Gotify server URL + app token (self-hosted) |
| **Pushover** | App token + user key from pushover.net |
| **Rocket.Chat** | Incoming webhook URL |
| **Google Chat** | Google Chat space webhook URL |
| **Zulip** | Site URL + bot email + API key |
| **Mattermost** | Incoming webhook URL |
| **Microsoft Teams** | Teams incoming webhook URL |
| **OpenClaw** | Webhook URL + secret — routes to WhatsApp, Teams, Signal, LINE, Mattermost, Matrix, Zalo, and [20+ more](https://openclaw.ai) |

Configure one or more — only channels with credentials set will be used.

## Quick Start

```bash
# Install (pip, no dependencies)
pip install gpu-monitor

# Or just grab the single file
curl -O https://raw.githubusercontent.com/reacher-z/gpu-monitor/main/gpu_monitor.py
```

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
python gpu_monitor.py --once          # check status once and exit
python gpu_monitor.py --channels      # list which channels are configured
python gpu_monitor.py --test-notify   # send a test alert to verify all channels work
```

Or use the start script:

```bash
bash start.sh           # start in background
bash start.sh stop      # stop
bash start.sh restart   # restart
bash start.sh status    # check if running
```

Or run as a **systemd service** (auto-start on boot):

```bash
# 1. Download and configure the service file
curl -O https://raw.githubusercontent.com/reacher-z/gpu-monitor/main/gpu-monitor.service
# 2. Edit Environment= lines to set your notification channel vars
# 3. Install and start
sudo cp gpu-monitor.service /etc/systemd/system/gpu-monitor@$USER.service
sudo systemctl daemon-reload
sudo systemctl enable --now gpu-monitor@$USER
sudo journalctl -u gpu-monitor@$USER -f   # follow logs
```

## Example Output

**`--once` status check:**

```
gpu-cluster-1 | 2026-03-07 14:32 | avg 87% | 72C | 1820W | mem 188G/320G (59%)
[87% 91% 83% 88% 92% 79% 85% 90%]
GPU0: python3(18G)[alice] | GPU1: torchrun(22G)[bob] | GPU3: python3(18G)[carol]
```

**Slack alert when GPUs go idle:**

```
gpu-cluster-1 | 2026-03-07 15:01 | avg 2% | 38C | idle 8min
All GPUs idle for 8 minutes. Last active: training job (alice)
```

**Crash detection alert (PIDs disappeared while GPUs were busy):**

```
gpu-cluster-1 | GPUs went idle — processes exited: 12345, 12346, 12347 | avg 1% | 38C | mem 2G/320G (1%)
```

**`--test-notify` output:**

```
Test notification sent to: Slack, Discord, ntfy
Not configured:           Telegram, Email, SMS, iMessage, WeCom, Feishu, DingTalk, Bark, Teams, Pushover, Gotify, Mattermost, Google Chat, Zulip, OpenClaw
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
| `WEB_PORT` | — | Local dashboard + `/metrics` port (disabled if unset) |
| `APPRISE_URLS` | — | Space/comma-separated [Apprise](https://github.com/caronc/apprise) URLs (optional, `pip install apprise`) |
| `MEMLEAK_THRESHOLD` | `30` | GPU memory growth % to trigger leak alert |
| `MEMLEAK_MINUTES` | `10` | Window (minutes) for memory leak detection |
| `GPU_TEMP_WARN` | `85` | °C threshold for high temperature warning alert |
| `GPU_TEMP_CRIT` | `92` | °C threshold for critical temperature alert |

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

### ntfy

| Variable | Description |
|----------|-------------|
| `NTFY_URL` | ntfy topic URL, e.g. `https://ntfy.sh/my-gpu-alerts` or self-hosted |
| `NTFY_TOKEN` | Auth token (optional, for protected topics) |

### Gotify

| Variable | Description |
|----------|-------------|
| `GOTIFY_URL` | Gotify server URL, e.g. `http://gotify.example.com` |
| `GOTIFY_TOKEN` | App token from Gotify dashboard |

### Pushover

| Variable | Description |
|----------|-------------|
| `PUSHOVER_TOKEN` | App API token from [pushover.net](https://pushover.net) |
| `PUSHOVER_USER` | Your user/group key |

### Rocket.Chat

| Variable | Description |
|----------|-------------|
| `ROCKETCHAT_WEBHOOK_URL` | Rocket.Chat incoming webhook URL (Administration → Integrations → Incoming WebHook) |

### Google Chat

| Variable | Description |
|----------|-------------|
| `GOOGLE_CHAT_WEBHOOK_URL` | Google Chat space webhook URL (Space → Manage webhooks) |

### Zulip

| Variable | Description | Default |
|----------|-------------|---------|
| `ZULIP_SITE` | Your Zulip server URL, e.g. `https://yourorg.zulipchat.com` | — |
| `ZULIP_EMAIL` | Bot email address | — |
| `ZULIP_API_KEY` | Bot API key | — |
| `ZULIP_STREAM` | Stream to post to | `general` |
| `ZULIP_TOPIC` | Topic/thread name | `GPU Monitor` |

### Mattermost

| Variable | Description |
|----------|-------------|
| `MATTERMOST_WEBHOOK_URL` | Mattermost incoming webhook URL (Main Menu → Integrations → Incoming Webhooks) |

### Microsoft Teams

| Variable | Description |
|----------|-------------|
| `TEAMS_WEBHOOK_URL` | Teams incoming webhook URL (channel → ⋯ → Connectors → Incoming Webhook) |

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

Exposed metrics: `gpu_utilization_percent`, `gpu_memory_used_mib`, `gpu_memory_total_mib`, `gpu_memory_utilization_percent`, `gpu_temperature_celsius`, `gpu_power_watts`, `gpu_power_limit_watts`, `gpu_clock_sm_mhz`, `gpu_fan_speed_percent`, `gpu_process_count`. All labeled with `gpu` index and `host`.

Add to your `prometheus.yml`:
```yaml
scrape_configs:
  - job_name: gpu
    static_configs:
      - targets: ['your-server:8080']
```

A pre-built **Grafana dashboard** is included at [`grafana/dashboard.json`](grafana/dashboard.json) — import it in Grafana via Dashboards → Import → Upload JSON. It includes utilization, memory, temperature, and power panels with host and GPU variable filters.

**Prometheus alerting rules** are included at [`grafana/alerts.yml`](grafana/alerts.yml) — copy to your Prometheus `rules/` directory and add to `prometheus.yml`:

```yaml
rule_files:
  - rules/gpu-monitor-alerts.yml
```

Included rules:

| Alert | Condition | Severity |
|-------|-----------|----------|
| `GPUAllIdle` | avg util < 10% for 5m | warning |
| `GPUHighTemperature` | temp > 85°C for 2m | warning |
| `GPUCriticalTemperature` | temp > 92°C for 1m | critical |
| `GPUMemoryHigh` | mem util > 90% for 5m | warning |
| `GPUMemoryFull` | mem util > 98% for 2m | critical |
| `GPUMonitorDown` | no metrics for 3m | critical |

### Alertmanager webhook receiver

When `WEB_PORT` is set, gpu-monitor also acts as an Alertmanager webhook receiver — forwarding **any** Prometheus alert (GPU or otherwise) to all 19 configured notification channels.

Configure in Alertmanager:
```yaml
receivers:
  - name: gpu-monitor
    webhook_configs:
      - url: http://your-server:8080/webhook
        send_resolved: true
```

Alerts arrive with severity-appropriate formatting (`:fire:` for critical, `:warning:` for warning) and resolved alerts are announced with `:white_check_mark:`.

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

## Setting Up Apprise (80+ Extra Services)

[Apprise](https://github.com/caronc/apprise) is an optional dependency that adds support for 80+ additional notification services (AWS SNS, Pushbullet, Home Assistant, Matrix, Ryver, SparkPost, and many more) through a single URL-based configuration.

```bash
pip install apprise
export APPRISE_URLS="slack://TokenA/TokenB/TokenC/#channel tgram://bot_token/chat_id"
python gpu_monitor.py
```

The core gpu-monitor has zero dependencies — Apprise is only used if it is installed and `APPRISE_URLS` is set.

For a full list of supported URL formats see the [Apprise wiki](https://github.com/caronc/apprise/wiki).

## Setting Up ntfy

[ntfy](https://ntfy.sh) is a simple, zero-signup push notification service. Subscribe via the ntfy app (Android/iOS), the web UI, or any HTTP client.

```bash
# No account needed — just pick any topic name
export NTFY_URL="https://ntfy.sh/my-gpu-cluster-abc123"
python gpu_monitor.py
```

Subscribe to the same topic in the ntfy app on your phone to receive GPU alerts instantly. For private topics, generate a token at [ntfy.sh/app](https://ntfy.sh/app) and set `NTFY_TOKEN`.

Self-hosted: replace `https://ntfy.sh/` with your server URL.

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

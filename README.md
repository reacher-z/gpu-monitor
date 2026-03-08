# GPU Monitor

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/gpu-watchdog.svg)](https://pypi.org/project/gpu-watchdog/)
[![20 channels](https://img.shields.io/badge/channels-20-blueviolet.svg)](#supported-notification-channels)

**Get alerted on Slack, Discord, Telegram (20 notification channels total) when your GPU training crashes, goes idle, or overheats.** Single Python file. Zero dependencies. Works in the background while you sleep.

```bash
pip install gpu-watchdog
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK"
gpu-monitor   # or: python gpu_monitor.py
```

---

## Table of Contents

- [Quick Start](#quick-start)
- [Example Output](#example-output)
- [Why gpu-monitor?](#why-gpu-monitor)
- [Features](#features)
- [Supported Notification Channels](#supported-notification-channels)
- [Environment Variables](#environment-variables)
  - [General](#general)
  - [Per-channel variables](#per-channel-variables)
- [Prometheus Metrics](#prometheus-metrics)
- [Alertmanager Webhook Receiver](#alertmanager-webhook-receiver)
- [Kubernetes](#kubernetes)
- [GitHub Pages Dashboard](#github-pages-dashboard)
- [Multi-Machine Setup](#multi-machine-setup)
- [Setting Up Specific Channels](#setting-up-specific-channels)
  - [Telegram](#setting-up-telegram)
  - [Chinese channels (WeCom, Feishu, DingTalk, Bark)](#setting-up-chinese-notification-channels)
  - [ntfy](#setting-up-ntfy)
  - [Apprise (80+ extra services)](#setting-up-apprise-80-extra-services)
  - [OpenClaw](#setting-up-openclaw)

---

## Quick Start

**Install:**

```bash
# Option 1: pip (recommended)
pip install gpu-watchdog

# Option 2: single file, no install needed
curl -O https://raw.githubusercontent.com/reacher-z/gpu-monitor/main/gpu_monitor.py
```

**Run with your notification channel:**

```bash
# Slack
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
python gpu_monitor.py

# Discord
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/YOUR/WEBHOOK"
python gpu_monitor.py

# Telegram
export TELEGRAM_BOT_TOKEN="your-bot-token"
export TELEGRAM_CHAT_ID="your-chat-id"
python gpu_monitor.py

# ntfy (zero-signup push notifications to your phone)
export NTFY_URL="https://ntfy.sh/my-gpu-cluster-abc123"
python gpu_monitor.py
```

Set multiple env vars to send to multiple channels simultaneously.

**Useful CLI flags:**

```bash
python gpu_monitor.py --once          # check once and print status, then exit
python gpu_monitor.py --json          # output current GPU stats as JSON
python gpu_monitor.py --watch 2       # live color terminal table, 2-second refresh
python gpu_monitor.py --channels      # show which notification channels are configured
python gpu_monitor.py --test-notify   # send a test alert to all configured channels
python gpu_monitor.py --web 8080      # dashboard + Prometheus /metrics at :8080
```

**Run as a background service (systemd):**

```bash
curl -O https://raw.githubusercontent.com/reacher-z/gpu-monitor/main/gpu-monitor.service
# Edit the Environment= lines with your notification credentials, then:
sudo cp gpu-monitor.service /etc/systemd/system/gpu-monitor@$USER.service
sudo systemctl daemon-reload
sudo systemctl enable --now gpu-monitor@$USER
sudo journalctl -u gpu-monitor@$USER -f   # follow logs
```

**Run with the full monitoring stack (Prometheus + Grafana + Alertmanager):**

```bash
cp .env.example .env && $EDITOR .env   # add your notification credentials
docker compose -f docker-compose.monitoring.yml up -d
# Grafana at http://localhost:3000  (admin/admin)
# Import grafana/dashboard.json for the pre-built GPU dashboard
```

**Deploy to Kubernetes as a DaemonSet on every GPU node:**

```bash
# Edit kubernetes/secret.yaml with your notification credentials
kubectl apply -k kubernetes/
```

---

## Example Output

**`--watch` live terminal view:**

```
gpu-cluster-1          2026-03-07 14:32
GPU  Name                 Util   Mem         Temp   Power   Procs
  0  NVIDIA A100-SXM4-80  87%    18G/80G     72°C   312W    python3[alice]
  1  NVIDIA A100-SXM4-80  91%    22G/80G     75°C   318W    torchrun[bob]
  2  NVIDIA A100-SXM4-80  83%    18G/80G     69°C   305W    python3[carol]
  3  NVIDIA A100-SXM4-80  88%    21G/80G     71°C   310W    torchrun[bob]
```

**`--once` status check:**

```
gpu-cluster-1 | 2026-03-07 14:32 | avg 87% | 72C | 1820W | mem 188G/320G (59%)
[87% 91% 83% 88% 92% 79% 85% 90%]
GPU0: python3(18G)[alice] | GPU1: torchrun(22G)[bob] | GPU3: python3(18G)[carol]
```

**Slack/Discord alert when all GPUs go idle:**

```
gpu-cluster-1 | 2026-03-07 15:01 | avg 2% | 38C | idle 8min
All GPUs idle for 8 minutes. Last active: training job (alice)
```

**Crash detection alert (processes exited while GPUs were busy):**

```
gpu-cluster-1 | GPUs went idle — processes exited: 12345, 12346, 12347 | avg 1% | 38C | mem 2G/320G (1%)
```

**`--test-notify` output:**

```
Test notification sent to: Slack, Discord, ntfy
Not configured:           Telegram, Email, SMS, iMessage, WeCom, Feishu, DingTalk, Bark,
                          Teams, Pushover, Gotify, Mattermost, Google Chat, Zulip, OpenClaw
```

---

## Why gpu-monitor?

| | gpu-monitor | gpustat | nvitop | wandb |
|---|---|---|---|---|
| Background alerts | ✅ | ❌ | ❌ | ❌ |
| Multi-channel notifications | ✅ 20 + 80 via Apprise | ❌ | ❌ | Slack only |
| Zero dependencies | ✅ stdlib only | ❌ | ❌ | ❌ |
| Single file deploy | ✅ | ❌ | ❌ | ❌ |
| Prometheus `/metrics` | ✅ 11 metrics | ❌ | ✅ | ❌ |
| InfluxDB / Datadog / OTLP | ✅ | ❌ | ❌ | ❌ |
| Crash detection | ✅ | ❌ | ❌ | ❌ |
| Temperature alerting | ✅ | ❌ | ❌ | ❌ |
| ECC error detection | ✅ | ❌ | ❌ | ❌ |
| Alertmanager receiver | ✅ | ❌ | ❌ | ❌ |
| Live terminal view | ✅ `--watch` | ✅ | ✅ | ❌ |
| Kubernetes DaemonSet | ✅ | ❌ | ❌ | ❌ |
| Multi-machine dashboard | ✅ GitHub Pages | ❌ | ❌ | ✅ paid |

**gpustat** and **nvitop** are excellent interactive tools — gpu-monitor fills the complementary role of *unattended background monitoring with instant alerts*.

---

## Features

**Alerting**
- **Idle alert** — all GPUs below 10% utilization for 5 min → alert
- **Process crash detection** — GPUs suddenly go idle while processes were running → instant alert
- **Partial idle** — some GPUs idle while others are busy → warning
- **Recovery notification** — GPUs become active again → notify
- **Temperature alerting** — configurable `GPU_TEMP_WARN` / `GPU_TEMP_CRIT` thresholds, no Prometheus required
- **Power throttle alert** — fires when power draw hits 95% of TDP limit
- **ECC error detection** — alert on uncorrected volatile ECC errors (A100/H100/V100); prevents silent training corruption
- **Memory leak detection** — alert when GPU memory grows unexpectedly without process changes

**Status & Visibility**
- **Periodic status** — active: every 10 min, idle: every 30 min
- **Startup notification** — know when the monitor comes online
- **GPU processes** — shows which processes are using each GPU with username
- **Power draw** — shows watts per GPU in status messages
- **Per-machine color** — auto-assigned color bar in Slack/Discord for multi-machine setups
- **Uptime tracking** — shows `up 2h30m` or `idle 15min` in status
- **`--watch`** — live ANSI color terminal table (like a lite nvtop): `gpu_monitor.py --watch 2`
- **`--json`** — output current GPU stats as JSON: `--json | jq '.gpus[].util'`

**Observability Integrations**
- **Prometheus `/metrics`** — 11 metrics exposed when `WEB_PORT` is set; ready for Grafana
- **InfluxDB export** — line protocol to InfluxDB v1/v2 (`INFLUXDB_URL`)
- **Datadog export** — DogStatsD gauges (`DATADOG_STATSD_HOST`)
- **OpenTelemetry OTLP** — export to any OTel-compatible backend (`OTEL_EXPORTER_OTLP_ENDPOINT`)
- **Alertmanager receiver** — route any Prometheus alert to all 20 channels via `POST /webhook`
- **`ALERT_WEBHOOK_URL`** — POST JSON to any HTTP endpoint on every alert (CI/CD, custom integrations)
- **Web dashboard sparklines** — `--web PORT` shows per-GPU utilization history

**Deployment**
- **20 notification channels** — Slack, Discord, Telegram, Email, SMS, iMessage, WeCom, Feishu, DingTalk, Bark, Rocket.Chat, ntfy, Gotify, Pushover, Mattermost, Teams, Google Chat, Zulip, OpenClaw, PagerDuty (+ **80+ more via [Apprise](https://github.com/caronc/apprise)**)
- **`--test-notify`** — verify all configured channels with one command
- **Kubernetes DaemonSet** — deploy to every GPU node with one `kubectl apply -k kubernetes/`
- **GitHub Pages dashboard** — multi-machine status page, no server required
- **Watchdog** — auto-restart on crash
- **Log rotation** — 5 MB × 3 backups

---

## Supported Notification Channels

20 channels built in. Set the relevant env vars — only channels with credentials configured are used.

| Channel | Env var(s) needed |
|---------|-------------------|
| **Slack** | `SLACK_WEBHOOK_URL` |
| **Discord** | `DISCORD_WEBHOOK_URL` |
| **Telegram** | `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` |
| **Email (SMTP)** | `EMAIL_SMTP_HOST`, `EMAIL_USER`, `EMAIL_PASS`, `EMAIL_TO` |
| **SMS (Twilio)** | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`, `TWILIO_TO` |
| **iMessage** | `IMESSAGE_TO` (macOS only) |
| **WeCom (企业微信)** | `WECOM_WEBHOOK_URL` |
| **Feishu (飞书)** | `FEISHU_WEBHOOK_URL` |
| **DingTalk (钉钉)** | `DINGTALK_WEBHOOK_URL` |
| **Bark** | `BARK_URL` (self-hosted or api.day.app) |
| **ntfy** | `NTFY_URL` (+ optional `NTFY_TOKEN`) |
| **Gotify** | `GOTIFY_URL` + `GOTIFY_TOKEN` |
| **Pushover** | `PUSHOVER_TOKEN` + `PUSHOVER_USER` |
| **Rocket.Chat** | `ROCKETCHAT_WEBHOOK_URL` |
| **Google Chat** | `GOOGLE_CHAT_WEBHOOK_URL` |
| **Zulip** | `ZULIP_SITE` + `ZULIP_EMAIL` + `ZULIP_API_KEY` |
| **Mattermost** | `MATTERMOST_WEBHOOK_URL` |
| **Microsoft Teams** | `TEAMS_WEBHOOK_URL` |
| **OpenClaw** | `OPENCLAW_WEBHOOK_URL` — routes to WhatsApp, Signal, LINE, Matrix, Zalo, [20+ more](https://openclaw.ai) |
| **PagerDuty** | `PAGERDUTY_INTEGRATION_KEY` (Events API v2) |
| **Apprise (80+ more)** | `APPRISE_URLS` — requires `pip install apprise` |

---

## Environment Variables

### General

| Variable | Default | Description |
|----------|---------|-------------|
| `CHECK_INTERVAL` | `60` | Seconds between GPU checks |
| `IDLE_THRESHOLD` | `10` | Alert when utilization drops below this % |
| `IDLE_MINUTES` | `5` | Minutes idle before the first alert fires |
| `ALERT_COOLDOWN` | `30` | Minutes between repeated alerts |
| `STATUS_ACTIVE` | `10` | Periodic status interval when active (minutes) |
| `STATUS_IDLE` | `30` | Periodic status interval when idle (minutes) |
| `MACHINE_COLOR` | auto | Hex color for Slack/Discord messages |
| `LOG_FILE` | — | Log file path (enables rotation) |
| `WEB_PORT` | — | Enables local dashboard + `/metrics` on this port |
| `MEMLEAK_THRESHOLD` | `30` | GPU memory growth % to trigger a leak alert |
| `MEMLEAK_MINUTES` | `10` | Window (minutes) for memory leak detection |
| `GPU_TEMP_WARN` | `85` | °C threshold for high-temperature warning alert |
| `GPU_TEMP_CRIT` | `92` | °C threshold for critical temperature alert |
| `ALERT_WEBHOOK_URL` | — | HTTP endpoint to POST JSON on every alert |
| `INFLUXDB_URL` | — | InfluxDB server URL (e.g. `http://influxdb:8086`) |
| `INFLUXDB_TOKEN` | — | API token (v2) or `user:password` (v1) |
| `INFLUXDB_BUCKET` | `gpu_metrics` | InfluxDB v2 bucket or v1 `db/rp` |
| `INFLUXDB_ORG` | — | InfluxDB v2 organization name |
| `DATADOG_STATSD_HOST` | — | Hostname of Datadog agent (enables DogStatsD export) |
| `DATADOG_STATSD_PORT` | `8125` | DogStatsD port |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | OTel Collector URL (e.g. `http://otel-collector:4318`) |
| `OTEL_SERVICE_NAME` | `gpu-monitor` | Service name for OTLP resource attributes |
| `OTEL_EXPORTER_OTLP_HEADERS` | — | Extra headers as `key=val,key2=val2` |
| `APPRISE_URLS` | — | Space/comma-separated [Apprise](https://github.com/caronc/apprise) URLs (`pip install apprise` required) |

### Per-channel variables

#### Slack
| Variable | Description |
|----------|-------------|
| `SLACK_WEBHOOK_URL` | Slack incoming webhook URL |

#### Discord
| Variable | Description |
|----------|-------------|
| `DISCORD_WEBHOOK_URL` | Discord webhook URL |

#### Telegram
| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Target chat/group/channel ID |

#### Email (SMTP)
| Variable | Default | Description |
|----------|---------|-------------|
| `EMAIL_SMTP_HOST` | — | SMTP server hostname |
| `EMAIL_SMTP_PORT` | `587` | SMTP port (STARTTLS) |
| `EMAIL_USER` | — | Login username |
| `EMAIL_PASS` | — | Login password or app password |
| `EMAIL_TO` | — | Recipient(s), comma-separated |

#### SMS (Twilio)
| Variable | Description |
|----------|-------------|
| `TWILIO_ACCOUNT_SID` | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_FROM` | Twilio phone number (E.164 format) |
| `TWILIO_TO` | Recipient number(s), comma-separated |

#### iMessage (macOS only)
| Variable | Description |
|----------|-------------|
| `IMESSAGE_TO` | Recipient phone/email, comma-separated |

#### WeCom (企业微信)
| Variable | Description |
|----------|-------------|
| `WECOM_WEBHOOK_URL` | WeCom group bot webhook URL |

#### Feishu (飞书 / Lark)
| Variable | Description |
|----------|-------------|
| `FEISHU_WEBHOOK_URL` | Feishu bot webhook URL |

#### DingTalk (钉钉)
| Variable | Description |
|----------|-------------|
| `DINGTALK_WEBHOOK_URL` | DingTalk group robot webhook URL |

#### Bark (iOS push)
| Variable | Description |
|----------|-------------|
| `BARK_URL` | Bark server URL, e.g. `https://api.day.app/YOUR_KEY` |

#### ntfy
| Variable | Description |
|----------|-------------|
| `NTFY_URL` | ntfy topic URL, e.g. `https://ntfy.sh/my-gpu-alerts` |
| `NTFY_TOKEN` | Auth token (optional, for protected topics) |

#### Gotify
| Variable | Description |
|----------|-------------|
| `GOTIFY_URL` | Gotify server URL, e.g. `http://gotify.example.com` |
| `GOTIFY_TOKEN` | App token from Gotify dashboard |

#### Pushover
| Variable | Description |
|----------|-------------|
| `PUSHOVER_TOKEN` | App API token from [pushover.net](https://pushover.net) |
| `PUSHOVER_USER` | Your user/group key |

#### Rocket.Chat
| Variable | Description |
|----------|-------------|
| `ROCKETCHAT_WEBHOOK_URL` | Incoming webhook URL (Administration → Integrations → Incoming WebHook) |

#### Google Chat
| Variable | Description |
|----------|-------------|
| `GOOGLE_CHAT_WEBHOOK_URL` | Google Chat space webhook URL (Space → Manage webhooks) |

#### Zulip
| Variable | Default | Description |
|----------|---------|-------------|
| `ZULIP_SITE` | — | Your Zulip server URL, e.g. `https://yourorg.zulipchat.com` |
| `ZULIP_EMAIL` | — | Bot email address |
| `ZULIP_API_KEY` | — | Bot API key |
| `ZULIP_STREAM` | `general` | Stream to post to |
| `ZULIP_TOPIC` | `GPU Monitor` | Topic/thread name |

#### Mattermost
| Variable | Description |
|----------|-------------|
| `MATTERMOST_WEBHOOK_URL` | Incoming webhook URL (Main Menu → Integrations → Incoming Webhooks) |

#### Microsoft Teams
| Variable | Description |
|----------|-------------|
| `TEAMS_WEBHOOK_URL` | Teams incoming webhook URL (channel → ... → Connectors → Incoming Webhook) |

#### OpenClaw
| Variable | Description |
|----------|-------------|
| `OPENCLAW_WEBHOOK_URL` | Your OpenClaw webhook URL, e.g. `http://your-host:18789/hooks/wake` |
| `OPENCLAW_WEBHOOK_SECRET` | Bearer token (from OpenClaw settings), if auth is enabled |

#### PagerDuty
| Variable | Description |
|----------|-------------|
| `PAGERDUTY_INTEGRATION_KEY` | 32-character Events API v2 integration key from PagerDuty |

Create an integration in PagerDuty: Service → Integrations → Add integration → Events API v2. Copy the integration key.

---

## Prometheus Metrics

Enable with `WEB_PORT`:

```bash
export WEB_PORT=8080
python gpu_monitor.py
# Metrics at http://localhost:8080/metrics
# Dashboard at http://localhost:8080/
```

**11 exposed metrics**, all labeled with `gpu` index and `host`:

`gpu_utilization_percent`, `gpu_memory_used_mib`, `gpu_memory_total_mib`, `gpu_memory_utilization_percent`, `gpu_temperature_celsius`, `gpu_power_watts`, `gpu_power_limit_watts`, `gpu_clock_sm_mhz`, `gpu_fan_speed_percent`, `gpu_ecc_errors_uncorrected`, `gpu_process_count`

Add to `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: gpu
    static_configs:
      - targets: ['your-server:8080']
```

**Pre-built Grafana dashboard** is at [`grafana/dashboard.json`](grafana/dashboard.json) — import via Dashboards → Import → Upload JSON. Includes utilization, memory, temperature, and power panels with host and GPU variable filters.

**Prometheus alerting rules** are at [`grafana/alerts.yml`](grafana/alerts.yml):

```yaml
rule_files:
  - rules/gpu-monitor-alerts.yml
```

| Alert | Condition | Severity |
|-------|-----------|----------|
| `GPUAllIdle` | avg util < 10% for 5m | warning |
| `GPUHighTemperature` | temp > 85°C for 2m | warning |
| `GPUCriticalTemperature` | temp > 92°C for 1m | critical |
| `GPUMemoryHigh` | mem util > 90% for 5m | warning |
| `GPUMemoryFull` | mem util > 98% for 2m | critical |
| `GPUMonitorDown` | no metrics for 3m | critical |

---

## Alertmanager Webhook Receiver

When `WEB_PORT` is set, gpu-monitor also acts as an Alertmanager webhook receiver — forwarding **any** Prometheus alert (GPU or otherwise) to all 20 configured notification channels.

Configure in Alertmanager:

```yaml
receivers:
  - name: gpu-monitor
    webhook_configs:
      - url: http://your-server:8080/webhook
        send_resolved: true
```

Alerts arrive with severity-appropriate formatting (fire icon for critical, warning icon for warning). Resolved alerts are announced separately.

A pre-configured `grafana/alertmanager.yml` is included that routes all Prometheus alerts through gpu-monitor's webhook receiver automatically.

---

## Kubernetes

Deploy as a DaemonSet to monitor every GPU node:

```bash
# Edit kubernetes/secret.yaml with your notification channel credentials
kubectl apply -k kubernetes/
```

The DaemonSet:
- Schedules on nodes labeled `nvidia.com/gpu: "true"`
- Exposes `/metrics` on port 8080 with Prometheus scraping annotations
- Uses `spec.nodeName` as hostname for per-node identification in alerts
- Reads credentials from a `gpu-monitor-secrets` Secret

For Prometheus pod auto-discovery:

```yaml
# In prometheus.yml:
- job_name: gpu-monitor
  kubernetes_sd_configs:
    - role: pod
      namespaces:
        names: [gpu-monitor]
  relabel_configs:
    - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
      action: keep
      regex: "true"
    - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_port]
      action: replace
      target_label: __address__
      regex: (.+)
      replacement: ${1}:8080
```

---

## GitHub Pages Dashboard

Real-time GPU dashboard hosted on GitHub Pages — no extra server needed.

**Setup:**

1. Enable GitHub Pages in your repo: Settings → Pages → Source: `main` branch, `/docs` folder
2. Create a fine-grained personal access token with **Contents: read and write** on that repo
3. Set env vars on each machine:

```bash
export GITHUB_PAGES_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
export GITHUB_PAGES_REPO=your-username/your-repo
python gpu_monitor.py
```

The monitor pushes `docs/data/{hostname}.json` every check interval. The dashboard at `https://your-username.github.io/your-repo/` auto-refreshes every 30 seconds.

Multi-machine: each machine pushes its own file. The dashboard shows all machines side-by-side with online/stale/offline badges.

| Variable | Description |
|----------|-------------|
| `GITHUB_PAGES_TOKEN` | Fine-grained token with Contents read+write |
| `GITHUB_PAGES_REPO` | Repo to push stats to, e.g. `owner/repo` |

---

## Multi-Machine Setup

Deploy to each machine — each gets an auto-assigned color in Slack/Discord and appears on the GitHub Pages dashboard. All report to the same webhook/channel.

---

## Setting Up Specific Channels

### Setting Up Telegram

1. Message [@BotFather](https://t.me/BotFather) → `/newbot`
2. Copy the token → `TELEGRAM_BOT_TOKEN`
3. Send a message to your bot, then visit `https://api.telegram.org/bot<TOKEN>/getUpdates` to find your `TELEGRAM_CHAT_ID`

### Setting Up Chinese Notification Channels

**WeCom (企业微信)**
1. Open WeCom → Group Chat → Add Group Robot
2. Copy the webhook URL → `WECOM_WEBHOOK_URL`

**Feishu (飞书 / Lark)**
1. Open Feishu group → Settings → Bots → Add Bot → Custom Bot
2. Copy the webhook URL → `FEISHU_WEBHOOK_URL`

**DingTalk (钉钉)**
1. Open DingTalk group → Group Settings → Bots → Add Robot → Custom
2. Set a keyword (e.g. `GPU`) in security settings
3. Copy the webhook URL → `DINGTALK_WEBHOOK_URL`

**Bark (iOS)**
1. Install [Bark](https://github.com/Finb/Bark) from the App Store
2. Copy your device URL → `BARK_URL` (e.g. `https://api.day.app/YOUR_DEVICE_KEY`)

### Setting Up ntfy

[ntfy](https://ntfy.sh) is a zero-signup push notification service. Subscribe via the ntfy app (Android/iOS), web UI, or any HTTP client.

```bash
# No account needed — just pick any topic name
export NTFY_URL="https://ntfy.sh/my-gpu-cluster-abc123"
python gpu_monitor.py
```

Subscribe to the same topic in the ntfy app on your phone to receive alerts instantly. For private topics, generate a token at [ntfy.sh/app](https://ntfy.sh/app) and set `NTFY_TOKEN`.

Self-hosted: replace `https://ntfy.sh/` with your own server URL.

### Setting Up Apprise (80+ Extra Services)

[Apprise](https://github.com/caronc/apprise) is an optional dependency that adds 80+ additional services — AWS SNS, Pushbullet, Home Assistant, Matrix, SparkPost, and more — through URL-based configuration.

```bash
pip install apprise
export APPRISE_URLS="slack://TokenA/TokenB/TokenC/#channel tgram://bot_token/chat_id"
python gpu_monitor.py
```

The core gpu-monitor has zero dependencies — Apprise is only activated when installed and `APPRISE_URLS` is set.

See the full list of URL formats in the [Apprise wiki](https://github.com/caronc/apprise/wiki).

### Setting Up OpenClaw

[OpenClaw](https://openclaw.ai) is a self-hosted notification router that delivers to 20+ chat platforms — WhatsApp, Teams, Signal, LINE, Mattermost, Matrix, Zalo, and more.

1. Install and start OpenClaw (see [openclaw.ai](https://openclaw.ai))
2. In OpenClaw settings, enable the webhook gateway and copy the URL
3. Configure:

```bash
export OPENCLAW_WEBHOOK_URL="http://your-openclaw-host:18789/hooks/wake"
export OPENCLAW_WEBHOOK_SECRET="your-bearer-token"  # optional, if auth enabled
python gpu_monitor.py
```

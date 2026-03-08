# Changelog

## [0.3.0] — 2026-03-07

### Added
- **19 notification channels total**: ntfy, Gotify, Pushover, Microsoft Teams, Mattermost, Google Chat, Zulip, Rocket.Chat, OpenClaw added (joins Slack, Discord, Telegram, Email, SMS, iMessage, WeCom, Feishu, DingTalk, Bark)
- **`--channels` CLI flag** — list all configured (active/inactive) channels and exit
- **`--test-notify` CLI flag** — send a test message to all configured channels
- **`--version` CLI flag** — print version and exit
- **systemd service file** (`gpu-monitor.service`) — auto-start on boot
- **Dockerfile + docker-compose.yml** — containerized deployment with NVIDIA runtime
- **`pyproject.toml`** — installable via `pip install gpu-monitor`
- **`CITATION.cff`** — BibTeX/Zotero citation support for academic users
- **`CHANGELOG.md`** — this file
- **Prometheus `/metrics` endpoint** — expose GPU stats for Grafana/alertmanager (set `WEB_PORT`)
- **Power draw monitoring** — watts per GPU in status messages (thermal throttle detection)
- **GPU clock speed** — SM clock MHz shown in status and dashboard
- **Username per process** — shows who owns each GPU via `/proc` UID lookup
- **Process crash detection** — PID-based tracking, instant alert when training processes vanish
- **GitHub Pages multi-machine dashboard** — push stats to a repo, view all machines side-by-side
- **Partial idle detection** — warning when some GPUs idle while others are busy
- **Dashboard**: dark/light theme toggle (keyboard shortcut `t`), `r` to refresh, version badge per machine
- **Grafana dashboard** (`grafana/dashboard.json`) — importable pre-built dashboard with utilization, memory, temperature, and power panels; host/GPU variable filters; 30s auto-refresh
- **Prometheus alerting rules** (`grafana/alerts.yml`) — 6 rules: idle, high temp, critical temp, high memory, full memory, exporter-down
- **Temperature alerting** — `GPU_TEMP_WARN` (default 85°C) and `GPU_TEMP_CRIT` (default 92°C) trigger notifications via all configured channels without requiring Prometheus; 5°C hysteresis prevents flapping
- **Power throttle alert** — notify when GPU power draw reaches 95% of enforced power limit; 5% hysteresis
- **Fan speed metric** — `gpu_fan_speed_percent` Prometheus metric (from `nvidia-smi fan.speed`)
- **Power limit metric** — `gpu_power_limit_watts` Prometheus metric (enforced.power.limit)
- **Alertmanager webhook receiver** — `POST /webhook` on `WEB_PORT` accepts Prometheus Alertmanager payloads and routes them to all 19+ configured channels; supports firing/resolved and severity
- **`--json` flag** — print current GPU stats and processes as JSON and exit (scriptable: `gpu_monitor.py --json | jq '.gpus[].util'`)
- **ECC error detection** — alert when uncorrected volatile ECC errors increase on data-center GPUs (A100/H100/V100); `gpu_ecc_errors_uncorrected` Prometheus metric
- **`ALERT_WEBHOOK_URL`** — POST `{"host","text","color","timestamp"}` JSON to any HTTP endpoint on every alert; useful for CI/CD, PagerDuty, custom integrations
- **Grafana dashboard updated** — added Fan Speed panel and Power Draw vs Limit panel (v2)
- **Kubernetes DaemonSet** (`kubernetes/`) — deploy to every GPU node via `kubectl apply -k kubernetes/`; includes DaemonSet, Service, Secret template, Namespace, and Kustomize config
- **Complete monitoring stack** (`docker-compose.monitoring.yml`) — one-command setup: gpu-monitor + Prometheus + Grafana + Alertmanager with auto-provisioned datasource and dashboard
- **Prometheus config** (`grafana/prometheus.yml`) — ready-to-use scrape config with alerting rules
- **Alertmanager config** (`grafana/alertmanager.yml`) — routes Alertmanager alerts back through gpu-monitor webhook to all 19 channels
- **PagerDuty** — 20th notification channel; Events API v2 via `PAGERDUTY_INTEGRATION_KEY`
- **OpenTelemetry OTLP HTTP** — `OTEL_EXPORTER_OTLP_ENDPOINT` exports all 11 GPU metrics as OTLP/JSON gauges to any OTel-compatible backend (Grafana, Honeycomb, Lightstep, OTLP Collector, etc.)
- **Datadog DogStatsD** — `DATADOG_STATSD_HOST`/`DATADOG_STATSD_PORT`; sends all 9 GPU metrics as gauges with gpu/host/gpu_name tags via UDP
- **`--watch [SECS]`** — live color terminal table refreshing every SECS (default 2); shows util, memory, temperature, power, fan, and processes with ANSI colors
- **InfluxDB line protocol export** — `INFLUXDB_URL`/`INFLUXDB_TOKEN`/`INFLUXDB_BUCKET`/`INFLUXDB_ORG`; supports both v1 and v2 endpoints; writes all 9 GPU metrics per check
- **Web dashboard sparklines** — `/api/history` endpoint + SVG sparklines on each GPU card showing utilization over the last hour

### Fixed
- `monitor()` startup log now lists all 19 configured channels (was missing 9 new channels)
- Non-blocking notifications: `notify()` now dispatches in a background daemon thread
- `_update_index` dead branch (`if False`) — was silently skipping GitHub Pages index updates
- SMS truncation: `"…"` (UCS-2) → `"..."` (ASCII, GSM-7 safe, 157 char limit)
- Power/clock query: split into optional second `nvidia-smi` call with graceful fallback for older drivers
- Prometheus label sanitization: escape `\`, `"`, `\n` in GPU names/hostnames
- `import pwd` guard: moved inside `_pid_username()` to avoid crash on non-Linux platforms
- Email `To` header: comma-space separator (was missing space)
- GitHub Pages push throttled to max once per 5 minutes (was every 60s)

## [0.2.0] — 2026-02-15

### Added
- Multi-channel notifications: Discord, Telegram, Email, SMS, iMessage, WeCom, Feishu, DingTalk, Bark
- Per-machine auto-assigned color in Slack/Discord
- Periodic status reports (active: every 10 min, idle: every 30 min)
- Startup notification
- Uptime tracking (`up 2h30m` / `idle 15min`)
- Watchdog auto-restart
- Log rotation (5 MB × 3 backups)
- `--once` flag for one-shot status check

## [0.1.0] — 2026-01-20

### Added
- Initial release: NVIDIA GPU utilization monitoring via `nvidia-smi`
- Slack webhook notifications
- Idle alert (configurable threshold + duration)
- Recovery alert
- Configurable via environment variables

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

# Changelog

## [0.3.0] — 2026-03-07

### Added
- **15 notification channels**: ntfy, Gotify, Pushover, Microsoft Teams, OpenClaw added (joins Slack, Discord, Telegram, Email, SMS, iMessage, WeCom, Feishu, DingTalk, Bark)
- **`--test-notify` CLI flag** — sends a test message to all configured channels, prints active/inactive channel list
- **Prometheus `/metrics` endpoint** — expose GPU stats for Grafana/alertmanager (set `WEB_PORT`)
- **Power draw monitoring** — watts per GPU in status messages (thermal throttle detection)
- **GPU clock speed** — SM clock MHz shown in status and dashboard
- **Username per process** — shows who owns each GPU via `/proc` UID lookup
- **Process crash detection** — PID-based tracking, instant alert when training processes vanish
- **GitHub Pages multi-machine dashboard** — push stats to a repo, view all machines side-by-side
- **`pyproject.toml`** — installable via `pip install gpu-monitor`
- **`CITATION.cff`** — BibTeX/Zotero citation support
- **Partial idle detection** — warning when some GPUs idle while others are busy

### Fixed
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

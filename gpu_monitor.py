#!/usr/bin/env python3
"""
Lightweight GPU Monitor with multi-channel notifications and web dashboard.

Supported notification channels (configure via environment variables):
  Slack, Discord, Telegram, Email (SMTP), SMS (Twilio), iMessage (macOS only),
  WeCom (企业微信), Feishu (飞书), DingTalk (钉钉), Bark (iOS push),
  ntfy (self-hosted or ntfy.sh), Gotify (self-hosted), Pushover, Microsoft Teams, Mattermost,
  Google Chat, Zulip, Rocket.Chat, Apprise (optional — 80+ extra services via pip install apprise),
  OpenClaw (routes to WhatsApp, Teams, Signal, LINE, Mattermost, Matrix, Zalo, etc.)

Web dashboard:
  Set WEB_PORT=8080 (or any port) to enable the real-time GPU dashboard.
  Then open http://localhost:8080 in your browser.
"""

__version__ = "0.3.0"

import argparse
import base64
import hashlib
import http.server
import json
import logging
import logging.handlers
import os
import re
import signal
import smtplib
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from email.mime.text import MIMEText

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
_log_file = os.environ.get("LOG_FILE", "")
_handlers: list[logging.Handler] = [logging.StreamHandler()]
if _log_file:
    _handlers.append(
        logging.handlers.RotatingFileHandler(_log_file, maxBytes=5 * 1024 * 1024, backupCount=3)
    )
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=_handlers,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config — general
# ---------------------------------------------------------------------------
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "60"))
IDLE_THRESHOLD = int(os.environ.get("IDLE_THRESHOLD", "10"))
IDLE_MINUTES   = int(os.environ.get("IDLE_MINUTES",   "5"))
ALERT_COOLDOWN = int(os.environ.get("ALERT_COOLDOWN", "30"))
STATUS_ACTIVE  = int(os.environ.get("STATUS_ACTIVE",  "10"))
STATUS_IDLE    = int(os.environ.get("STATUS_IDLE",    "30"))
WEB_PORT       = int(os.environ.get("WEB_PORT",       "0"))   # 0 = disabled

HOSTNAME = socket.gethostname().split(".")[0] or "unknown"

_COLORS = ["#2eb886", "#e01e5a", "#36c5f0", "#ecb22e", "#6c5ce7", "#e17055", "#00b894", "#fd79a8"]
MACHINE_COLOR = os.environ.get(
    "MACHINE_COLOR",
    _COLORS[int(hashlib.md5(HOSTNAME.encode()).hexdigest(), 16) % len(_COLORS)],
)

# ---------------------------------------------------------------------------
# Config — notification channels
# ---------------------------------------------------------------------------
SLACK_WEBHOOK_URL    = os.environ.get("SLACK_WEBHOOK_URL",    "")
DISCORD_WEBHOOK_URL  = os.environ.get("DISCORD_WEBHOOK_URL",  "")
TELEGRAM_BOT_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN",   "")
TELEGRAM_CHAT_ID     = os.environ.get("TELEGRAM_CHAT_ID",     "")
EMAIL_SMTP_HOST      = os.environ.get("EMAIL_SMTP_HOST",      "")
EMAIL_SMTP_PORT      = int(os.environ.get("EMAIL_SMTP_PORT",  "587"))
EMAIL_USER           = os.environ.get("EMAIL_USER",           "")
EMAIL_PASS           = os.environ.get("EMAIL_PASS",           "")
EMAIL_TO             = os.environ.get("EMAIL_TO",             "")   # comma-separated
TWILIO_ACCOUNT_SID   = os.environ.get("TWILIO_ACCOUNT_SID",   "")
TWILIO_AUTH_TOKEN    = os.environ.get("TWILIO_AUTH_TOKEN",    "")
TWILIO_FROM          = os.environ.get("TWILIO_FROM",          "")
TWILIO_TO            = os.environ.get("TWILIO_TO",            "")   # comma-separated
IMESSAGE_TO          = os.environ.get("IMESSAGE_TO",          "")   # comma-separated
WECOM_WEBHOOK_URL    = os.environ.get("WECOM_WEBHOOK_URL",    "")  # 企业微信
FEISHU_WEBHOOK_URL   = os.environ.get("FEISHU_WEBHOOK_URL",   "")  # 飞书
DINGTALK_WEBHOOK_URL = os.environ.get("DINGTALK_WEBHOOK_URL", "")  # 钉钉
BARK_URL             = os.environ.get("BARK_URL",             "")  # e.g. https://api.day.app/YOUR_KEY
OPENCLAW_WEBHOOK_URL    = os.environ.get("OPENCLAW_WEBHOOK_URL",    "")  # e.g. http://localhost:18789/hooks/wake
OPENCLAW_WEBHOOK_SECRET = os.environ.get("OPENCLAW_WEBHOOK_SECRET", "")  # Bearer token for auth
NTFY_URL   = os.environ.get("NTFY_URL",   "")  # e.g. https://ntfy.sh/your-topic (or self-hosted)
NTFY_TOKEN = os.environ.get("NTFY_TOKEN", "")  # optional auth token
GOTIFY_URL   = os.environ.get("GOTIFY_URL",   "")  # e.g. http://gotify.example.com
GOTIFY_TOKEN = os.environ.get("GOTIFY_TOKEN", "")  # app token from Gotify
PUSHOVER_TOKEN   = os.environ.get("PUSHOVER_TOKEN",   "")  # app token from pushover.net
PUSHOVER_USER    = os.environ.get("PUSHOVER_USER",    "")  # user/group key
TEAMS_WEBHOOK_URL      = os.environ.get("TEAMS_WEBHOOK_URL",      "")  # Microsoft Teams incoming webhook URL
MATTERMOST_WEBHOOK_URL = os.environ.get("MATTERMOST_WEBHOOK_URL", "")  # Mattermost incoming webhook URL
GOOGLE_CHAT_WEBHOOK_URL = os.environ.get("GOOGLE_CHAT_WEBHOOK_URL", "")  # Google Chat space webhook URL
ZULIP_SITE     = os.environ.get("ZULIP_SITE",     "")  # e.g. https://yourorg.zulipchat.com
ZULIP_EMAIL    = os.environ.get("ZULIP_EMAIL",    "")  # bot email
ZULIP_API_KEY  = os.environ.get("ZULIP_API_KEY",  "")  # bot API key
ZULIP_STREAM   = os.environ.get("ZULIP_STREAM",   "general")
ZULIP_TOPIC    = os.environ.get("ZULIP_TOPIC",    "GPU Monitor")
ROCKETCHAT_WEBHOOK_URL = os.environ.get("ROCKETCHAT_WEBHOOK_URL", "")  # Rocket.Chat incoming webhook URL
# Apprise — optional, requires: pip install apprise
# Set APPRISE_URLS to a space/comma-separated list of Apprise-format URLs
# Examples: "slack://token/channel", "tgram://bot_token/chat_id", "json://your-host/"
APPRISE_URLS = os.environ.get("APPRISE_URLS", "")  # space or comma-separated Apprise URLs
# Memory leak detection
MEMLEAK_THRESHOLD = int(os.environ.get("MEMLEAK_THRESHOLD", "30"))  # % growth to trigger alert
MEMLEAK_MINUTES   = int(os.environ.get("MEMLEAK_MINUTES",   "10"))  # window to check
# Temperature alerting (0 = disabled)
GPU_TEMP_WARN = int(os.environ.get("GPU_TEMP_WARN", "85"))  # °C — warning alert
GPU_TEMP_CRIT = int(os.environ.get("GPU_TEMP_CRIT", "92"))  # °C — critical alert
# Generic alert webhook — receives a POST with JSON body for every alert
ALERT_WEBHOOK_URL = os.environ.get("ALERT_WEBHOOK_URL", "")
# InfluxDB — write GPU metrics in line protocol format
INFLUXDB_URL    = os.environ.get("INFLUXDB_URL",    "")  # e.g. http://influxdb:8086
INFLUXDB_TOKEN  = os.environ.get("INFLUXDB_TOKEN",  "")  # API token (v2) or "user:pass" (v1)
INFLUXDB_BUCKET = os.environ.get("INFLUXDB_BUCKET", "gpu_metrics")  # v2 bucket or "db/rp"
INFLUXDB_ORG    = os.environ.get("INFLUXDB_ORG",    "")  # v2 org name
# PagerDuty Events API v2 — on-call alerting
PAGERDUTY_INTEGRATION_KEY = os.environ.get("PAGERDUTY_INTEGRATION_KEY", "")  # 32-char routing key
# Datadog DogStatsD — send GPU metrics to Datadog agent
DATADOG_STATSD_HOST = os.environ.get("DATADOG_STATSD_HOST", "")  # e.g. localhost or datadog-agent
DATADOG_STATSD_PORT = int(os.environ.get("DATADOG_STATSD_PORT", "8125"))

# GitHub Pages dashboard (optional)
GITHUB_PAGES_TOKEN = os.environ.get("GITHUB_PAGES_TOKEN", "")
GITHUB_PAGES_REPO  = os.environ.get("GITHUB_PAGES_REPO",  "")  # e.g. owner/repo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe_int(s: str) -> int | None:
    """Parse int from nvidia-smi output that may contain '[N/A]'."""
    try:
        return int(float(s.strip()))
    except (ValueError, AttributeError):
        return None


def _safe_float(s: str) -> float | None:
    try:
        return round(float(s.strip()), 1)
    except (ValueError, AttributeError):
        return None


def _pid_username(pid: str) -> str:
    """Resolve process owner username from /proc (Linux only)."""
    try:
        import pwd as _pwd
        uid = os.stat(f"/proc/{pid}").st_uid
        return _pwd.getpwuid(uid).pw_name
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# GPU queries
# ---------------------------------------------------------------------------
def get_gpu_stats() -> list[dict]:
    try:
        # Core query — always attempted
        r = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return []
        gpus = []
        for line in r.stdout.strip().split("\n"):
            if not line.strip():
                continue
            p = [x.strip() for x in line.split(",")]
            if len(p) < 6:
                continue
            idx  = _safe_int(p[0])
            util = _safe_int(p[2])
            mem_used  = _safe_int(p[3])
            mem_total = _safe_int(p[4])
            temp = _safe_int(p[5])
            if None in (idx, util, mem_used, mem_total, temp):
                logger.debug(f"Skipping malformed nvidia-smi line: {line!r}")
                continue
            gpus.append({
                "idx": idx, "name": p[1], "util": util,
                "mem_used": mem_used, "mem_total": mem_total, "temp": temp,
                "power_w":      None,
                "clock_mhz":    None,
                "fan_speed":     None,
                "power_limit_w": None,
                "ecc_errors":    None,
            })

        # Optional query — power, clock, fan, power limit; skip silently if not supported
        try:
            r2 = subprocess.run(
                ["nvidia-smi",
                 "--query-gpu=index,power.draw,clocks.sm,fan.speed,enforced.power.limit",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10,
            )
            if r2.returncode == 0:
                idx_map = {g["idx"]: g for g in gpus}
                for line in r2.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    p = [x.strip() for x in line.split(",")]
                    if len(p) < 5:
                        continue
                    idx = _safe_int(p[0])
                    if idx is not None and idx in idx_map:
                        idx_map[idx]["power_w"]      = _safe_float(p[1])
                        idx_map[idx]["clock_mhz"]    = _safe_int(p[2])
                        idx_map[idx]["fan_speed"]     = _safe_int(p[3])
                        idx_map[idx]["power_limit_w"] = _safe_float(p[4])
        except Exception as e:
            logger.debug(f"Optional power/clock/fan query failed (skipping): {e}")

        # Optional ECC query — only available on Tesla/data-center GPUs (A100, H100, V100, etc.)
        try:
            r3 = subprocess.run(
                ["nvidia-smi",
                 "--query-gpu=index,ecc.errors.uncorrected.volatile.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10,
            )
            if r3.returncode == 0:
                idx_map = {g["idx"]: g for g in gpus}
                for line in r3.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    p = [x.strip() for x in line.split(",")]
                    if len(p) >= 2:
                        idx = _safe_int(p[0])
                        if idx is not None and idx in idx_map:
                            idx_map[idx]["ecc_errors"] = _safe_int(p[1])
        except Exception as e:
            logger.debug(f"Optional ECC query failed (skipping): {e}")

        return gpus
    except Exception as e:
        logger.debug(f"get_gpu_stats failed: {e}")
        return []


def get_gpu_processes() -> dict[int, list[dict]]:
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        r2 = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,uuid", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0 or r2.returncode != 0:
            return {}
        uuid_map: dict[str, int] = {}
        for line in r2.stdout.strip().split("\n"):
            parts = [x.strip() for x in line.split(",")]
            if len(parts) >= 2:
                uuid_map[parts[1]] = int(parts[0])
        procs: dict[int, list[dict]] = {}
        if not r.stdout.strip():
            return procs
        for line in r.stdout.strip().split("\n"):
            p = [x.strip() for x in line.split(",")]
            if len(p) >= 4:
                idx = uuid_map.get(p[0], -1)
                if idx >= 0:
                    procs.setdefault(idx, []).append({
                        "pid":  p[1],
                        "name": p[2].split("/")[-1],
                        "mem":  p[3],
                        "user": _pid_username(p[1]),
                    })
        return procs
    except Exception as e:
        logger.debug(f"get_gpu_processes failed: {e}")
        return {}


# ---------------------------------------------------------------------------
# Message formatting
# ---------------------------------------------------------------------------
_SLACK_EMOJI = {
    ":rotating_light:": "🚨",
    ":white_check_mark:": "✅",
    ":rocket:": "🚀",
    ":eyes:": "👀",
    ":x:": "❌",
}
_RE_BOLD   = re.compile(r"\*([^*]+)\*")
_RE_CODE   = re.compile(r"`([^`]+)`")
_RE_ITALIC = re.compile(r"_([^_]+)_")


def _to_plain(text: str) -> str:
    """Convert Slack-formatted text to plain text with Unicode emoji."""
    for code, uni in _SLACK_EMOJI.items():
        text = text.replace(code, uni)
    text = _RE_BOLD.sub(r"\1", text)
    text = _RE_CODE.sub(r"\1", text)
    text = _RE_ITALIC.sub(r"\1", text)
    return text


def _cooldown_ok(last_alert_time: float | None, now: float) -> bool:
    """True if enough time has passed since the last alert (or no alert yet)."""
    return last_alert_time is None or (now - last_alert_time) / 60 >= ALERT_COOLDOWN


def _hex_to_int(color: str) -> int:
    """Convert '#rrggbb' to Discord decimal color integer."""
    try:
        return int(color.lstrip("#"), 16)
    except (ValueError, AttributeError):
        return 0


def format_status(gpus: list[dict], procs: dict | None = None) -> str:
    """Slack-formatted GPU status."""
    if not gpus:
        return ":x: Cannot read GPU status"
    now       = datetime.now().strftime("%m-%d %H:%M")
    total_mem = sum(g["mem_total"] for g in gpus)
    used_mem  = sum(g["mem_used"]  for g in gpus)
    mem_pct   = used_mem / total_mem * 100 if total_mem else 0
    avg_util  = sum(g["util"] for g in gpus) / len(gpus)
    avg_temp  = sum(g["temp"] for g in gpus) / len(gpus)
    util_parts = " ".join(f"{g['idx']}:{g['util']}%" for g in gpus)
    # Optional power summary
    powers = [g["power_w"] for g in gpus if g.get("power_w") is not None]
    power_str = f" | {sum(powers):.0f}W" if powers else ""
    lines = [
        f"`{HOSTNAME}` | {now} | avg *{avg_util:.0f}%* | "
        f"{avg_temp:.0f}C{power_str} | mem {used_mem // 1024}G/{total_mem // 1024}G ({mem_pct:.0f}%)",
        f"`{util_parts}`",
    ]
    if procs:
        proc_parts = [
            f"GPU{idx}: " + ", ".join(
                f"{p['name']}({p['mem']}M)" + (f"[{p['user']}]" if p.get("user") else "")
                for p in plist
            )
            for idx, plist in sorted(procs.items())
        ]
        lines.append("_" + " | ".join(proc_parts) + "_")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Notification senders
# ---------------------------------------------------------------------------
def _post_json(url: str, payload: dict, ok_statuses: tuple = (200,), label: str = "") -> bool:
    """POST JSON payload; returns True if response status is in ok_statuses."""
    try:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in ok_statuses
    except Exception as e:
        logger.error(f"{label} error: {e}")
        return False


def send_slack(text: str, color: str = "") -> bool:
    if not SLACK_WEBHOOK_URL:
        return False
    payload = {"attachments": [{"color": color or MACHINE_COLOR, "text": text, "mrkdwn_in": ["text"]}]}
    return _post_json(SLACK_WEBHOOK_URL, payload, label="Slack")


def send_discord(plain_text: str, color: str = "") -> bool:
    if not DISCORD_WEBHOOK_URL:
        return False
    payload = {"embeds": [{"description": plain_text, "color": _hex_to_int(color or MACHINE_COLOR)}]}
    return _post_json(DISCORD_WEBHOOK_URL, payload, ok_statuses=(200, 204), label="Discord")


def send_telegram(plain_text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    return _post_json(url, {"chat_id": TELEGRAM_CHAT_ID, "text": plain_text}, label="Telegram")


def send_email(plain_text: str) -> bool:
    if not all([EMAIL_SMTP_HOST, EMAIL_USER, EMAIL_PASS, EMAIL_TO]):
        return False
    lines = plain_text.strip().splitlines()
    subject = lines[0].strip() if lines else "GPU Monitor Alert"
    try:
        msg = MIMEText(plain_text, "plain")
        recipients = [a.strip() for a in EMAIL_TO.split(",") if a.strip()]
        msg["Subject"] = subject
        msg["From"]    = EMAIL_USER
        msg["To"]      = ", ".join(recipients)
        with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, timeout=15) as s:
            s.starttls()
            s.login(EMAIL_USER, EMAIL_PASS)
            s.sendmail(EMAIL_USER, recipients, msg.as_string())
        return True
    except Exception as e:
        logger.error(f"Email error: {e}")
        return False


def send_sms(plain_text: str) -> bool:
    """Send SMS via Twilio REST API (no SDK required)."""
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM, TWILIO_TO]):
        return False
    url   = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    creds = base64.b64encode(f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}".encode()).decode()
    body  = (plain_text[:157] + "...") if len(plain_text) > 160 else plain_text
    ok = True
    for to in TWILIO_TO.split(","):
        to = to.strip()
        if not to:
            continue
        data = urllib.parse.urlencode({"From": TWILIO_FROM, "To": to, "Body": body}).encode()
        try:
            req = urllib.request.Request(
                url, data=data,
                headers={"Authorization": f"Basic {creds}",
                         "Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                ok = ok and resp.status == 201
        except Exception as e:
            logger.error(f"SMS error ({to}): {e}")
            ok = False
    return ok


def send_imessage(plain_text: str) -> bool:
    """Send iMessage via osascript (macOS only).

    Text is passed as a script argument (on run argv) rather than embedded
    in the script body, preventing AppleScript injection via message content.
    """
    if not IMESSAGE_TO:
        return False
    if sys.platform != "darwin":
        logger.debug("iMessage skipped: not macOS")
        return False
    script = (
        "on run argv\n"
        "  tell application \"Messages\"\n"
        "    set tgt to buddy (item 2 of argv) of (service 1 whose service type is iMessage)\n"
        "    send (item 1 of argv) to tgt\n"
        "  end tell\n"
        "end run"
    )
    ok = True
    for recipient in IMESSAGE_TO.split(","):
        recipient = recipient.strip()
        if not recipient:
            continue
        try:
            r = subprocess.run(
                ["osascript", "-e", script, plain_text, recipient],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode != 0:
                logger.error(f"iMessage error ({recipient}): {r.stderr.strip()}")
                ok = False
        except Exception as e:
            logger.error(f"iMessage error ({recipient}): {e}")
            ok = False
    return ok


def send_wecom(plain_text: str) -> bool:
    """Send via 企业微信 (WeCom) group bot webhook."""
    if not WECOM_WEBHOOK_URL:
        return False
    payload = {"msgtype": "text", "text": {"content": plain_text}}
    return _post_json(WECOM_WEBHOOK_URL, payload, ok_statuses=(200,), label="WeCom")


def send_feishu(plain_text: str) -> bool:
    """Send via 飞书 (Feishu/Lark) bot webhook."""
    if not FEISHU_WEBHOOK_URL:
        return False
    payload = {"msg_type": "text", "content": {"text": plain_text}}
    return _post_json(FEISHU_WEBHOOK_URL, payload, ok_statuses=(200,), label="Feishu")


def send_dingtalk(plain_text: str) -> bool:
    """Send via 钉钉 (DingTalk) group robot webhook."""
    if not DINGTALK_WEBHOOK_URL:
        return False
    payload = {
        "msgtype": "text",
        "text": {"content": plain_text},
        "at": {"isAtAll": False},
    }
    return _post_json(DINGTALK_WEBHOOK_URL, payload, ok_statuses=(200,), label="DingTalk")


def send_bark(plain_text: str) -> bool:
    """Send iOS push via Bark (https://github.com/Finb/Bark)."""
    if not BARK_URL:
        return False
    lines = plain_text.strip().splitlines()
    title = lines[0][:64] if lines else "GPU Monitor"
    body  = "\n".join(lines[1:])[:256] if len(lines) > 1 else plain_text[:256]
    url   = BARK_URL.rstrip("/") + "/" + urllib.parse.quote(title, safe="") + "/" + urllib.parse.quote(body, safe="")
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        logger.error(f"Bark error: {e}")
        return False


def send_apprise(plain_text: str) -> bool:
    """Send via Apprise (https://github.com/caronc/apprise) — 80+ notification services.

    Optional: requires `pip install apprise`. If not installed, silently skipped.
    Set APPRISE_URLS to a space/comma-separated list of Apprise-format URLs.
    Examples:
      APPRISE_URLS="slack://token/channel tgram://bot_token/chat_id"
    Docs: https://github.com/caronc/apprise/wiki
    """
    if not APPRISE_URLS:
        return False
    try:
        import apprise  # type: ignore[import]
    except ImportError:
        logger.debug("Apprise not installed — skipping (pip install apprise to enable)")
        return False
    try:
        lines = plain_text.strip().splitlines()
        title = lines[0] if lines else "GPU Monitor"
        body  = "\n".join(lines[1:]) if len(lines) > 1 else plain_text
        ap = apprise.Apprise()
        for url in re.split(r"[,\s]+", APPRISE_URLS.strip()):
            if url:
                ap.add(url)
        return ap.notify(body=body, title=title)
    except Exception as e:
        logger.error(f"Apprise error: {e}")
        return False


def send_rocketchat(plain_text: str) -> bool:
    """Send via Rocket.Chat incoming webhook.

    Create a webhook in Rocket.Chat: Administration → Integrations → New Integration → Incoming WebHook.
    Docs: https://docs.rocket.chat/use-rocket.chat/workspace-administration/integrations
    """
    if not ROCKETCHAT_WEBHOOK_URL:
        return False
    return _post_json(ROCKETCHAT_WEBHOOK_URL, {"text": plain_text}, label="Rocket.Chat")


def send_google_chat(plain_text: str) -> bool:
    """Send via Google Chat space webhook.

    Create a webhook: Space → Manage webhooks.
    Docs: https://developers.google.com/chat/how-tos/webhooks
    """
    if not GOOGLE_CHAT_WEBHOOK_URL:
        return False
    return _post_json(GOOGLE_CHAT_WEBHOOK_URL, {"text": plain_text}, label="Google Chat")


def send_zulip(plain_text: str) -> bool:
    """Send via Zulip bot API (https://zulip.com).

    Create a bot in Zulip: Settings → Your bots → Add a new bot (Incoming webhook).
    Docs: https://zulip.com/api/send-message
    """
    if not all([ZULIP_SITE, ZULIP_EMAIL, ZULIP_API_KEY]):
        return False
    url  = ZULIP_SITE.rstrip("/") + "/api/v1/messages"
    creds = base64.b64encode(f"{ZULIP_EMAIL}:{ZULIP_API_KEY}".encode()).decode()
    data = urllib.parse.urlencode({
        "type":    "stream",
        "to":      ZULIP_STREAM,
        "topic":   ZULIP_TOPIC,
        "content": plain_text,
    }).encode()
    try:
        req = urllib.request.Request(
            url, data=data,
            headers={
                "Authorization": f"Basic {creds}",
                "Content-Type":  "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        logger.error(f"Zulip error: {e}")
        return False


def send_mattermost(plain_text: str) -> bool:
    """Send via Mattermost incoming webhook (same payload format as Slack).

    Create a webhook in Mattermost: Main Menu → Integrations → Incoming Webhooks.
    Docs: https://developers.mattermost.com/integrate/webhooks/incoming/
    """
    if not MATTERMOST_WEBHOOK_URL:
        return False
    return _post_json(MATTERMOST_WEBHOOK_URL, {"text": plain_text}, label="Mattermost")


def send_teams(plain_text: str) -> bool:
    """Send via Microsoft Teams incoming webhook (Adaptive Card format).

    Create a webhook: Teams channel → ⋯ → Connectors → Incoming Webhook.
    Docs: https://learn.microsoft.com/en-us/microsoftteams/platform/webhooks-and-connectors/how-to/add-incoming-webhook
    """
    if not TEAMS_WEBHOOK_URL:
        return False
    lines = plain_text.strip().splitlines()
    title = lines[0] if lines else "GPU Monitor"
    body  = "\n\n".join(lines[1:]) if len(lines) > 1 else plain_text
    # Adaptive Card 1.4 (supported by Teams)
    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.4",
                "body": [
                    {"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Medium", "wrap": True},
                    {"type": "TextBlock", "text": body,  "wrap": True, "spacing": "Small"},
                ],
            },
        }],
    }
    return _post_json(TEAMS_WEBHOOK_URL, payload, ok_statuses=(200, 202), label="Teams")


def send_pushover(plain_text: str) -> bool:
    """Send via Pushover (https://pushover.net) — iOS/Android push notifications."""
    if not PUSHOVER_TOKEN or not PUSHOVER_USER:
        return False
    lines = plain_text.strip().splitlines()
    title = lines[0][:250] if lines else "GPU Monitor"
    data = urllib.parse.urlencode({
        "token":   PUSHOVER_TOKEN,
        "user":    PUSHOVER_USER,
        "title":   title,
        "message": plain_text[:1024],
    }).encode()
    try:
        req = urllib.request.Request(
            "https://api.pushover.net/1/messages.json",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        logger.error(f"Pushover error: {e}")
        return False


def send_gotify(plain_text: str) -> bool:
    """Send via Gotify (self-hosted push notification server).

    Docs: https://gotify.net/api-docs
    """
    if not GOTIFY_URL or not GOTIFY_TOKEN:
        return False
    lines = plain_text.strip().splitlines()
    title = lines[0][:100] if lines else "GPU Monitor"
    url = GOTIFY_URL.rstrip("/") + "/message"
    payload = {"title": title, "message": plain_text, "priority": 5}
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Gotify-Key": GOTIFY_TOKEN,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        logger.error(f"Gotify error: {e}")
        return False


def send_ntfy(plain_text: str) -> bool:
    """Send via ntfy.sh (or self-hosted ntfy server).

    Set NTFY_URL to your topic URL, e.g. https://ntfy.sh/my-gpu-alerts
    Docs: https://docs.ntfy.sh/publish/
    """
    if not NTFY_URL:
        return False
    lines = plain_text.strip().splitlines()
    title = lines[0][:100] if lines else "GPU Monitor"
    headers = {
        "Title": title,
        "Content-Type": "text/plain; charset=utf-8",
    }
    if NTFY_TOKEN:
        headers["Authorization"] = f"Bearer {NTFY_TOKEN}"
    try:
        req = urllib.request.Request(
            NTFY_URL,
            data=plain_text.encode(),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        logger.error(f"ntfy error: {e}")
        return False


def send_openclaw(plain_text: str) -> bool:
    """Send via OpenClaw webhook (https://openclaw.ai).

    OpenClaw is a self-hosted AI assistant that routes messages to whichever
    chat channel the user configured: WhatsApp, Telegram, Slack, Discord,
    Teams, Signal, iMessage, LINE, Mattermost, Matrix, Zalo, and more.
    """
    if not OPENCLAW_WEBHOOK_URL:
        return False
    headers = {"Content-Type": "application/json"}
    if OPENCLAW_WEBHOOK_SECRET:
        headers["Authorization"] = f"Bearer {OPENCLAW_WEBHOOK_SECRET}"
    try:
        req = urllib.request.Request(
            OPENCLAW_WEBHOOK_URL,
            data=json.dumps({"text": plain_text, "mode": "now"}).encode(),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 204)
    except Exception as e:
        logger.error(f"OpenClaw error: {e}")
        return False


def send_pagerduty(plain_text: str) -> bool:
    """Send alert to PagerDuty via Events API v2."""
    if not PAGERDUTY_INTEGRATION_KEY:
        return False
    payload = {
        "routing_key":  PAGERDUTY_INTEGRATION_KEY,
        "event_action": "trigger",
        "payload": {
            "summary":  plain_text[:1024],
            "severity": "warning",
            "source":   HOSTNAME,
            "custom_details": {"host": HOSTNAME},
        },
    }
    return _post_json(
        "https://events.pagerduty.com/v2/enqueue",
        payload,
        ok_statuses=(200, 202),
        label="PagerDuty",
    )


def push_datadog(gpus: list[dict]) -> None:
    """Send GPU metrics to Datadog via DogStatsD (UDP)."""
    if not DATADOG_STATSD_HOST:
        return
    try:
        import socket as _sock
        sock = _sock.socket(_sock.AF_INET, _sock.SOCK_DGRAM)
        h_tag = f"host:{HOSTNAME}"
        for g in gpus:
            name_tag = f"gpu_name:{g['name'].replace(' ', '_')}"
            tags = f"gpu:{g['idx']},{name_tag},{h_tag}"
            mp = round(g["mem_used"] / g["mem_total"] * 100, 1) if g["mem_total"] else 0
            metrics: dict[str, float | int] = {
                "gpu.utilization":         g["util"],
                "gpu.memory.used_mib":     g["mem_used"],
                "gpu.memory.total_mib":    g["mem_total"],
                "gpu.memory.utilization":  mp,
                "gpu.temperature":         g["temp"],
            }
            if g.get("power_w")      is not None: metrics["gpu.power_w"]    = g["power_w"]
            if g.get("fan_speed")    is not None: metrics["gpu.fan_speed"]  = g["fan_speed"]
            if g.get("clock_mhz")    is not None: metrics["gpu.clock_mhz"]  = g["clock_mhz"]
            if g.get("ecc_errors")   is not None: metrics["gpu.ecc_errors"] = g["ecc_errors"]
            for name, val in metrics.items():
                msg = f"{name}:{val}|g|#{tags}".encode()
                sock.sendto(msg, (DATADOG_STATSD_HOST, DATADOG_STATSD_PORT))
        sock.close()
    except Exception as e:
        logger.warning(f"Datadog StatsD failed: {e}")


def push_influxdb(gpus: list[dict]) -> None:
    """Write GPU metrics to InfluxDB in line protocol format (v1 and v2 compatible)."""
    if not INFLUXDB_URL:
        return
    try:
        ts_ns = int(time.time() * 1e9)
        h = HOSTNAME.replace(" ", "\\ ")
        lines = []
        for g in gpus:
            name_tag = g["name"].replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")
            tags = f'gpu={g["idx"]},host={h},name={name_tag}'
            fields: list[str] = [
                f"utilization={g['util']}",
                f"mem_used={g['mem_used']}",
                f"mem_total={g['mem_total']}",
                f"temperature={g['temp']}",
            ]
            if g.get("power_w")      is not None: fields.append(f"power_w={g['power_w']}")
            if g.get("power_limit_w") is not None: fields.append(f"power_limit_w={g['power_limit_w']}")
            if g.get("clock_mhz")    is not None: fields.append(f"clock_mhz={g['clock_mhz']}")
            if g.get("fan_speed")    is not None: fields.append(f"fan_speed={g['fan_speed']}")
            if g.get("ecc_errors")   is not None: fields.append(f"ecc_errors={g['ecc_errors']}")
            lines.append(f"gpu_metrics,{tags} {','.join(fields)} {ts_ns}")
        body = "\n".join(lines).encode()

        # Support both InfluxDB v1 (/write) and v2 (/api/v2/write)
        if "/api/v2" in INFLUXDB_URL or INFLUXDB_ORG:
            url = INFLUXDB_URL.rstrip("/") + f"/api/v2/write?bucket={urllib.parse.quote(INFLUXDB_BUCKET)}&org={urllib.parse.quote(INFLUXDB_ORG)}&precision=ns"
            headers = {"Authorization": f"Token {INFLUXDB_TOKEN}", "Content-Type": "text/plain; charset=utf-8"}
        else:
            db, _, rp = INFLUXDB_BUCKET.partition("/")
            url = INFLUXDB_URL.rstrip("/") + f"/write?db={urllib.parse.quote(db)}" + (f"&rp={urllib.parse.quote(rp)}" if rp else "") + "&precision=ns"
            headers = {"Content-Type": "text/plain; charset=utf-8"}
            if INFLUXDB_TOKEN and ":" in INFLUXDB_TOKEN:
                import base64 as _b64
                headers["Authorization"] = "Basic " + _b64.b64encode(INFLUXDB_TOKEN.encode()).decode()
            elif INFLUXDB_TOKEN:
                headers["Authorization"] = f"Token {INFLUXDB_TOKEN}"

        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status not in (200, 204):
                logger.warning(f"InfluxDB write returned {resp.status}")
    except Exception as e:
        logger.warning(f"InfluxDB write failed: {e}")


def notify(slack_text: str, color: str = "") -> None:
    """Dispatch to all configured notification channels in a background thread."""
    def _dispatch() -> None:
        try:
            plain = _to_plain(slack_text)
            send_slack(slack_text, color)
            send_discord(plain, color)
            send_telegram(plain)
            send_email(plain)
            send_sms(plain)
            send_imessage(plain)
            send_wecom(plain)
            send_feishu(plain)
            send_dingtalk(plain)
            send_bark(plain)
            send_apprise(plain)
            send_rocketchat(plain)
            send_google_chat(plain)
            send_zulip(plain)
            send_mattermost(plain)
            send_teams(plain)
            send_pushover(plain)
            send_gotify(plain)
            send_ntfy(plain)
            send_openclaw(plain)
            send_pagerduty(plain)
            if ALERT_WEBHOOK_URL:
                try:
                    body = json.dumps({
                        "host": HOSTNAME,
                        "text": plain,
                        "color": color,
                        "timestamp": datetime.now().isoformat(timespec="seconds"),
                    }).encode()
                    req = urllib.request.Request(
                        ALERT_WEBHOOK_URL, data=body,
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    urllib.request.urlopen(req, timeout=10)
                except Exception as e:
                    logger.warning(f"ALERT_WEBHOOK_URL failed: {e}")
        except Exception as e:
            logger.error(f"notify dispatch error: {e}")
    threading.Thread(target=_dispatch, daemon=True).start()


# ---------------------------------------------------------------------------
# Prometheus label sanitization
# ---------------------------------------------------------------------------
def _prom_label(s: str) -> str:
    """Escape string for use as a Prometheus label value."""
    return str(s).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')


# ---------------------------------------------------------------------------
# Web dashboard
# ---------------------------------------------------------------------------
# Ring buffer for web dashboard sparklines — updated by monitor() on each check
# {gpu_idx: [[util%, mem%, temp], ...]}  up to _MAX_HISTORY_POINTS entries
_dashboard_history: dict[int, list] = {}
_MAX_HISTORY_POINTS = 60  # 60 × CHECK_INTERVAL seconds (default 1 hour)

_DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GPU Monitor — %%HOST%%</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0b0b12;
  --surface:#12121c;
  --surface2:#18182a;
  --border:rgba(255,255,255,.07);
  --text:#e2e8f0;
  --muted:#4a5568;
  --accent:%%ACCENT%%;
  --green:#22c55e;
  --amber:#f59e0b;
  --red:#ef4444;
  --blue:#60a5fa;
}
body{background:var(--bg);color:var(--text);font-family:ui-monospace,'SF Mono','Cascadia Code',monospace;font-size:13px;min-height:100vh}

/* ── Header ── */
header{
  display:flex;align-items:center;gap:14px;
  padding:12px 20px;
  background:var(--surface);
  border-bottom:1px solid var(--border);
  position:sticky;top:0;z-index:10;
  backdrop-filter:blur(8px);
}
.logo{font-size:14px;font-weight:700;letter-spacing:.04em;color:var(--accent)}
.host-badge{
  background:color-mix(in srgb,var(--accent) 12%,transparent);
  border:1px solid color-mix(in srgb,var(--accent) 30%,transparent);
  color:var(--accent);border-radius:6px;padding:2px 10px;font-size:11px;font-weight:600;
}
.spacer{flex:1}
#live{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--muted)}
.dot{width:7px;height:7px;border-radius:50%;background:var(--green);transition:background .4s}
.dot.offline{background:var(--red)}
#clock{color:var(--muted);font-size:11px;margin-left:8px}

/* ── Grid ── */
main{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px;padding:16px 20px}

/* ── GPU Card ── */
.card{
  background:var(--surface);border:1px solid var(--border);
  border-radius:14px;padding:16px 18px;
  transition:border-color .25s,transform .15s;
}
.card:hover{border-color:rgba(255,255,255,.14);transform:translateY(-1px)}

.card-header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:14px}
.gpu-name{font-weight:600;font-size:12px;color:var(--text);line-height:1.3;max-width:220px}
.gpu-idx{
  background:color-mix(in srgb,var(--accent) 15%,transparent);
  color:var(--accent);
  border:1px solid color-mix(in srgb,var(--accent) 35%,transparent);
  border-radius:6px;padding:2px 8px;font-size:10px;font-weight:700;white-space:nowrap;
}

/* Stat pills row */
.pills{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap}
.pill{
  flex:1;min-width:70px;
  background:var(--surface2);border-radius:10px;padding:8px 10px;text-align:center;
}
.pill-val{font-size:18px;font-weight:700;line-height:1;margin-bottom:3px}
.pill-lbl{font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}

/* Progress bars */
.bar-row{margin-bottom:9px}
.bar-meta{display:flex;justify-content:space-between;margin-bottom:4px;font-size:10px}
.bar-meta .lbl{color:var(--muted)}
.bar-meta .val{color:var(--text);font-weight:600}
.track{height:6px;background:rgba(255,255,255,.06);border-radius:3px;overflow:hidden}
.fill{height:100%;border-radius:3px;transition:width .7s cubic-bezier(.4,0,.2,1),background .5s}

/* Process list */
.procs{margin-top:12px;padding-top:11px;border-top:1px solid var(--border)}
.procs-title{font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin-bottom:7px}
.proc{display:flex;justify-content:space-between;align-items:center;padding:3px 0;gap:8px}
.proc-name{color:var(--text);font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}
.proc-mem{color:var(--muted);font-size:10px;white-space:nowrap}
.no-proc{color:var(--muted);font-size:10px;font-style:italic}

/* Summary bar */
#summary{
  margin:0 20px 4px;padding:10px 16px;
  background:var(--surface);border:1px solid var(--border);border-radius:10px;
  display:flex;gap:24px;align-items:center;flex-wrap:wrap;font-size:11px;
}
.sum-item{display:flex;align-items:center;gap:6px;color:var(--muted)}
.sum-val{font-weight:700;font-size:13px}

/* Sparkline */
.spark-row{display:flex;align-items:center;justify-content:space-between;margin-top:10px;padding-top:10px;border-top:1px solid var(--border)}
.spark-lbl{font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);white-space:nowrap;margin-right:8px}

/* Loading / error */
.loading,.error{
  grid-column:1/-1;display:flex;align-items:center;justify-content:center;
  gap:12px;padding:80px 0;color:var(--muted);font-size:14px;
}
.spinner{width:18px;height:18px;border:2px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.error{color:var(--red)}
</style>
</head>
<body>
<header>
  <span class="logo">◈ gpu-monitor</span>
  <span class="host-badge">%%HOST%%</span>
  <span class="spacer"></span>
  <span id="live"><span class="dot" id="dot"></span><span id="live-txt">connecting…</span></span>
  <span id="clock"></span>
</header>
<div id="summary" style="display:none">
  <span class="sum-item">GPUs <span class="sum-val" id="sum-gpus">—</span></span>
  <span class="sum-item">Avg util <span class="sum-val" id="sum-util">—</span></span>
  <span class="sum-item">Memory <span class="sum-val" id="sum-mem">—</span></span>
  <span class="sum-item">Avg temp <span class="sum-val" id="sum-temp">—</span></span>
  <span class="sum-item" id="sum-procs-wrap">Processes <span class="sum-val" id="sum-procs">—</span></span>
</div>
<main id="grid"><div class="loading"><div class="spinner"></div>Loading…</div></main>
<script>
function utilColor(p){return p<40?'var(--green)':p<70?'var(--amber)':'var(--red)'}
function memColor(p){return p<60?'var(--blue)':p<80?'var(--amber)':'var(--red)'}
function tempColor(t){return t<55?'var(--blue)':t<75?'var(--amber)':'var(--red)'}

function bar(pct,colorFn){
  const p=Math.min(100,Math.max(0,pct));
  return `<div class="track"><div class="fill" style="width:${p}%;background:${colorFn(p)}"></div></div>`;
}

function sparkline(data,colorFn){
  if(!data||data.length<2)return'';
  const vals=data.slice(-40);
  const W=84,H=22;
  const pts=vals.map((v,i)=>{
    const x=(i/(vals.length-1))*W;
    const y=H-(Math.min(v,100)/100)*H;
    return x.toFixed(1)+','+y.toFixed(1);
  }).join(' ');
  const last=vals[vals.length-1];
  const col=colorFn(last);
  const lx=((vals.length-1)/(vals.length-1))*W,ly=H-(Math.min(last,100)/100)*H;
  return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" style="overflow:visible;display:block"><polyline points="${pts}" fill="none" stroke="${col}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.85"/><circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="2.5" fill="${col}"/></svg>`;
}

let _gpuHistory={};

function renderCard(g,procs){
  const mp=g.mem_total?g.mem_used/g.mem_total*100:0;
  const pl=(procs[g.idx]||[]);
  const procsHtml=pl.length
    ?pl.map(p=>`<div class="proc"><span class="proc-name">${esc(p.name)}</span><span class="proc-mem">${p.mem} MiB</span></div>`).join('')
    :'<div class="no-proc">idle</div>';
  const hist=_gpuHistory[String(g.idx)]||[];
  const utilHist=hist.map(h=>h[0]);
  const sparkHtml=utilHist.length>1?`<div class="spark-row"><span class="spark-lbl">Util history (${utilHist.length} pts)</span>${sparkline(utilHist,utilColor)}</div>`:'';
  return `<div class="card">
  <div class="card-header">
    <div class="gpu-name">${esc(g.name)}</div>
    <div class="gpu-idx">GPU ${g.idx}</div>
  </div>
  <div class="pills">
    <div class="pill">
      <div class="pill-val" style="color:${utilColor(g.util)}">${g.util}%</div>
      <div class="pill-lbl">Util</div>
    </div>
    <div class="pill">
      <div class="pill-val" style="color:${memColor(mp)}">${(g.mem_used/1024).toFixed(1)}G</div>
      <div class="pill-lbl">/ ${(g.mem_total/1024).toFixed(0)}G</div>
    </div>
    <div class="pill">
      <div class="pill-val" style="color:${tempColor(g.temp)}">${g.temp}°</div>
      <div class="pill-lbl">Temp</div>
    </div>
  </div>
  <div class="bar-row">
    <div class="bar-meta"><span class="lbl">Utilization</span><span class="val">${g.util}%</span></div>
    ${bar(g.util,utilColor)}
  </div>
  <div class="bar-row">
    <div class="bar-meta"><span class="lbl">Memory</span><span class="val">${mp.toFixed(0)}% · ${(g.mem_used/1024).toFixed(1)}/${(g.mem_total/1024).toFixed(0)} GiB</span></div>
    ${bar(mp,memColor)}
  </div>
  <div class="procs">
    <div class="procs-title">Processes</div>
    ${procsHtml}
  </div>
  ${sparkHtml}
</div>`;
}

function esc(s){
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

async function fetchHistory(){
  try{
    const r=await fetch('/api/history',{signal:AbortSignal.timeout(5000)});
    if(r.ok)_gpuHistory=await r.json();
  }catch(e){}
}

async function refresh(){
  try{
    const r=await fetch('/api/stats',{signal:AbortSignal.timeout(5000)});
    if(!r.ok)throw new Error(r.status);
    const d=await r.json();
    document.getElementById('dot').className='dot';
    document.getElementById('live-txt').textContent='live';

    const avgUtil=d.gpus.reduce((s,g)=>s+g.util,0)/(d.gpus.length||1);
    const totalMem=d.gpus.reduce((s,g)=>s+g.mem_total,0);
    const usedMem=d.gpus.reduce((s,g)=>s+g.mem_used,0);
    const avgTemp=d.gpus.reduce((s,g)=>s+g.temp,0)/(d.gpus.length||1);
    const totalProcs=Object.values(d.procs).reduce((s,a)=>s+a.length,0);

    const sum=document.getElementById('summary');
    sum.style.display='flex';
    document.getElementById('sum-gpus').textContent=d.gpus.length;
    document.getElementById('sum-util').style.color=utilColor(avgUtil);
    document.getElementById('sum-util').textContent=avgUtil.toFixed(0)+'%';
    document.getElementById('sum-mem').textContent=
      `${(usedMem/1024).toFixed(1)}/${(totalMem/1024).toFixed(0)} GiB`;
    document.getElementById('sum-temp').style.color=tempColor(avgTemp);
    document.getElementById('sum-temp').textContent=avgTemp.toFixed(0)+'°C';
    document.getElementById('sum-procs').textContent=totalProcs;

    document.getElementById('grid').innerHTML=
      d.gpus.map(g=>renderCard(g,d.procs)).join('');
  }catch(e){
    document.getElementById('dot').className='dot offline';
    document.getElementById('live-txt').textContent='offline';
  }
}

// Live clock
setInterval(()=>{
  const n=new Date();
  document.getElementById('clock').textContent=
    n.toLocaleDateString()+' '+n.toLocaleTimeString();
},1000);

setInterval(refresh,2000);
setInterval(fetchHistory,60000);
refresh();
fetchHistory();
</script>
</body>
</html>
"""


class _DashboardHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # suppress access logs

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            html = _DASHBOARD_HTML.replace("%%HOST%%", HOSTNAME).replace("%%ACCENT%%", MACHINE_COLOR)
            body = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/api/stats":
            gpus  = get_gpu_stats()
            procs = get_gpu_processes()
            procs_str = {str(k): v for k, v in procs.items()}
            payload = {
                "hostname": HOSTNAME,
                "color":    MACHINE_COLOR,
                "time":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "gpus":     gpus,
                "procs":    procs_str,
            }
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/metrics":
            # Prometheus text format — compatible with Grafana, prometheus scrape
            gpus = get_gpu_stats()
            h = _prom_label(HOSTNAME)
            lines = [
                "# HELP gpu_utilization_percent GPU utilization %",
                "# TYPE gpu_utilization_percent gauge",
            ] + [f'gpu_utilization_percent{{gpu="{g["idx"]}",name="{_prom_label(g["name"])}",host="{h}"}} {g["util"]}' for g in gpus] + [
                "# HELP gpu_memory_used_mib GPU memory used MiB",
                "# TYPE gpu_memory_used_mib gauge",
            ] + [f'gpu_memory_used_mib{{gpu="{g["idx"]}",host="{h}"}} {g["mem_used"]}' for g in gpus] + [
                "# HELP gpu_memory_total_mib GPU memory total MiB",
                "# TYPE gpu_memory_total_mib gauge",
            ] + [f'gpu_memory_total_mib{{gpu="{g["idx"]}",host="{h}"}} {g["mem_total"]}' for g in gpus] + [
                "# HELP gpu_temperature_celsius GPU temperature",
                "# TYPE gpu_temperature_celsius gauge",
            ] + [f'gpu_temperature_celsius{{gpu="{g["idx"]}",host="{h}"}} {g["temp"]}' for g in gpus]
            # Optional: power, power limit, and clocks
            pw = [g for g in gpus if g.get("power_w") is not None]
            if pw:
                lines += ["# HELP gpu_power_watts GPU power draw watts", "# TYPE gpu_power_watts gauge"]
                lines += [f'gpu_power_watts{{gpu="{g["idx"]}",host="{h}"}} {g["power_w"]}' for g in pw]
            pl = [g for g in gpus if g.get("power_limit_w") is not None]
            if pl:
                lines += ["# HELP gpu_power_limit_watts GPU enforced power limit watts", "# TYPE gpu_power_limit_watts gauge"]
                lines += [f'gpu_power_limit_watts{{gpu="{g["idx"]}",host="{h}"}} {g["power_limit_w"]}' for g in pl]
            cl = [g for g in gpus if g.get("clock_mhz") is not None]
            if cl:
                lines += ["# HELP gpu_clock_sm_mhz GPU SM clock MHz", "# TYPE gpu_clock_sm_mhz gauge"]
                lines += [f'gpu_clock_sm_mhz{{gpu="{g["idx"]}",host="{h}"}} {g["clock_mhz"]}' for g in cl]
            # Computed: memory utilization %
            lines += ["# HELP gpu_memory_utilization_percent GPU memory utilization %", "# TYPE gpu_memory_utilization_percent gauge"]
            lines += [f'gpu_memory_utilization_percent{{gpu="{g["idx"]}",host="{h}"}} {round(g["mem_used"]/g["mem_total"]*100,1) if g["mem_total"] else 0}' for g in gpus]
            # Fan speed
            fs = [g for g in gpus if g.get("fan_speed") is not None]
            if fs:
                lines += ["# HELP gpu_fan_speed_percent GPU fan speed %", "# TYPE gpu_fan_speed_percent gauge"]
                lines += [f'gpu_fan_speed_percent{{gpu="{g["idx"]}",host="{h}"}} {g["fan_speed"]}' for g in fs]
            # ECC uncorrected errors (data-center GPUs only)
            ec = [g for g in gpus if g.get("ecc_errors") is not None]
            if ec:
                lines += ["# HELP gpu_ecc_errors_uncorrected GPU uncorrected volatile ECC errors", "# TYPE gpu_ecc_errors_uncorrected gauge"]
                lines += [f'gpu_ecc_errors_uncorrected{{gpu="{g["idx"]}",host="{h}"}} {g["ecc_errors"]}' for g in ec]
            # Process count per GPU
            procs_now = get_gpu_processes()
            lines += ["# HELP gpu_process_count Number of compute processes on GPU", "# TYPE gpu_process_count gauge"]
            lines += [f'gpu_process_count{{gpu="{g["idx"]}",host="{h}"}} {len(procs_now.get(g["idx"], []))}' for g in gpus]
            body = ("\n".join(lines) + "\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/api/history":
            body = json.dumps({str(k): v for k, v in _dashboard_history.items()}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/webhook" and self.command == "POST":
            # Prometheus Alertmanager webhook receiver.
            # Configure Alertmanager to POST to http://YOUR_HOST:WEB_PORT/webhook
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                payload = json.loads(body)
            except Exception as e:
                logger.error(f"Alertmanager webhook: bad request: {e}")
                self.send_response(400)
                self.end_headers()
                return
            for alert in payload.get("alerts", []):
                status   = alert.get("status", "firing")
                labels   = alert.get("labels", {})
                annots   = alert.get("annotations", {})
                name     = labels.get("alertname", "Alert")
                severity = labels.get("severity", "")
                summary  = annots.get("summary", "")
                desc     = annots.get("description", "")
                if status == "firing":
                    icon  = ":fire:" if severity == "critical" else ":warning:"
                    color = "#e01e5a" if severity == "critical" else "#ecb22e"
                    msg   = f"{icon} *{name}*"
                    if summary: msg += f" — {summary}"
                    if desc:    msg += f"\n{desc}"
                else:
                    icon  = ":white_check_mark:"
                    color = "#22c55e"
                    msg   = f"{icon} *{name} resolved*"
                    if summary: msg += f" — {summary}"
                logger.info(f"Alertmanager webhook: {status} {name} ({severity})")
                notify(msg, color=color)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

        else:
            self.send_response(404)
            self.end_headers()


def _start_dashboard(port: int) -> None:
    """Start the web dashboard in a background daemon thread."""
    server = http.server.ThreadingHTTPServer(("", port), _DashboardHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    logger.info(f"Dashboard running at http://0.0.0.0:{port}")


# ---------------------------------------------------------------------------
# GitHub Pages — push stats as JSON so the static dashboard can read them
# ---------------------------------------------------------------------------
def _gh_update_file(token: str, repo: str, path: str, content: bytes, message: str) -> bool:
    """Create or update a file in a GitHub repo via the Contents API."""
    api = f"https://api.github.com/repos/{repo}/contents/{path}"
    hdrs = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    }
    sha = None
    try:
        req = urllib.request.Request(api, headers=hdrs)
        with urllib.request.urlopen(req, timeout=10) as resp:
            sha = json.loads(resp.read())["sha"]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            pass  # new file — no SHA needed
        elif e.code in (401, 403):
            logger.warning(f"GitHub API auth error {e.code} — check GITHUB_PAGES_TOKEN permissions")
            return False
        else:
            logger.debug(f"GitHub GET error {e.code}: {e}")
            return False
    payload: dict = {"message": message, "content": base64.b64encode(content).decode()}
    if sha:
        payload["sha"] = sha
    try:
        req = urllib.request.Request(api, data=json.dumps(payload).encode(), headers=hdrs, method="PUT")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status in (200, 201)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            logger.warning(f"GitHub API auth error {e.code} on PUT — check token")
        else:
            logger.debug(f"GitHub PUT error {e.code}: {e}")
        return False


_last_gh_push: float = 0.0
_GH_PUSH_INTERVAL = 300  # push at most every 5 minutes


def push_stats_to_github(gpus: list[dict], procs: dict) -> None:
    """Push current GPU stats to GitHub Pages repo (best-effort, throttled to 5 min)."""
    global _last_gh_push
    if not GITHUB_PAGES_TOKEN or not GITHUB_PAGES_REPO:
        return
    now = time.time()
    if now - _last_gh_push < _GH_PUSH_INTERVAL:
        return
    _last_gh_push = now
    try:
        stats = {
            "hostname": HOSTNAME,
            "color":    MACHINE_COLOR,
            "ts":       int(time.time()),
            "time":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "version":  __version__,
            "gpus":     gpus,
            "procs":    {str(k): v for k, v in procs.items()},
        }
        _gh_update_file(
            GITHUB_PAGES_TOKEN, GITHUB_PAGES_REPO,
            f"docs/data/{HOSTNAME}.json",
            json.dumps(stats, separators=(",", ":")).encode(),
            f"stats: {HOSTNAME}",
        )
        # Update index.json (list of known machines), retry once on SHA conflict
        _update_index(GITHUB_PAGES_TOKEN, GITHUB_PAGES_REPO)
    except Exception as e:
        logger.debug(f"GitHub Pages push failed: {e}")


def _update_index(token: str, repo: str) -> None:
    """Add this machine to docs/data/index.json if not already listed."""
    api = f"https://api.github.com/repos/{repo}/contents/docs/data/index.json"
    hdrs = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    }
    for _ in range(2):  # retry once on SHA conflict
        sha, machines = None, []
        try:
            req = urllib.request.Request(api, headers=hdrs)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                sha = data["sha"]
                machines = json.loads(base64.b64decode(data["content"]))["machines"]
        except urllib.error.HTTPError as e:
            if e.code != 404:
                return
        if HOSTNAME in machines:
            return
        machines.append(HOSTNAME)
        payload: dict = {
            "message": f"index: add {HOSTNAME}",
            "content": base64.b64encode(json.dumps({"machines": machines}).encode()).decode(),
        }
        if sha:
            payload["sha"] = sha
        try:
            req = urllib.request.Request(api, data=json.dumps(payload).encode(), headers=hdrs, method="PUT")
            with urllib.request.urlopen(req, timeout=15):
                return
        except urllib.error.HTTPError as e:
            if e.code != 409:  # 409 = SHA conflict, retry
                return


# ---------------------------------------------------------------------------
# Monitor loop
# ---------------------------------------------------------------------------
def _fmt_duration(seconds: float) -> str:
    m = int(seconds // 60)
    if m < 60:
        return f"{m}min"
    h, m = divmod(m, 60)
    return f"{h}h{m}m" if m else f"{h}h"


def monitor():
    idle_since       = None
    active_since     = None
    last_alert_time  = None
    last_status_time = 0.0
    was_idle         = False
    partial_alerted  = False
    # Track PIDs from previous iteration for crash detection
    prev_pids: set[str] = set()
    # Memory leak detection: {gpu_idx: [(timestamp, mem_used_mib), ...]}
    _mem_history: dict[int, list] = {}
    _memleak_alerted: set[int] = set()
    # Temperature alerting: {gpu_idx: 'warn' | 'crit'}
    _temp_alerted: dict[int, str] = {}
    # Power throttle tracking: set of GPU indices currently near power limit
    _power_alerted: set[int] = set()
    # ECC error tracking: {gpu_idx: last_known_count}
    _ecc_prev: dict[int, int] = {}

    channels = [c for c, v in [
        ("Slack",        SLACK_WEBHOOK_URL),
        ("Discord",      DISCORD_WEBHOOK_URL),
        ("Telegram",     TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
        ("Email",        EMAIL_SMTP_HOST and EMAIL_TO),
        ("SMS",          TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM and TWILIO_TO),
        ("iMessage",     IMESSAGE_TO and sys.platform == "darwin"),
        ("WeCom",        WECOM_WEBHOOK_URL),
        ("Feishu",       FEISHU_WEBHOOK_URL),
        ("DingTalk",     DINGTALK_WEBHOOK_URL),
        ("Bark",         BARK_URL),
        ("Apprise",      APPRISE_URLS),
        ("Rocket.Chat",  ROCKETCHAT_WEBHOOK_URL),
        ("ntfy",         NTFY_URL),
        ("Gotify",       GOTIFY_URL and GOTIFY_TOKEN),
        ("Pushover",     PUSHOVER_TOKEN and PUSHOVER_USER),
        ("Mattermost",   MATTERMOST_WEBHOOK_URL),
        ("Teams",        TEAMS_WEBHOOK_URL),
        ("Google Chat",  GOOGLE_CHAT_WEBHOOK_URL),
        ("Zulip",        ZULIP_SITE and ZULIP_EMAIL and ZULIP_API_KEY),
        ("OpenClaw",     OPENCLAW_WEBHOOK_URL),
        ("PagerDuty",    PAGERDUTY_INTEGRATION_KEY),
    ] if v]

    logger.info(
        f"Monitor started | host={HOSTNAME} interval={CHECK_INTERVAL}s "
        f"threshold=<{IDLE_THRESHOLD}% idle={IDLE_MINUTES}min "
        f"cooldown={ALERT_COOLDOWN}min | channels: {', '.join(channels) or 'none'}"
    )
    if not channels:
        logger.warning("No notification channels configured")

    if WEB_PORT:
        _start_dashboard(WEB_PORT)

    startup = True

    while True:
        gpus = get_gpu_stats()
        if not gpus:
            time.sleep(CHECK_INTERVAL)
            continue

        now          = time.time()
        _cached_procs: dict | None = None

        def get_procs() -> dict:
            nonlocal _cached_procs
            if _cached_procs is None:
                _cached_procs = get_gpu_processes()
            return _cached_procs

        if startup:
            notify(":rocket: *Monitor started* | " + format_status(gpus, get_procs()))
            last_status_time = now
            startup = False

        # Push to GitHub Pages (throttled to every 5 min)
        push_stats_to_github(gpus, get_procs())

        # Push to InfluxDB (every check interval)
        push_influxdb(gpus)

        # Push to Datadog via DogStatsD
        push_datadog(gpus)

        # Update web dashboard sparkline history
        for g in gpus:
            mp = round(g["mem_used"] / g["mem_total"] * 100) if g["mem_total"] else 0
            hist = _dashboard_history.setdefault(g["idx"], [])
            hist.append([g["util"], mp, g["temp"]])
            if len(hist) > _MAX_HISTORY_POINTS:
                hist.pop(0)

        all_idle = all(g["util"] < IDLE_THRESHOLD for g in gpus)

        status_interval = STATUS_IDLE if all_idle else STATUS_ACTIVE
        if now - last_status_time >= status_interval * 60:
            dur = ""
            if active_since:
                dur = f" | up {_fmt_duration(now - active_since)}"
            elif idle_since:
                dur = f" | idle {_fmt_duration(now - idle_since)}"
            notify(format_status(gpus, get_procs()) + dur)
            last_status_time = now
            logger.info("Periodic status sent")

        idle_gpus = [g for g in gpus if g["util"] < IDLE_THRESHOLD]
        busy_gpus = [g for g in gpus if g["util"] >= IDLE_THRESHOLD]

        if len(idle_gpus) == len(gpus):
            if idle_since is None:
                idle_since = now
                # Just went idle — check if actual PIDs disappeared (real crash vs normal finish)
                if not was_idle and _cooldown_ok(last_alert_time, now):
                    current_procs = get_procs()
                    current_pids = {p["pid"] for plist in current_procs.values() for p in plist}
                    vanished = prev_pids - current_pids
                    if vanished and prev_pids:
                        # Look up names of vanished PIDs from previous proc snapshot
                        # (they're gone now, so use prev_pids set directly; names not available)
                        logger.warning(f"GPUs went idle; vanished PIDs: {vanished}")
                        notify(
                            f":x: *GPUs went idle* — processes exited: {', '.join(sorted(vanished))} | "
                            + format_status(gpus, current_procs),
                            color="#e01e5a",
                        )
                        last_alert_time = now

            active_since    = None
            partial_alerted = False
            prev_pids       = set()

            idle_min = (now - idle_since) / 60
            if idle_min >= IDLE_MINUTES:
                if _cooldown_ok(last_alert_time, now):
                    logger.warning(f"All GPUs idle for {int(idle_min)} min")
                    notify(
                        f":rotating_light: *All idle {_fmt_duration(now - idle_since)}* | "
                        + format_status(gpus, get_procs()),
                        color="#e01e5a",
                    )
                    last_alert_time = now
            was_idle = True

        else:
            if was_idle:
                logger.info("GPUs active again")
                notify(
                    ":white_check_mark: *GPUs active* | " + format_status(gpus, get_procs()),
                    color="#22c55e",
                )
                last_status_time = now

            if idle_gpus and busy_gpus and not partial_alerted and _cooldown_ok(last_alert_time, now):
                idle_ids = ",".join(str(g["idx"]) for g in idle_gpus)
                logger.info(f"Partial idle: {len(idle_gpus)}/{len(gpus)}")
                notify(
                    f":eyes: *{len(idle_gpus)}/{len(gpus)} GPUs idle* "
                    f"(GPU {idle_ids}) | " + format_status(gpus, get_procs()),
                    color="#ecb22e",
                )
                partial_alerted = True
                last_alert_time = now

            if not idle_gpus:
                partial_alerted = False

            # Only start active_since when fully busy (not partial)
            if not idle_gpus and active_since is None:
                active_since = now
            idle_since = None
            was_idle   = False

            # Update tracked PIDs for crash detection
            cur_procs = get_procs()
            prev_pids = {p["pid"] for plist in cur_procs.values() for p in plist}

        # --- Memory leak detection (runs regardless of idle/busy state) ---
        if MEMLEAK_THRESHOLD > 0:
            memleak_window = MEMLEAK_MINUTES * 60
            for g in gpus:
                idx = g["idx"]
                hist = _mem_history.setdefault(idx, [])
                hist.append((now, g["mem_used"]))
                # Prune entries older than window
                hist[:] = [(t, m) for t, m in hist if now - t <= memleak_window]
                if len(hist) < 3:
                    continue
                oldest_mem = hist[0][1]
                latest_mem = hist[-1][1]
                if oldest_mem == 0:
                    continue
                growth_pct = (latest_mem - oldest_mem) / oldest_mem * 100
                proc_count_now = len(get_procs().get(idx, []))
                if growth_pct >= MEMLEAK_THRESHOLD and proc_count_now > 0 and idx not in _memleak_alerted:
                    logger.warning(f"GPU{idx}: memory grew {growth_pct:.0f}% over {MEMLEAK_MINUTES}min ({oldest_mem}→{latest_mem} MiB) — possible leak")
                    notify(
                        f":warning: *GPU{idx} memory leak?* — grew {growth_pct:.0f}% in {MEMLEAK_MINUTES}min "
                        f"({oldest_mem}→{latest_mem} MiB) | " + format_status(gpus, get_procs()),
                        color="#ecb22e",
                    )
                    _memleak_alerted.add(idx)
                elif growth_pct < MEMLEAK_THRESHOLD / 2:
                    _memleak_alerted.discard(idx)  # reset when growth subsides

        # --- Temperature alerting (standalone, no Prometheus needed) ---
        if GPU_TEMP_WARN > 0:
            for g in gpus:
                idx, temp = g["idx"], g["temp"]
                alerted = _temp_alerted.get(idx, "")
                if temp >= GPU_TEMP_CRIT and alerted != "crit":
                    logger.warning(f"GPU{idx}: critical temperature {temp}°C (threshold: {GPU_TEMP_CRIT}°C)")
                    notify(
                        f":fire: *GPU{idx} critical temp* — {temp}°C "
                        f"(threshold: {GPU_TEMP_CRIT}°C). GPU may throttle or shut down.",
                        color="#e01e5a",
                    )
                    _temp_alerted[idx] = "crit"
                elif temp >= GPU_TEMP_WARN and alerted not in ("warn", "crit"):
                    logger.warning(f"GPU{idx}: high temperature {temp}°C (threshold: {GPU_TEMP_WARN}°C)")
                    notify(
                        f":thermometer: *GPU{idx} high temp* — {temp}°C "
                        f"(threshold: {GPU_TEMP_WARN}°C). Check cooling.",
                        color="#ecb22e",
                    )
                    _temp_alerted[idx] = "warn"
                elif temp < GPU_TEMP_WARN - 5:  # hysteresis: clear when 5°C below warn
                    _temp_alerted.pop(idx, None)

        # --- Power throttle alert (when draw >= 95% of enforced power limit) ---
        for g in gpus:
            idx = g["idx"]
            pw = g.get("power_w")
            pl = g.get("power_limit_w")
            if pw is None or pl is None or pl <= 0:
                continue
            pct = pw / pl * 100
            if pct >= 95 and idx not in _power_alerted:
                logger.warning(f"GPU{idx}: near power limit {pw:.0f}/{pl:.0f}W ({pct:.0f}%)")
                notify(
                    f":electric_plug: *GPU{idx} near power limit* — {pw:.0f}/{pl:.0f}W "
                    f"({pct:.0f}%). Performance may be throttled.",
                    color="#ecb22e",
                )
                _power_alerted.add(idx)
            elif pct < 90:
                _power_alerted.discard(idx)

        # --- ECC error alerting (data-center GPUs: A100, H100, V100, etc.) ---
        for g in gpus:
            idx  = g["idx"]
            errs = g.get("ecc_errors")
            if errs is None:
                continue
            prev = _ecc_prev.get(idx)
            if prev is not None and errs > prev:
                new_errs = errs - prev
                logger.error(f"GPU{idx}: {new_errs} new uncorrected ECC error(s) (total: {errs})")
                notify(
                    f":skull: *GPU{idx} ECC error* — {new_errs} new uncorrected volatile ECC error(s) "
                    f"(total: {errs}). GPU memory may be corrupted. Consider rebooting.",
                    color="#e01e5a",
                )
            _ecc_prev[idx] = errs

        time.sleep(CHECK_INTERVAL)


# ---------------------------------------------------------------------------
# Main with watchdog
# ---------------------------------------------------------------------------
def run_with_watchdog(target):
    while True:
        try:
            target()
        except KeyboardInterrupt:
            logger.info("Stopped.")
            break
        except SystemExit:
            break
        except Exception as e:
            logger.error(f"Crashed: {e}, restarting in 10s...")
            time.sleep(10)


def main():
    global WEB_PORT
    parser = argparse.ArgumentParser(description="Lightweight GPU Monitor")
    parser.add_argument("--version",     action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--once",        action="store_true", help="Print status and exit")
    parser.add_argument("--json",        action="store_true", help="Output current GPU stats as JSON and exit")
    parser.add_argument("--watch",       type=int, metavar="SECS", nargs="?", const=2,
                        help="Live terminal GPU table, refreshed every SECS (default 2)")
    parser.add_argument("--channels",    action="store_true", help="List configured notification channels and exit")
    parser.add_argument("--test-notify", action="store_true", help="Send a test notification to all configured channels and exit")
    parser.add_argument("--web",  type=int, metavar="PORT", default=0,
                        help="Start web dashboard on PORT (overrides WEB_PORT env var)")
    args = parser.parse_args()

    if args.channels:
        all_channels = [
            ("Slack",        SLACK_WEBHOOK_URL),
            ("Discord",      DISCORD_WEBHOOK_URL),
            ("Telegram",     TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
            ("Email",        EMAIL_SMTP_HOST and EMAIL_TO),
            ("SMS",          TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM and TWILIO_TO),
            ("iMessage",     IMESSAGE_TO and sys.platform == "darwin"),
            ("WeCom",        WECOM_WEBHOOK_URL),
            ("Feishu",       FEISHU_WEBHOOK_URL),
            ("DingTalk",     DINGTALK_WEBHOOK_URL),
            ("Bark",         BARK_URL),
            ("Rocket.Chat",  ROCKETCHAT_WEBHOOK_URL),
            ("ntfy",         NTFY_URL),
            ("Gotify",       GOTIFY_URL and GOTIFY_TOKEN),
            ("Pushover",     PUSHOVER_TOKEN and PUSHOVER_USER),
            ("Mattermost",   MATTERMOST_WEBHOOK_URL),
            ("Teams",        TEAMS_WEBHOOK_URL),
            ("Google Chat",  GOOGLE_CHAT_WEBHOOK_URL),
            ("Zulip",        ZULIP_SITE and ZULIP_EMAIL and ZULIP_API_KEY),
            ("OpenClaw",       OPENCLAW_WEBHOOK_URL),
            ("PagerDuty",      PAGERDUTY_INTEGRATION_KEY),
            ("Alert Webhook",  ALERT_WEBHOOK_URL),
        ]
        active   = [n for n, v in all_channels if v]
        inactive = [n for n, v in all_channels if not v]
        print(f"Active   ({len(active)}): {', '.join(active) or 'none'}")
        print(f"Inactive ({len(inactive)}): {', '.join(inactive)}")
        sys.exit(0)

    if args.once:
        gpus  = get_gpu_stats()
        procs = get_gpu_processes()
        print(_to_plain(format_status(gpus, procs)))
        sys.exit(0)

    if args.json:
        gpus  = get_gpu_stats()
        procs = get_gpu_processes()
        procs_serializable = {str(k): v for k, v in procs.items()}
        payload = {
            "host":      HOSTNAME,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "version":   __version__,
            "gpus":      gpus,
            "procs":     procs_serializable,
        }
        print(json.dumps(payload, indent=2))
        sys.exit(0)

    if args.watch is not None:
        interval = max(1, args.watch)
        _RESET  = "\033[0m"
        _BOLD   = "\033[1m"
        _RED    = "\033[91m"
        _YELLOW = "\033[93m"
        _GREEN  = "\033[92m"
        _BLUE   = "\033[94m"
        _GRAY   = "\033[90m"
        def _util_color(p):
            return _RED if p >= 90 else _YELLOW if p >= 40 else _GREEN
        def _temp_color(t):
            return _RED if t >= 85 else _YELLOW if t >= 70 else _BLUE
        try:
            while True:
                gpus  = get_gpu_stats()
                procs = get_gpu_processes()
                ts    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print("\033[2J\033[H", end="")  # clear screen + move cursor home
                print(f"{_BOLD}gpu-monitor{_RESET}  {_GRAY}{HOSTNAME}  {ts}{_RESET}")
                print()
                hdr = f"{'GPU':<4} {'Name':<28} {'Util':>5} {'Mem Used/Total':>20} {'Temp':>5}"
                if any(g.get("power_w") is not None for g in gpus):
                    hdr += f" {'Power/Limit':>12}"
                if any(g.get("fan_speed") is not None for g in gpus):
                    hdr += f" {'Fan':>4}"
                print(f"{_BOLD}{hdr}{_RESET}")
                print("─" * len(hdr))
                for g in gpus:
                    uc = _util_color(g["util"])
                    tc = _temp_color(g["temp"])
                    mem = f"{g['mem_used']:,}/{g['mem_total']:,} MiB"
                    row = f"{g['idx']:<4} {g['name'][:27]:<28} {uc}{g['util']:>4}%{_RESET} {mem:>20} {tc}{g['temp']:>4}°C{_RESET}"
                    if g.get("power_w") is not None:
                        pl = g.get("power_limit_w")
                        pw_str = f"{g['power_w']:.0f}/{pl:.0f}W" if pl else f"{g['power_w']:.0f}W"
                        row += f" {pw_str:>12}"
                    if g.get("fan_speed") is not None:
                        row += f" {g['fan_speed']:>3}%"
                    print(row)
                    for p in procs.get(g["idx"], []):
                        print(f"  {_GRAY}└ {p['name']} (pid {p['pid']}, {p['user']}, {p['mem']} MiB){_RESET}")
                print()
                print(f"{_GRAY}Refreshing every {interval}s — Ctrl+C to exit{_RESET}")
                time.sleep(interval)
        except KeyboardInterrupt:
            print()
            sys.exit(0)

    if args.test_notify:
        msg = f"[gpu-monitor] Test notification from {HOSTNAME} — your alerts are working!"
        notify(msg)
        time.sleep(2)  # allow background thread to flush
        channels = [
            ("Slack",    bool(SLACK_WEBHOOK_URL)),
            ("Discord",  bool(DISCORD_WEBHOOK_URL)),
            ("Telegram", bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)),
            ("Email",    bool(EMAIL_SMTP_HOST and EMAIL_USER and EMAIL_PASS and EMAIL_TO)),
            ("SMS",      bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM and TWILIO_TO)),
            ("iMessage", bool(IMESSAGE_TO)),
            ("WeCom",    bool(WECOM_WEBHOOK_URL)),
            ("Feishu",   bool(FEISHU_WEBHOOK_URL)),
            ("DingTalk", bool(DINGTALK_WEBHOOK_URL)),
            ("Bark",     bool(BARK_URL)),
            ("Apprise",      bool(APPRISE_URLS)),
            ("Rocket.Chat",  bool(ROCKETCHAT_WEBHOOK_URL)),
            ("Google Chat",  bool(GOOGLE_CHAT_WEBHOOK_URL)),
            ("Zulip",       bool(ZULIP_SITE and ZULIP_EMAIL and ZULIP_API_KEY)),
            ("Mattermost", bool(MATTERMOST_WEBHOOK_URL)),
            ("Teams",    bool(TEAMS_WEBHOOK_URL)),
            ("Pushover", bool(PUSHOVER_TOKEN and PUSHOVER_USER)),
            ("Gotify",   bool(GOTIFY_URL and GOTIFY_TOKEN)),
            ("ntfy",     bool(NTFY_URL)),
            ("OpenClaw",   bool(OPENCLAW_WEBHOOK_URL)),
            ("PagerDuty",  bool(PAGERDUTY_INTEGRATION_KEY)),
        ]
        active   = [n for n, ok in channels if ok]
        inactive = [n for n, ok in channels if not ok]
        print(f"Test notification sent to: {', '.join(active) or 'none'}")
        if inactive:
            print(f"Not configured:           {', '.join(inactive)}")
        sys.exit(0)

    if args.web:
        WEB_PORT = args.web

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    run_with_watchdog(monitor)


if __name__ == "__main__":
    main()

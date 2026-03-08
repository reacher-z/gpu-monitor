#!/usr/bin/env python3
"""
Lightweight GPU Monitor with multi-channel notifications and web dashboard.

Supported notification channels (configure via environment variables):
  Slack, Discord, Telegram, Email (SMTP), SMS (Twilio), iMessage (macOS only),
  WeCom (企业微信), Feishu (飞书), DingTalk (钉钉), Bark (iOS push),
  ntfy (self-hosted or ntfy.sh), Gotify (self-hosted), Pushover, Microsoft Teams,
  OpenClaw (routes to WhatsApp, Teams, Signal, LINE, Mattermost, Matrix, Zalo, etc.)

Web dashboard:
  Set WEB_PORT=8080 (or any port) to enable the real-time GPU dashboard.
  Then open http://localhost:8080 in your browser.
"""

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
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")  # Microsoft Teams incoming webhook URL

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
                "power_w":   None,
                "clock_mhz": None,
            })

        # Optional query — power and clock; skip silently if driver doesn't support it
        try:
            r2 = subprocess.run(
                ["nvidia-smi",
                 "--query-gpu=index,power.draw,clocks.sm",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10,
            )
            if r2.returncode == 0:
                idx_map = {g["idx"]: g for g in gpus}
                for line in r2.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    p = [x.strip() for x in line.split(",")]
                    if len(p) < 3:
                        continue
                    idx = _safe_int(p[0])
                    if idx is not None and idx in idx_map:
                        idx_map[idx]["power_w"]   = _safe_float(p[1])
                        idx_map[idx]["clock_mhz"] = _safe_int(p[2])
        except Exception as e:
            logger.debug(f"Optional power/clock query failed (skipping): {e}")

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
            send_teams(plain)
            send_pushover(plain)
            send_gotify(plain)
            send_ntfy(plain)
            send_openclaw(plain)
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

function renderCard(g,procs){
  const mp=g.mem_total?g.mem_used/g.mem_total*100:0;
  const pl=(procs[g.idx]||[]);
  const procsHtml=pl.length
    ?pl.map(p=>`<div class="proc"><span class="proc-name">${esc(p.name)}</span><span class="proc-mem">${p.mem} MiB</span></div>`).join('')
    :'<div class="no-proc">idle</div>';
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
</div>`;
}

function esc(s){
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
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
refresh();
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
            # Optional: power and clocks
            pw = [g for g in gpus if g.get("power_w") is not None]
            if pw:
                lines += ["# HELP gpu_power_watts GPU power draw watts", "# TYPE gpu_power_watts gauge"]
                lines += [f'gpu_power_watts{{gpu="{g["idx"]}",host="{h}"}} {g["power_w"]}' for g in pw]
            cl = [g for g in gpus if g.get("clock_mhz") is not None]
            if cl:
                lines += ["# HELP gpu_clock_sm_mhz GPU SM clock MHz", "# TYPE gpu_clock_sm_mhz gauge"]
                lines += [f'gpu_clock_sm_mhz{{gpu="{g["idx"]}",host="{h}"}} {g["clock_mhz"]}' for g in cl]
            body = ("\n".join(lines) + "\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

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

    channels = [c for c, v in [
        ("Slack",    SLACK_WEBHOOK_URL),
        ("Discord",  DISCORD_WEBHOOK_URL),
        ("Telegram", TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
        ("Email",    EMAIL_SMTP_HOST and EMAIL_TO),
        ("SMS",      TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM and TWILIO_TO),
        ("iMessage", IMESSAGE_TO and sys.platform == "darwin"),
        ("WeCom",    WECOM_WEBHOOK_URL),
        ("Feishu",   FEISHU_WEBHOOK_URL),
        ("DingTalk", DINGTALK_WEBHOOK_URL),
        ("Bark",     BARK_URL),
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
    parser.add_argument("--once",        action="store_true", help="Print status and exit")
    parser.add_argument("--test-notify", action="store_true", help="Send a test notification to all configured channels and exit")
    parser.add_argument("--web",  type=int, metavar="PORT", default=0,
                        help="Start web dashboard on PORT (overrides WEB_PORT env var)")
    args = parser.parse_args()

    if args.once:
        gpus  = get_gpu_stats()
        procs = get_gpu_processes()
        print(_to_plain(format_status(gpus, procs)))
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
            ("Teams",    bool(TEAMS_WEBHOOK_URL)),
            ("Pushover", bool(PUSHOVER_TOKEN and PUSHOVER_USER)),
            ("Gotify",   bool(GOTIFY_URL and GOTIFY_TOKEN)),
            ("ntfy",     bool(NTFY_URL)),
            ("OpenClaw", bool(OPENCLAW_WEBHOOK_URL)),
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

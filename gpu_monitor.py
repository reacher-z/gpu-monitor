#!/usr/bin/env python3
"""
Lightweight GPU Monitor with multi-channel notifications.

Supported channels (configure via environment variables):
  Slack, Discord, Telegram, Email (SMTP), SMS (Twilio), iMessage (macOS only)
"""

import hashlib
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
import time
import urllib.parse
import urllib.request
from base64 import b64encode
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

HOSTNAME = socket.gethostname().split(".")[0] or "unknown"

_COLORS = ["#2eb886", "#e01e5a", "#36c5f0", "#ecb22e", "#6c5ce7", "#e17055", "#00b894", "#fd79a8"]
MACHINE_COLOR = os.environ.get(
    "MACHINE_COLOR",
    _COLORS[int(hashlib.md5(HOSTNAME.encode()).hexdigest(), 16) % len(_COLORS)],
)

# ---------------------------------------------------------------------------
# Config — notification channels
# ---------------------------------------------------------------------------
SLACK_WEBHOOK_URL   = os.environ.get("SLACK_WEBHOOK_URL",   "")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
TELEGRAM_BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN",  "")
TELEGRAM_CHAT_ID    = os.environ.get("TELEGRAM_CHAT_ID",    "")
EMAIL_SMTP_HOST     = os.environ.get("EMAIL_SMTP_HOST",     "")
EMAIL_SMTP_PORT     = int(os.environ.get("EMAIL_SMTP_PORT", "587"))
EMAIL_USER          = os.environ.get("EMAIL_USER",          "")
EMAIL_PASS          = os.environ.get("EMAIL_PASS",          "")
EMAIL_TO            = os.environ.get("EMAIL_TO",            "")   # comma-separated
TWILIO_ACCOUNT_SID  = os.environ.get("TWILIO_ACCOUNT_SID",  "")
TWILIO_AUTH_TOKEN   = os.environ.get("TWILIO_AUTH_TOKEN",   "")
TWILIO_FROM         = os.environ.get("TWILIO_FROM",         "")
TWILIO_TO           = os.environ.get("TWILIO_TO",           "")   # comma-separated
IMESSAGE_TO         = os.environ.get("IMESSAGE_TO",         "")   # comma-separated


# ---------------------------------------------------------------------------
# GPU queries
# ---------------------------------------------------------------------------
def get_gpu_stats() -> list[dict]:
    try:
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
            p = [x.strip() for x in line.split(",")]
            if len(p) >= 6:
                gpus.append({
                    "idx": int(p[0]), "name": p[1], "util": int(p[2]),
                    "mem_used": int(p[3]), "mem_total": int(p[4]), "temp": int(p[5]),
                })
        return gpus
    except Exception:
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
        uuid_map = {}
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
                    procs.setdefault(idx, []).append(
                        {"pid": p[1], "name": p[2].split("/")[-1], "mem": p[3]}
                    )
        return procs
    except Exception:
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
    now      = datetime.now().strftime("%m-%d %H:%M")
    total_mem = sum(g["mem_total"] for g in gpus)
    used_mem  = sum(g["mem_used"]  for g in gpus)
    mem_pct   = used_mem / total_mem * 100 if total_mem else 0
    avg_util  = sum(g["util"] for g in gpus) / len(gpus)
    avg_temp  = sum(g["temp"] for g in gpus) / len(gpus)
    util_parts = " ".join(f"{g['idx']}:{g['util']}%" for g in gpus)
    lines = [
        f"`{HOSTNAME}` | {now} | avg *{avg_util:.0f}%* | "
        f"{avg_temp:.0f}C | mem {used_mem // 1024}G/{total_mem // 1024}G ({mem_pct:.0f}%)",
        f"`{util_parts}`",
    ]
    if procs:
        proc_parts = [
            f"GPU{idx}: " + ", ".join(f"{p['name']}({p['mem']}M)" for p in plist)
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
        msg["Subject"] = subject
        msg["From"]    = EMAIL_USER
        msg["To"]      = EMAIL_TO
        with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, timeout=15) as s:
            s.starttls()
            s.login(EMAIL_USER, EMAIL_PASS)
            s.sendmail(EMAIL_USER, [a.strip() for a in EMAIL_TO.split(",")], msg.as_string())
        return True
    except Exception as e:
        logger.error(f"Email error: {e}")
        return False


def send_sms(plain_text: str) -> bool:
    """Send SMS via Twilio REST API (no SDK required)."""
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM, TWILIO_TO]):
        return False
    url   = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    creds = b64encode(f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}".encode()).decode()
    body  = (plain_text[:155] + "…") if len(plain_text) > 160 else plain_text
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
    # Text passed as argv — never interpolated into script code
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


def notify(slack_text: str, color: str = "") -> None:
    """Dispatch to all configured notification channels."""
    plain = _to_plain(slack_text)
    send_slack(slack_text, color)
    send_discord(plain, color)
    send_telegram(plain)
    send_email(plain)
    send_sms(plain)
    send_imessage(plain)


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

    channels = [c for c, v in [
        ("Slack",    SLACK_WEBHOOK_URL),
        ("Discord",  DISCORD_WEBHOOK_URL),
        ("Telegram", TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
        ("Email",    EMAIL_SMTP_HOST and EMAIL_TO),
        ("SMS",      TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM and TWILIO_TO),
        ("iMessage", IMESSAGE_TO and sys.platform == "darwin"),
    ] if v]

    logger.info(
        f"Monitor started | host={HOSTNAME} interval={CHECK_INTERVAL}s "
        f"threshold=<{IDLE_THRESHOLD}% idle={IDLE_MINUTES}min "
        f"cooldown={ALERT_COOLDOWN}min | channels: {', '.join(channels) or 'none'}"
    )
    if not channels:
        logger.warning("No notification channels configured")

    startup = True

    while True:
        gpus = get_gpu_stats()
        if not gpus:
            time.sleep(CHECK_INTERVAL)
            continue

        now      = time.time()
        procs    = None  # fetched lazily; at most one call per iteration

        def get_procs() -> dict:
            nonlocal procs
            if procs is None:
                procs = get_gpu_processes()
            return procs

        # Startup notification (first successful GPU read)
        if startup:
            notify(f":rocket: *Monitor started* | " + format_status(gpus, get_procs()))
            last_status_time = now
            startup = False

        all_idle = all(g["util"] < IDLE_THRESHOLD for g in gpus)

        # Periodic status report
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
            # All GPUs idle
            if idle_since is None:
                idle_since = now
            active_since    = None
            partial_alerted = False

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
            # At least one GPU active
            if not idle_gpus:
                # All GPUs fully busy — allow partial-idle to re-alert next time
                partial_alerted = False

            if was_idle:
                # Recovery from full idle
                logger.info("GPUs active again")
                notify(
                    f":white_check_mark: *GPUs active* | " + format_status(gpus, get_procs()),
                    color="#22c55e",
                )
                last_status_time = now

            # Partial idle: some GPUs wasted
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

            if active_since is None:
                active_since = now
            idle_since = None
            was_idle   = False

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
    import argparse
    parser = argparse.ArgumentParser(description="Lightweight GPU Monitor")
    parser.add_argument("--once", action="store_true", help="Print status and exit")
    args = parser.parse_args()

    if args.once:
        gpus  = get_gpu_stats()
        procs = get_gpu_processes()
        print(_to_plain(format_status(gpus, procs)))
        sys.exit(0)

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    run_with_watchdog(monitor)


if __name__ == "__main__":
    main()

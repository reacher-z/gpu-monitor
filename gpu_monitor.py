#!/usr/bin/env python3
"""
Lightweight GPU Monitor with Slack alerts and periodic status reports.

Features:
- Slack alerts when GPUs idle (<10%) with per-machine color coding
- Recovery notification when GPUs become active
- Periodic GPU status report to Slack
- GPU process info (who is using which GPU)
- Process watchdog with auto-restart
"""

import hashlib
import json
import logging
import logging.handlers
import os
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

# Log rotation: 5MB per file, keep 3 backups
_log_file = os.environ.get("LOG_FILE", "")
_handlers: list[logging.Handler] = [logging.StreamHandler()]
if _log_file:
    _handlers.append(
        logging.handlers.RotatingFileHandler(_log_file, maxBytes=5*1024*1024, backupCount=3)
    )
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=_handlers,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "60"))       # seconds
IDLE_THRESHOLD = int(os.environ.get("IDLE_THRESHOLD", "10"))       # percent
IDLE_MINUTES = int(os.environ.get("IDLE_MINUTES", "5"))            # before alert
ALERT_COOLDOWN = int(os.environ.get("ALERT_COOLDOWN", "30"))       # between alerts
STATUS_ACTIVE = int(os.environ.get("STATUS_ACTIVE", "10"))         # report interval when active (min)
STATUS_IDLE = int(os.environ.get("STATUS_IDLE", "30"))             # report interval when idle (min)

_full_hostname = subprocess.run(
    ["hostname"], capture_output=True, text=True
).stdout.strip() or "unknown"
HOSTNAME = _full_hostname.split(".")[0]

_COLORS = ["#2eb886", "#e01e5a", "#36c5f0", "#ecb22e", "#6c5ce7", "#e17055", "#00b894", "#fd79a8"]
MACHINE_COLOR = os.environ.get(
    "MACHINE_COLOR",
    _COLORS[int(hashlib.md5(HOSTNAME.encode()).hexdigest(), 16) % len(_COLORS)],
)


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
                    "mem_used": int(p[3]), "mem_total": int(p[4]),
                    "temp": int(p[5]),
                })
        return gpus
    except Exception:
        return []


def get_gpu_processes() -> dict[int, list[dict]]:
    """Returns {gpu_idx: [{pid, name, mem}]}"""
    try:
        r = subprocess.run(
            ["nvidia-smi",
             "--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory",
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
                    procs.setdefault(idx, []).append({
                        "pid": p[1],
                        "name": p[2].split("/")[-1],
                        "mem": p[3],
                    })
        return procs
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------
def format_status(gpus: list[dict], procs: dict | None = None) -> str:
    if not gpus:
        return ":x: Cannot read GPU status"
    now = datetime.now().strftime("%m-%d %H:%M")
    total_mem = sum(g["mem_total"] for g in gpus)
    used_mem = sum(g["mem_used"] for g in gpus)
    mem_pct = used_mem / total_mem * 100 if total_mem else 0
    avg_util = sum(g["util"] for g in gpus) / len(gpus)
    avg_temp = sum(g["temp"] for g in gpus) / len(gpus)

    util_parts = " ".join(f"{g['idx']}:{g['util']}%" for g in gpus)

    lines = [
        f"`{HOSTNAME}` | {now} | avg *{avg_util:.0f}%* | "
        f"{avg_temp:.0f}C | mem {used_mem // 1024}G/{total_mem // 1024}G ({mem_pct:.0f}%)",
        f"`{util_parts}`",
    ]

    if procs:
        proc_parts = []
        for idx, plist in sorted(procs.items()):
            names = ", ".join(f"{p['name']}({p['mem']}M)" for p in plist)
            proc_parts.append(f"GPU{idx}: {names}")
        lines.append("_" + " | ".join(proc_parts) + "_")

    return "\n".join(lines)


def send_slack(webhook_url: str, text: str, color: str = "") -> bool:
    if not webhook_url:
        return False
    color = color or MACHINE_COLOR
    payload = {"attachments": [{"color": color, "text": text, "mrkdwn_in": ["text"]}]}
    try:
        req = urllib.request.Request(
            webhook_url, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        logger.error(f"Slack send failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Monitor loop
# ---------------------------------------------------------------------------
def _fmt_duration(seconds: float) -> str:
    """Format seconds into compact duration string."""
    m = int(seconds // 60)
    if m < 60:
        return f"{m}min"
    h, m = divmod(m, 60)
    return f"{h}h{m}m" if m else f"{h}h"


def monitor():
    idle_since = None
    active_since = None
    last_alert_time = None
    last_status_time = 0.0
    was_idle = False
    partial_alerted = False

    logger.info(
        f"Monitor started | host={HOSTNAME} interval={CHECK_INTERVAL}s "
        f"threshold=<{IDLE_THRESHOLD}% idle={IDLE_MINUTES}min "
        f"cooldown={ALERT_COOLDOWN}min active_report={STATUS_ACTIVE}min idle_report={STATUS_IDLE}min"
    )
    if not SLACK_WEBHOOK_URL:
        logger.warning("SLACK_WEBHOOK_URL not set – alerts disabled")

    # Startup notification
    gpus = get_gpu_stats()
    if gpus:
        procs = get_gpu_processes()
        send_slack(SLACK_WEBHOOK_URL,
                   f":rocket: *Monitor started* | " + format_status(gpus, procs))
        last_status_time = time.time()

    while True:
        gpus = get_gpu_stats()
        if not gpus:
            time.sleep(CHECK_INTERVAL)
            continue

        now = time.time()
        all_idle = all(g["util"] < IDLE_THRESHOLD for g in gpus)

        # --- Periodic status report (different intervals for active vs idle) ---
        status_interval = STATUS_IDLE if all_idle else STATUS_ACTIVE
        if now - last_status_time >= status_interval * 60:
            procs = get_gpu_processes()
            dur = ""
            if active_since:
                dur = f" | up {_fmt_duration(now - active_since)}"
            elif idle_since:
                dur = f" | idle {_fmt_duration(now - idle_since)}"
            send_slack(SLACK_WEBHOOK_URL, format_status(gpus, procs) + dur)
            last_status_time = now
            logger.info("Periodic status sent")

        # --- Idle / partial idle detection ---
        idle_gpus = [g for g in gpus if g["util"] < IDLE_THRESHOLD]
        busy_gpus = [g for g in gpus if g["util"] >= IDLE_THRESHOLD]

        if len(idle_gpus) == len(gpus):
            # All idle
            if idle_since is None:
                idle_since = now
            active_since = None
            partial_alerted = False

            idle_min = (now - idle_since) / 60
            if idle_min >= IDLE_MINUTES:
                should_alert = (
                    last_alert_time is None
                    or (now - last_alert_time) / 60 >= ALERT_COOLDOWN
                )
                if should_alert:
                    procs = get_gpu_processes()
                    msg = (
                        f":rotating_light: *All idle {_fmt_duration(now - idle_since)}* | "
                        + format_status(gpus, procs)
                    )
                    logger.warning(f"All GPUs idle for {int(idle_min)} min")
                    send_slack(SLACK_WEBHOOK_URL, msg, color="#e01e5a")
                    last_alert_time = now
            was_idle = True
        else:
            # --- Recovery notification ---
            if was_idle and idle_since is not None:
                procs = get_gpu_processes()
                msg = (
                    f":white_check_mark: *GPUs active* | "
                    + format_status(gpus, procs)
                )
                logger.info("GPUs active again")
                send_slack(SLACK_WEBHOOK_URL, msg, color="#22c55e")
                last_status_time = now

            # --- Partial idle: some GPUs wasted ---
            if idle_gpus and busy_gpus and not partial_alerted:
                should_partial = (
                    last_alert_time is None
                    or (now - last_alert_time) / 60 >= ALERT_COOLDOWN
                )
                if should_partial:
                    idle_ids = ",".join(str(g["idx"]) for g in idle_gpus)
                    procs = get_gpu_processes()
                    msg = (
                        f":eyes: *{len(idle_gpus)}/{len(gpus)} GPUs idle* "
                        f"(GPU {idle_ids}) | " + format_status(gpus, procs)
                    )
                    logger.info(f"Partial idle: {len(idle_gpus)}/{len(gpus)}")
                    send_slack(SLACK_WEBHOOK_URL, msg, color="#ecb22e")
                    partial_alerted = True
                    last_alert_time = now

            if active_since is None:
                active_since = now
            idle_since = None
            was_idle = False

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
        gpus = get_gpu_stats()
        procs = get_gpu_processes()
        print(format_status(gpus, procs))
        sys.exit(0)

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    run_with_watchdog(monitor)


if __name__ == "__main__":
    main()

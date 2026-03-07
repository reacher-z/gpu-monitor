#!/bin/bash
# GPU Monitor - one-click start
# Usage: bash start.sh [stop|status|restart]

DIR="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$DIR/.monitor.pid"
LOGFILE="$DIR/gpu_monitor.log"

# ---- Config (set these via environment or edit here) ----
export SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"
export DISCORD_WEBHOOK_URL="${DISCORD_WEBHOOK_URL:-}"
export TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
export TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-}"
export EMAIL_SMTP_HOST="${EMAIL_SMTP_HOST:-}"
export EMAIL_USER="${EMAIL_USER:-}"
export EMAIL_PASS="${EMAIL_PASS:-}"
export EMAIL_TO="${EMAIL_TO:-}"
export TWILIO_ACCOUNT_SID="${TWILIO_ACCOUNT_SID:-}"
export TWILIO_AUTH_TOKEN="${TWILIO_AUTH_TOKEN:-}"
export TWILIO_FROM="${TWILIO_FROM:-}"
export TWILIO_TO="${TWILIO_TO:-}"
export IMESSAGE_TO="${IMESSAGE_TO:-}"
export CHECK_INTERVAL="${CHECK_INTERVAL:-60}"
export IDLE_THRESHOLD="${IDLE_THRESHOLD:-10}"
export IDLE_MINUTES="${IDLE_MINUTES:-5}"
export ALERT_COOLDOWN="${ALERT_COOLDOWN:-30}"
export STATUS_ACTIVE="${STATUS_ACTIVE:-10}"
export STATUS_IDLE="${STATUS_IDLE:-30}"
export LOG_FILE="$LOGFILE"
# export MACHINE_COLOR="#2eb886"
# export http_proxy=http://your-proxy-host:port
# export https_proxy=http://your-proxy-host:port
# ---------------------------------------------------------

stop_monitor() {
    if [ -f "$PIDFILE" ]; then
        PID=$(cat "$PIDFILE")
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID"
            echo "Stopped (PID $PID)"
        else
            echo "Process $PID not running"
        fi
        rm -f "$PIDFILE"
    else
        echo "Not running"
    fi
}

start_monitor() {
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        echo "Already running (PID $(cat "$PIDFILE"))"
        return
    fi
    cd "$DIR"
    nohup python3 gpu_monitor.py >> "$LOGFILE" 2>&1 &
    echo $! > "$PIDFILE"
    echo "Started (PID $!) | log: $LOGFILE"
}

case "${1:-start}" in
    stop)    stop_monitor ;;
    restart) stop_monitor; sleep 1; start_monitor ;;
    status)
        if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
            echo "Running (PID $(cat "$PIDFILE"))"
        else
            echo "Not running"
        fi
        ;;
    start|*) start_monitor ;;
esac

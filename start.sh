#!/bin/bash
# GPU Monitor - one-click start
# Usage: bash start.sh [stop|status|restart]

DIR="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$DIR/.monitor.pid"
LOGFILE="$DIR/gpu_monitor.log"

# ---- Config (edit these or set in .env) ----
export SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"
# export http_proxy=http://your-proxy-host:port
# export https_proxy=http://your-proxy-host:port
export CHECK_INTERVAL=60
export IDLE_THRESHOLD=10
export IDLE_MINUTES=5
export ALERT_COOLDOWN=30
export STATUS_ACTIVE=10          # report every N min when GPUs active
export STATUS_IDLE=30            # report every N min when GPUs idle
export LOG_FILE="$LOGFILE"       # enable log rotation (5MB x 3 backups)
# export MACHINE_COLOR="#2eb886"  # optional: override auto color
# ------------------------------

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

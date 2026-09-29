#!/bin/bash
# Tatap - service manager (lokal)
DIR="$(cd "$(dirname "$0")" && pwd)"
PIDF="$DIR/server.pid"
LOG="/tmp/tatap.log"
case "$1" in
  start)
    if [ -f "$PIDF" ] && kill -0 $(cat "$PIDF") 2>/dev/null; then echo "sudah jalan"; exit 0; fi
    cd "$DIR" && setsid nohup ./run.sh > "$LOG" 2>&1 < /dev/null & echo $! > "$PIDF"
    sleep 3; curl -s --max-time 8 http://127.0.0.1:8767/api/health | head -c 120; echo;;
  stop) if [ -f "$PIDF" ]; then kill $(cat "$PIDF") 2>/dev/null; pkill -P $(cat "$PIDF") 2>/dev/null; rm -f "$PIDF"; fi; echo stopped;;
  status) [ -f "$PIDF" ] && kill -0 $(cat "$PIDF") 2>/dev/null && echo "jalan ($(cat $PIDF))" || echo berhenti;;
  logs) tail -30 "$LOG";;
  *) echo "pakai: $0 {start|stop|status|logs}";;
esac

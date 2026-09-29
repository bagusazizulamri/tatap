#!/bin/bash
cd "$(dirname "$0")"
# Full-tunnel warp (warp-cli mode warp) sudah bungkus semua trafik -> TANPA proxy.
# Mode proxy (127.0.0.1:8899) baru dipakai bila port itu aktif.
if curl -s --max-time 2 -o /dev/null -x http://127.0.0.1:8899 https://www.cloudflare.com/cdn-cgi/trace 2>/dev/null; then
  export WARP_PROXY="${WARP_PROXY:-http://127.0.0.1:8899}"
else
  unset WARP_PROXY
fi
./venv/bin/python backend/main.py

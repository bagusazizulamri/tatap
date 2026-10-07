#!/bin/bash
cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1
# Direct utama agar cepat. Warp full-tunnel mesin (bila aktif) tetap jadi
# jaring pengaman di level OS; WARP_PROXY hanya failover eksplisit per-request
# bila mode proxy warp sedang hidup di 127.0.0.1:8899.
if curl -s --max-time 2 -o /dev/null -x http://127.0.0.1:8899 https://www.cloudflare.com/cdn-cgi/trace 2>/dev/null; then
  export WARP_PROXY="${WARP_PROXY:-http://127.0.0.1:8899}"
else
  unset WARP_PROXY
fi
exec ./venv/bin/python backend/main.py

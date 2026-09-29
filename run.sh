#!/bin/bash
cd "$(dirname "$0")"
export WARP_PROXY="${WARP_PROXY:-http://127.0.0.1:8899}"
./venv/bin/python backend/main.py

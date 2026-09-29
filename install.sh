#!/bin/bash
# Tatap - script pemasangan (sekali saja).
set -e
cd "$(dirname "$0")"

echo "=== Tatap: pemasangan ==="

if ! command -v python3 >/dev/null 2>&1; then
  echo "Butuh python3 (versi 3.11+). Pasang dulu lalu ulangi."
  exit 1
fi
echo "Python: $(python3 --version 2>&1)"

if [ ! -d venv ]; then
  echo "Membuat venv..."
  python3 -m venv venv
fi

echo "Memasang kebutuhan..."
./venv/bin/pip install -q --upgrade pip
./venv/bin/pip install -q -r requirements.txt

mkdir -p cache

echo "Menyiapkan basis data..."
./venv/bin/python -c "import sys; sys.path.insert(0,'backend'); import asyncio; from database import init_db; asyncio.run(init_db()); print('Basis data siap.')"

echo ""
echo "=== Selesai ==="
echo "Jalankan: ./run.sh"
echo "Lalu buka: http://127.0.0.1:8767"

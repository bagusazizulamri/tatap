@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Tatap - Console Mode

echo ==============================================
echo  Tatap - Nonton Santai di Lokal (Console Mode)
echo ==============================================
echo.

REM Cek apakah port 8767 sedang dipakai oleh proses lain (misal Tatap.exe di background)
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr /r ":8767.*LISTENING"') do (
    echo [INFO] Port 8767 sedang digunakan oleh proses dengan PID: %%a
    echo [INFO] Menghentikan proses lama agar console mode bisa berjalan...
    taskkill /F /PID %%a >nul 2>&1
    timeout /t 1 /nobreak >nul
)

if exist "runtime\python.exe" (
    set "PY=runtime\python.exe"
) else (
    set "PY=python"
)

echo Membuka browser ke http://127.0.0.1:8767 ...
start "" http://127.0.0.1:8767

echo Menjalankan backend... (Tutup jendela ini untuk mematikan server)
echo.
"%PY%" backend\main.py
pause

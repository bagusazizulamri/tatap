@echo off
setlocal
cd /d "%~dp0"
title Tatap - Hentikan Server

echo ==============================================
echo  Menghentikan Server Tatap...
echo ==============================================

REM Kirim permintaan shutdown ke server
curl -s -X POST http://127.0.0.1:8767/api/shutdown >nul 2>&1
timeout /t 1 /nobreak >nul

REM Pastikan port 8767 benar-benar bebas
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr /r ":8767.*LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo Server Tatap berhasil dimatikan.
timeout /t 2 >nul

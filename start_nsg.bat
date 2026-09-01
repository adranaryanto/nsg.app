@echo off
title LOGBOOK WEB - FLASK + CLOUDFLARE TUNNEL

echo ==========================================
echo        LOGBOOK WEB SERVER
echo ==========================================
echo.

cd /d "D:\data\logbook_web"

echo [1] Menjalankan Flask...
start "FLASK SERVER" cmd /k "cd /d D:\data\logbook_web && python app.py"

echo.
echo Menunggu Flask aktif...
timeout /t 5 /nobreak >nul

echo.
echo [2] Menjalankan Cloudflare Tunnel...
echo.
echo Website publik akan muncul di bawah.
echo Jangan tutup jendela ini.
echo.

"D:\data\logbook_web\cloudflared-windows-amd64.exe" tunnel --url http://127.0.0.1:5000

echo.
echo ==========================================
echo Cloudflare Tunnel berhenti.
echo ==========================================
pause
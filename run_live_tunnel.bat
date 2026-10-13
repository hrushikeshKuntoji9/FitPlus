@echo off
title FitPulse Pro - Live Public Tunnel Launcher
color 0B

echo =========================================================================
echo       FITPULSE PRO - LIVE PUBLIC SECURE HTTPS DEPLOYMENT
echo =========================================================================
echo.

cd /d "%~dp0"

echo 1. Starting local backend server on port 5000...
start "FitPulse Backend Server" python server.py

echo 2. Waiting 3 seconds for server initialization...
timeout /t 3 /nobreak >nul

echo 3. Starting Cloudflare secure HTTPS public tunnel...
echo.
echo =========================================================================
echo YOUR LIVE PUBLIC URL WILL APPEAR BELOW (Look for trycloudflare.com):
echo Share this link with clients or open it on your mobile phone!
echo =========================================================================
echo.

deploy\cloudflared.exe tunnel --url http://127.0.0.1:5000

pause

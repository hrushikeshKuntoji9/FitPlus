@echo off
title FitPulse Pro - Full Stack Server
color 0A

echo =========================================================================
echo               FITPULSE PRO - HEALTH ^& FITNESS WEB APPLICATION
echo =========================================================================
echo.
echo Starting the FitPulse Full-Stack Python Server...
echo.

cd /d "%~dp0"

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set PY_CMD=python
    goto RUN
)

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set PY_CMD=py
    goto RUN
)

echo [ERROR] Python was not found in your PATH!
echo Please install Python 3.10+ or add it to PATH.
pause
exit /b 1

:RUN
echo Using Python interpreter: %PY_CMD%
echo Installing dependencies if needed...
%PY_CMD% -m pip install -r requirements.txt >nul 2>nul

echo.
echo Initializing database and launching server...
start "" "http://127.0.0.1:5000/fitpulse/index.html"
%PY_CMD% server.py

pause

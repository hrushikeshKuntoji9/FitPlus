@echo off
title FitPulse Pro - Push to GitHub
color 0A

echo =========================================================================
echo              FITPULSE PRO - GITHUB PUSH HELPER
echo =========================================================================
echo.

cd /d "%~dp0"

echo Your local repository is initialized and committed on branch 'main'.
echo.
echo Step 1: Create a new repository on GitHub:
echo         https://github.com/new
echo.
set DEFAULT_URL=https://github.com/hrushikeshKuntoji9/FitPlus.git
echo Target Repository: %DEFAULT_URL%
echo.
set /p REPO_URL="Press Enter to push to this repo, or paste a new URL: "

if "%REPO_URL%"=="" (
    set REPO_URL=%DEFAULT_URL%
)

echo.
echo Connecting remote origin to: %REPO_URL%
"C:\Program Files\Git\cmd\git.exe" remote remove origin 2>nul
"C:\Program Files\Git\cmd\git.exe" remote add origin %REPO_URL%

echo.
echo Pushing branch 'main' to GitHub...
echo (If a GitHub login dialog appears, click 'Sign in with your browser')
"C:\Program Files\Git\cmd\git.exe" push -u origin main

if %ERRORLEVEL% EQU 0 (
    echo.
    echo =====================================================================
    echo [SUCCESS] Your repository is now LIVE on GitHub!
    echo URL: %REPO_URL%
    echo =====================================================================
) else (
    echo.
    echo [NOTE] If authentication failed, you can generate a Personal Access Token:
    echo        https://github.com/settings/tokens
)

pause

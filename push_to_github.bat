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
echo Step 2: Paste your GitHub repository URL below
echo         (e.g., https://github.com/yourusername/fitpulse.git)
echo.
set /p REPO_URL="Enter GitHub Repo URL: "

if "%REPO_URL%"=="" (
    echo [ERROR] No URL entered. Aborted.
    pause
    exit /b 1
)

echo.
echo Connecting remote origin to: %REPO_URL%
"C:\Program Files\Git\cmd\git.exe" remote remove origin 2>nul
"C:\Program Files\Git\cmd\git.exe" remote add origin %REPO_URL%

echo.
echo Pushing branch 'main' to GitHub...
"C:\Program Files\Git\cmd\git.exe" push -u origin main

if %ERRORLEVEL% EQU 0 (
    echo.
    echo =====================================================================
    echo [SUCCESS] Your repository is now live on GitHub!
    echo You can now connect it directly to Render.com or Railway.
    echo =====================================================================
) else (
    echo.
    echo [NOTE] If prompted for GitHub login, enter your GitHub Personal Access Token
    echo or sign in via browser.
)

pause

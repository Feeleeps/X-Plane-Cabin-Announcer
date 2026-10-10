@echo off
title X-Plane Cabin Announcer
cd /d "%~dp0"

echo ========================================================
echo            X-PLANE 12 CABIN ANNOUNCER
echo ========================================================
echo.

where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python was not found in PATH!
    echo Please ensure Python is installed and added to PATH.
    pause
    exit /b 1
)

echo Starting X-Plane Cabin Announcer...
start "" pythonw main.py
if %ERRORLEVEL% neq 0 (
    echo Falling back to standard python launcher...
    python main.py
)
exit

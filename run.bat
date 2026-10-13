@echo off
title X-Plane Cabin Announcer
cd /d "%~dp0"

echo ========================================================
echo            X-PLANE 12 CABIN ANNOUNCER
echo ========================================================
echo.

:: 1. Locate Python executable (check 'python', fallback to 'py')
set "PY_BIN="
where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "PY_BIN=python"
) else (
    where py >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        set "PY_BIN=py"
    )
)

if "%PY_BIN%"=="" (
    echo [ERROR] Python was not found on your system!
    echo.
    echo Please install Python 3.9 or higher from:
    echo   https://www.python.org/downloads/
    echo.
    echo NOTE: During installation, make sure to CHECK the box:
    echo   "[X] Add Python to PATH"
    echo.
    pause
    exit /b 1
)

:: 2. Check if all required packages are installed
%PY_BIN% -c "import customtkinter, sounddevice, soundfile, scipy, numpy, pygame, yaml, PIL, pystray" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [FIRST-TIME SETUP] Required dependencies are missing.
    echo Installing packages from requirements.txt...
    echo This only needs to run once. Please wait...
    echo.
    %PY_BIN% -m pip install -r requirements.txt --prefer-binary
    if %ERRORLEVEL% neq 0 (
        echo.
        echo [ERROR] Failed to install dependencies!
        echo Please ensure you are connected to the internet.
        echo You can try running manually:
        echo   %PY_BIN% -m pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
    echo.
    echo [SUCCESS] Dependencies installed successfully!
    echo.
)

:: 3. Launch application
echo Starting X-Plane Cabin Announcer...
start "" pythonw main.py
if %ERRORLEVEL% neq 0 (
    echo Falling back to standard python launcher...
    %PY_BIN% main.py
)
exit

@echo off
title PACKTWIN Setup
echo ============================================
echo   PACKTWIN — EV Battery Digital Twin
echo   Setting up and starting the app...
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python was not found on this computer.
    echo.
    echo Please install Python first:
    echo   1. Go to https://python.org/downloads
    echo   2. Download and run the installer
    echo   3. IMPORTANT: tick the box that says "Add python.exe to PATH"
    echo      before clicking Install Now
    echo   4. Once installed, double-click this file again
    echo.
    pause
    exit /b
)

echo Installing required packages — this can take a few minutes the first time...
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo Something went wrong installing packages. Scroll up to see the error.
    pause
    exit /b
)

echo.
echo Starting PACKTWIN...
python main.py

pause

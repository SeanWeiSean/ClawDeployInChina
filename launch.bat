@echo off
REM ═══════════════════════════════════════════════════════
REM  MicroClaw Deployer — Windows Launcher
REM  Double-click this file to start the deployment GUI.
REM ═══════════════════════════════════════════════════════

title MicroClaw Deployer

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python 3 is required but not found in PATH.
    echo         Download from https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Launch the GUI
cd /d "%~dp0"
python deploy.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Deployer exited with an error.
    pause
)

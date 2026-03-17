@echo off
title OpenClaw Gateway
set OPENCLAW_STATE_DIR=%~1
set NODE_OPTIONS=--dns-result-order=ipv4first
set NODE_ENV=production
echo [OpenClaw Gateway] config=%OPENCLAW_STATE_DIR%
echo [OpenClaw Gateway] node=%~2
echo.
"%~2" "%~3" gateway run --port %4 --bind loopback --force --allow-unconfigured
echo.
echo [OpenClaw Gateway] exited with code %ERRORLEVEL%
pause

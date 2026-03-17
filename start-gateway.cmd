@echo off
title OpenClaw Gateway
set OPENCLAW_STATE_DIR=%USERPROFILE%\.openclaw
set NODE_OPTIONS=--dns-result-order=ipv4first
set NODE_COMPILE_CACHE=%OPENCLAW_STATE_DIR%\compile-cache
if not exist "%NODE_COMPILE_CACHE%" mkdir "%NODE_COMPILE_CACHE%"

echo ============================================
echo   OpenClaw Gateway Launcher
echo ============================================
echo Config dir: %OPENCLAW_STATE_DIR%
echo Node: %USERPROFILE%\.openclaw-node\node.exe
echo.

REM Kill any leftover gateway
taskkill /F /IM node.exe /T >nul 2>&1
timeout /t 3 /nobreak >nul

echo Starting gateway on port 18789 (verbose)...
echo.
"%USERPROFILE%\.openclaw-node\node.exe" "%USERPROFILE%\.openclaw-node\node_modules\openclaw\openclaw.mjs" gateway run --port 18789 --bind loopback --force --allow-unconfigured --verbose
echo.
echo ============================================
echo   Gateway exited with code %ERRORLEVEL%
echo ============================================
pause

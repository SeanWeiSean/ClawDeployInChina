# One-click build: desktop app -> portable zip -> installer exe
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

# Step 1: Build & pack Electron app
Write-Host "`n=== Step 1/3: Build & pack desktop ===" -ForegroundColor Cyan
Push-Location "$root\desktop"
npm run pack
Pop-Location

# Step 2: Create portable zip
Write-Host "`n=== Step 2/3: Create microclaw-portable.zip ===" -ForegroundColor Cyan
$zipPath = "$root\dist\microclaw-portable.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path "$root\desktop\release\win-unpacked\*" -DestinationPath $zipPath
Write-Host "  -> $zipPath ($([math]::Round((Get-Item $zipPath).Length / 1MB, 1)) MB)"

# Step 3: Build installer exe
Write-Host "`n=== Step 3/3: Build installer exe ===" -ForegroundColor Cyan
Push-Location $root
pyinstaller OpenClawDeployer.spec --noconfirm
Pop-Location

Write-Host "`n=== Done ===" -ForegroundColor Green
Write-Host "  Installer: $root\dist\MicroClaw.exe"
Write-Host "  Portable:  $zipPath"

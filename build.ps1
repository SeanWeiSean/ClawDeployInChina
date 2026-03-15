# One-click build: desktop app -> portable zip -> installer exe
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

# Use the bundled Node (v22) instead of the outdated system Node
$openclawNode = "$env:USERPROFILE\.openclaw-node"
if (Test-Path $openclawNode) {
    $env:PATH = "$openclawNode;$env:PATH"
    Write-Host "  Using Node: $openclawNode ($(& node --version))"
}

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
$pyinstaller = Get-Command pyinstaller -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty Source
if (-not $pyinstaller) {
    # Try known venv locations (USERPROFILE may differ from actual home)
    $homeDir = [System.IO.Path]::GetDirectoryName([System.IO.Path]::GetDirectoryName($root))
    $candidates = @(
        "$homeDir\PycharmProjects\gpt\venv\Scripts\pyinstaller.exe",
        "C:\Users\yuxwei\PycharmProjects\gpt\venv\Scripts\pyinstaller.exe",
        "$env:USERPROFILE\PycharmProjects\gpt\venv\Scripts\pyinstaller.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { $pyinstaller = $c; break }
    }
}
if (Test-Path $pyinstaller) {
    & $pyinstaller OpenClawDeployer.spec --noconfirm
} else {
    Write-Host "  WARNING: pyinstaller not found, skipping installer build" -ForegroundColor Yellow
}
Pop-Location

Write-Host "`n=== Done ===" -ForegroundColor Green
Write-Host "  Installer: $root\dist\MicroClawInstaller.exe"
Write-Host "  Portable:  $zipPath"

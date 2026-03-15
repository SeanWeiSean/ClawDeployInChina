<#
.SYNOPSIS
    Browser control via Playwright.
.DESCRIPTION
    Forwards to browser-control.js which uses Playwright for browser automation.
    Playwright must be installed: npm install -g playwright && npx playwright install chromium
.PARAMETER Action
    The action to perform: navigate, screenshot, extract, click, fill, evaluate
.PARAMETER Params
    JSON string of parameters for the action.
.EXAMPLE
    pwsh browser-control.ps1 navigate '{"url":"https://example.com"}'
    pwsh browser-control.ps1 screenshot '{"url":"https://example.com","output":"shot.png"}'
#>
param(
    [Parameter(Mandatory=$true, Position=0)]
    [ValidateSet("navigate", "screenshot", "extract", "click", "fill", "evaluate")]
    [string]$Action,

    [Parameter(Mandatory=$true, Position=1)]
    [string]$Params
)

$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$jsScript = Join-Path $scriptDir "browser-control.js"

# Find node — prefer managed install, fall back to system
$managedNode = Join-Path $env:USERPROFILE ".openclaw-node\node.exe"
if (Test-Path $managedNode) {
    $nodeExe = $managedNode
} else {
    $nodeExe = (Get-Command node -ErrorAction SilentlyContinue).Source
    if (-not $nodeExe) {
        Write-Error "node not found. Please install Node.js."
        exit 1
    }
}

# Set NODE_PATH so globally installed playwright is found
$npmRoot = & $nodeExe -e "console.log(require('child_process').execSync('npm root -g').toString().trim())" 2>$null
if ($npmRoot) {
    $env:NODE_PATH = $npmRoot
}

& $nodeExe $jsScript $Action $Params

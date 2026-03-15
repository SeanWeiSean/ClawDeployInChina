#!/usr/bin/env pwsh
# mcp-call.ps1 — Call an MCP tool on the M365Connector server (Streamable HTTP MCP)
# Usage: pwsh mcp-call.ps1 <tool_name> '<params_json>'

param(
    [Parameter(Mandatory)][string]$Tool,
    [Parameter(Mandatory)][string]$ParamsJson
)

$ErrorActionPreference = 'Stop'
$McpUrl = "http://127.0.0.1:52366/mcp"
$SessionId = $null

function Parse-SseResponse {
    param([string]$Content)
    $lines = $Content -split "`n"
    foreach ($line in $lines) {
        if ($line -match "^data:\s*(.+)$") {
            $payload = $Matches[1].Trim()
            try {
                $parsed = $payload | ConvertFrom-Json -ErrorAction Stop
                if ($null -ne $parsed.result -or $null -ne $parsed.error) {
                    return $parsed
                }
            } catch { }
        }
    }
    return $null
}

function Send-Mcp {
    param([string]$Body)
    $h = @{
        "Content-Type" = "application/json"
        "Accept"       = "application/json, text/event-stream"
    }
    if ($script:SessionId) { $h["mcp-session-id"] = $script:SessionId }

    $resp = Invoke-WebRequest -Uri $McpUrl -Method POST -Headers $h -Body $Body -TimeoutSec 120 -UseBasicParsing

    # Extract session id (case-insensitive header lookup)
    foreach ($key in $resp.Headers.Keys) {
        if ($key -ieq "mcp-session-id") {
            $script:SessionId = $resp.Headers[$key]
            if ($script:SessionId -is [array]) { $script:SessionId = $script:SessionId[0] }
            break
        }
    }

    $ct = ""
    foreach ($key in $resp.Headers.Keys) {
        if ($key -ieq "content-type") { $ct = "$($resp.Headers[$key])"; break }
    }

    if ($ct -match "text/event-stream") {
        return (Parse-SseResponse -Content $resp.Content)
    } else {
        return ($resp.Content | ConvertFrom-Json)
    }
}

# 1) initialize
$r = Send-Mcp -Body ('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"openclaw-workiq","version":"1.0.0"}}}')
if ($r.error) { Write-Error "Init failed: $($r.error.message)"; exit 1 }

# 2) notifications/initialized
try { Send-Mcp -Body '{"jsonrpc":"2.0","method":"notifications/initialized"}' | Out-Null } catch { }

# 3) tools/call
$call = @{
    jsonrpc = "2.0"; id = 2; method = "tools/call"
    params = @{ name = $Tool; arguments = ($ParamsJson | ConvertFrom-Json) }
} | ConvertTo-Json -Depth 10

$r = Send-Mcp -Body $call
if ($r.error) { Write-Error "MCP error [$($r.error.code)]: $($r.error.message)"; exit 1 }
$r.result | ConvertTo-Json -Depth 20

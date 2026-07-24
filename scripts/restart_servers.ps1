# Restarts the FastAPI backend (port 8000) and/or Next.js frontend (port 3000).
#
# Why this exists: uvicorn --reload spawns a reloader process plus a separate
# worker process that actually holds the socket. Killing only the reloader
# PID (e.g. from Task Manager or `Stop-Process <reloader-pid>`) leaves the
# worker orphaned — it keeps the port and keeps serving requests with
# whatever .env/code it started with, so a ".env edit + restart" silently
# does nothing. This script always kills by PORT (whoever is actually
# listening), never by a remembered PID, so it can't leave a stale orphan
# behind.
#
# Usage:
#   powershell -File scripts\restart_servers.ps1            # both
#   powershell -File scripts\restart_servers.ps1 -Backend   # backend only
#   powershell -File scripts\restart_servers.ps1 -Frontend  # frontend only

param(
    [switch]$Backend,
    [switch]$Frontend
)

if (-not $Backend -and -not $Frontend) {
    $Backend = $true
    $Frontend = $true
}

$RepoRoot = Split-Path -Parent $PSScriptRoot

function Stop-Port {
    param([int]$Port)
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        Write-Host "Killing PID $($c.OwningProcess) listening on port $Port"
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
    }
    # give Windows a moment to actually release the socket
    Start-Sleep -Milliseconds 500
}

if ($Backend) {
    Stop-Port -Port 8000
    Write-Host "Starting backend on :8000..."
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command",
        "cd '$RepoRoot'; uvicorn api.server:app --port 8000 --reload"
    )
}

if ($Frontend) {
    Stop-Port -Port 3000
    Write-Host "Starting frontend on :3000..."
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command",
        "cd '$RepoRoot\frontend'; npm run dev"
    )
}

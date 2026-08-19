# Restarts the FastAPI backend (port 8000) and/or Next.js frontend (port 3000).
#
# Why this exists: `uvicorn --reload` spawns a reloader process PLUS a separate
# multiprocessing worker that actually holds the socket. Killing one and not the
# other silently breaks a restart in two different ways:
#
#   * kill the reloader only  -> the worker is orphaned, keeps the port, and
#     keeps serving the OLD code/.env. A ".env edit + restart" does nothing.
#   * kill the worker only    -> the reloader immediately respawns a new worker,
#     which grabs the port back before the replacement server can bind.
#
# Worse, `Get-NetTCPConnection` can report the RELOADER's pid as OwningProcess
# while the worker is the process actually holding the socket, so killing "the
# pid listening on the port" can kill something already dead and leave the real
# holder running. That is not hypothetical — it is what made an earlier version
# of this script report "Killing PID 9652" twice while a worker with
# parent_pid=9652 carried on serving stale responses.
#
# So this script:
#   1. resolves the port owner, then walks the process tree BOTH ways — up to a
#      recognisable server ancestor, and down through children AND through
#      `parent_pid=<n>` recorded in orphaned workers' command lines,
#   2. kills that whole set,
#   3. WAITS for the port to actually be released and aborts loudly if it is
#      not, rather than starting a server that cannot bind and leaving you
#      talking to the old one,
#   4. waits for the new server to answer and says so.
#
# Note on blast radius: the upward walk stops as soon as a parent's command line
# does NOT match the server pattern, but the `-NoExit` PowerShell window this
# script launches DOES match (it has "uvicorn ..." on its command line), so a
# restart closes that host window too. That is deliberate — otherwise every
# restart leaves a dead shell behind. The consequence to know about: if you ever
# start uvicorn by hand from a terminal you are also using for other work, a
# restart will close that terminal.
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

function Get-PortOwners {
    param([int]$Port)
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) { return @() }
    return @($conns.OwningProcess | Sort-Object -Unique | ForEach-Object { [int]$_ })
}

function Test-PortFree {
    param([int]$Port)
    return -not (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

# Every pid belonging to the server holding $Port: the socket owner, any
# ancestor that looks like this server, and everything descended from those --
# including orphaned multiprocessing workers, which record parent_pid=<n> in
# their command line and so are still findable after their parent has died.
function Get-ServerProcessTree {
    param([int]$Port, [string]$Pattern)

    $all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
             Select-Object ProcessId, ParentProcessId, CommandLine)
    $byId = @{}
    foreach ($p in $all) { $byId[[int]$p.ProcessId] = $p }

    $targets = New-Object 'System.Collections.Generic.HashSet[int]'
    foreach ($o in (Get-PortOwners -Port $Port)) { [void]$targets.Add($o) }

    # Walk UP: include a parent only if it is recognisably this server, so we
    # never climb into explorer.exe or the shell that launched us.
    foreach ($seed in @($targets)) {
        $cur = $seed
        for ($hop = 0; $hop -lt 6; $hop++) {
            if (-not $byId.ContainsKey($cur)) { break }
            $parent = [int]$byId[$cur].ParentProcessId
            if ($parent -le 0 -or -not $byId.ContainsKey($parent)) { break }
            if ($byId[$parent].CommandLine -notmatch $Pattern) { break }
            [void]$targets.Add($parent)
            $cur = $parent
        }
    }

    # Walk DOWN: real children, plus orphans that still name one of our targets
    # as parent_pid in their command line.
    $queue = New-Object 'System.Collections.Generic.Queue[int]'
    foreach ($t in $targets) { $queue.Enqueue($t) }
    while ($queue.Count -gt 0) {
        $cur = $queue.Dequeue()
        foreach ($p in $all) {
            $pid_ = [int]$p.ProcessId
            if ($targets.Contains($pid_)) { continue }
            $isChild  = ([int]$p.ParentProcessId -eq $cur)
            $isOrphan = ($p.CommandLine -and $p.CommandLine -match "parent_pid=$cur(\D|$)")
            if ($isChild -or $isOrphan) {
                [void]$targets.Add($pid_)
                $queue.Enqueue($pid_)
            }
        }
    }
    return @($targets)
}

function Stop-Port {
    param(
        [int]$Port,
        [string]$Pattern,
        [int]$TimeoutSeconds = 20
    )

    if (Test-PortFree -Port $Port) {
        Write-Host "Port $Port already free."
        return $true
    }

    $targets = Get-ServerProcessTree -Port $Port -Pattern $Pattern
    if ($targets.Count -gt 0) {
        Write-Host "Port ${Port}: stopping $($targets.Count) process(es) -> $($targets -join ', ')"
        foreach ($t in $targets) {
            Stop-Process -Id $t -Force -ErrorAction SilentlyContinue
        }
    }

    # Wait for the socket to actually be released. Re-sweep as we go: killing a
    # reloader can spawn a replacement worker a moment later.
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortFree -Port $Port) {
            Write-Host "Port $Port released."
            return $true
        }
        Start-Sleep -Milliseconds 500
        foreach ($t in (Get-ServerProcessTree -Port $Port -Pattern $Pattern)) {
            Stop-Process -Id $t -Force -ErrorAction SilentlyContinue
        }
    }

    Write-Error @"
Port $Port is STILL held after ${TimeoutSeconds}s. NOT starting a replacement --
it could not bind, and you would be talking to the old server while believing
you had restarted it. Investigate with:
  Get-NetTCPConnection -LocalPort $Port -State Listen
  Get-CimInstance Win32_Process | Where-Object { `$_.CommandLine -match '$Pattern' } | Select-Object ProcessId, CommandLine
"@
    return $false
}

function Wait-Health {
    param([string]$Url, [string]$Name, [int]$TimeoutSeconds = 90)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $Url -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
            if ($r.StatusCode -eq 200) {
                Write-Host "$Name is up ($Url)."
                return $true
            }
        } catch {
            # 401/503 mean the app is up and answering — the probe just sends
            # no API key. Only a connection failure means "not started yet",
            # so an authenticated endpoint must not read as a dead server.
            $code = $_.Exception.Response.StatusCode.value__
            if ($code -eq 401 -or $code -eq 503) {
                Write-Host "$Name is up ($Url, HTTP $code - auth required)."
                return $true
            }
        }
        Start-Sleep -Seconds 1
    }
    Write-Warning "$Name did not answer $Url within ${TimeoutSeconds}s - check its window for a startup error."
    return $false
}

$ok = $true

if ($Backend) {
    # multiprocessing-fork catches the orphaned uvicorn worker specifically.
    $pattern = 'uvicorn|api\.server|multiprocessing-fork'
    if (Stop-Port -Port 8000 -Pattern $pattern) {
        Write-Host "Starting backend on :8000..."
        Start-Process powershell -ArgumentList @(
            "-NoExit", "-Command",
            "cd '$RepoRoot'; uvicorn api.server:app --port 8000 --reload"
        )
        if (-not (Wait-Health -Url "http://127.0.0.1:8000/api/meta" -Name "Backend")) { $ok = $false }
    } else { $ok = $false }
}

if ($Frontend) {
    $pattern = 'next|npm run dev|node.*dev'
    if (Stop-Port -Port 3000 -Pattern $pattern) {
        Write-Host "Starting frontend on :3000..."
        Start-Process powershell -ArgumentList @(
            "-NoExit", "-Command",
            "cd '$RepoRoot\frontend'; npm run dev"
        )
        # First dev compile after a cold start can take a while.
        if (-not (Wait-Health -Url "http://127.0.0.1:3000/" -Name "Frontend" -TimeoutSeconds 120)) { $ok = $false }
    } else { $ok = $false }
}

if (-not $ok) { exit 1 }

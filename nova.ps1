[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('start','stop','status','doctor','logs','config','target','backup','upgrade','rollback','support-bundle','dx','help')]
    [string]$Command = 'help',
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ComposeFile = Join-Path $Root 'compose.dev.yml'
$StateDir = Join-Path $Root 'data\operator'
$LiteStatePath = Join-Path $StateDir 'lite-processes.json'
$LogDir = Join-Path $StateDir 'logs'
$ApiBase = 'http://127.0.0.1:8788/api/v1'
$WebUrl = 'http://127.0.0.1:8787'

function Write-Step([string]$Code, [string]$Message, [ConsoleColor]$Color = [ConsoleColor]::Cyan) {
    Write-Host "[$Code] $Message" -ForegroundColor $Color
}

function Fail-Nova([string]$Code, [string]$Problem, [string]$Cause, [string]$Fix) {
    Write-Host "$Code $Problem" -ForegroundColor Red
    Write-Host "Cause: $Cause"
    Write-Host "Fix:   $Fix" -ForegroundColor Yellow
    Write-Host "Help:  .\nova.ps1 doctor --explain $Code"
    exit 1
}

function Test-Command([string]$Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-FreePort([int]$Port) {
    $listeners = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue
    return -not ($listeners | Where-Object { $_.LocalPort -eq $Port })
}

function Test-DockerReady {
    if (-not (Test-Command 'docker')) { return $false }
    try {
        & docker version --format '{{.Server.Version}}' 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

function Get-LiteState {
    if (-not (Test-Path -LiteralPath $LiteStatePath)) { return $null }
    try { return Get-Content -LiteralPath $LiteStatePath -Raw | ConvertFrom-Json } catch { return $null }
}

function Test-OwnedProcess([int]$ProcessId, [string]$StartedAt) {
    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $process) { return $false }
    try {
        return [math]::Abs(($process.StartTime - [datetime]$StartedAt).TotalSeconds) -lt 2
    } catch { return $false }
}

function Stop-OwnedProcess([int]$ProcessId, [string]$StartedAt) {
    if (Test-OwnedProcess $ProcessId $StartedAt) {
        $allProcesses = Get-CimInstance Win32_Process
        $frontier = @($ProcessId)
        $descendants = @()
        while ($frontier.Count -gt 0) {
            $children = @($allProcesses | Where-Object { $_.ParentProcessId -in $frontier })
            if ($children.Count -eq 0) { break }
            $childIds = @($children | ForEach-Object { [int]$_.ProcessId })
            $descendants += $childIds
            $frontier = $childIds
        }
        [array]::Reverse($descendants)
        @($descendants) + @($ProcessId) | ForEach-Object {
            Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
        }
    }
}

function Invoke-Doctor([switch]$Json) {
    $checks = [ordered]@{}
    $checks.docker_cli = Test-Command 'docker'
    $checks.docker_engine = $false
    $checks.compose_v2 = $false
    $checks.uv = Test-Command 'uv'
    $checks.pnpm = Test-Command 'pnpm'
    $checks.port_8787 = Get-FreePort 8787
    $checks.port_8788 = Get-FreePort 8788
    $checks.free_disk_gb = [math]::Round((Get-PSDrive -Name ([IO.Path]::GetPathRoot($Root).Substring(0,1))).Free / 1GB, 1)

    if ($checks.docker_cli) {
        try {
            & docker version --format '{{.Server.Version}}' 2>$null | Out-Null
            $checks.docker_engine = ($LASTEXITCODE -eq 0)
        } catch { $checks.docker_engine = $false }
        try {
            & docker compose version --short 2>$null | Out-Null
            $checks.compose_v2 = ($LASTEXITCODE -eq 0)
        } catch { $checks.compose_v2 = $false }
    }

    $checks.docker_ready = $checks.docker_cli -and $checks.docker_engine -and $checks.compose_v2 -and $checks.free_disk_gb -ge 5
    $checks.lite_ready = $checks.uv -and $checks.pnpm -and $checks.free_disk_gb -ge 2
    $checks.ready = $checks.docker_ready -or $checks.lite_ready
    if ($Json) {
        $checks | ConvertTo-Json
        if (-not $checks.ready) { exit 1 }
        return
    }

    Write-Step 'doctor' "Docker CLI ............ $(if ($checks.docker_cli) {'OK'} else {'MISSING'})"
    Write-Step 'doctor' "Docker engine ......... $(if ($checks.docker_engine) {'OK'} else {'NOT RUNNING'})"
    Write-Step 'doctor' "Compose v2 ............ $(if ($checks.compose_v2) {'OK'} else {'MISSING'})"
    Write-Step 'doctor' "uv + pnpm ............. $(if ($checks.lite_ready) {'OK (Lite available)'} else {'MISSING'})"
    Write-Step 'doctor' "Free disk ............. $($checks.free_disk_gb) GB"
    if (-not $checks.ready) {
        Fail-Nova 'NOVA-DOC-1002' 'No local runtime is ready.' 'Docker is unavailable and the Lite prerequisites (uv + pnpm + 2 GB disk) are incomplete.' 'Install uv and pnpm, or start Docker Desktop, then run .\nova.ps1 doctor again.'
    }
    if (-not $checks.docker_ready) { Write-Step 'doctor' 'Docker is off; start will automatically use the zero-cost Lite profile.' Yellow }
    Write-Step 'doctor' 'All required checks passed.' Green
}

function Start-Lite {
    New-Item -ItemType Directory -Force -Path $StateDir, $LogDir | Out-Null
    $existing = Get-LiteState
    if ($existing -and (Test-OwnedProcess $existing.api_pid $existing.api_started_at) -and (Test-OwnedProcess $existing.web_pid $existing.web_started_at)) {
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8788/healthz' -TimeoutSec 2
            $webReady = (Invoke-WebRequest -Uri $WebUrl -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200
            if ($health.status -eq 'ok' -and $webReady) {
                Write-Step 'lite' "NOVA Lite is already running: $WebUrl" Green
                return
            }
        } catch {}
    }
    if ($existing) {
        Stop-OwnedProcess $existing.api_pid $existing.api_started_at
        Stop-OwnedProcess $existing.web_pid $existing.web_started_at
        Remove-Item -LiteralPath $LiteStatePath -ErrorAction SilentlyContinue
    }

    $databasePath = (Join-Path $Root 'data\nova-lite.db').Replace('\', '/')
    $storagePath = Join-Path $Root 'data\artifacts'
    $env:NOVA_PROFILE = 'lite'
    $env:NOVA_DATABASE_URL = "sqlite:///$databasePath"
    $env:NOVA_STORAGE_DIR = $storagePath

    $apiOut = Join-Path $LogDir 'api.out.log'
    $apiErr = Join-Path $LogDir 'api.err.log'
    $webOut = Join-Path $LogDir 'web.out.log'
    $webErr = Join-Path $LogDir 'web.err.log'
    $api = $null
    $web = $null
    try {
        $api = Start-Process -FilePath (Get-Command uv).Source -ArgumentList @('run','--project',(Join-Path $Root 'backend'),'uvicorn','nova.main:app','--host','127.0.0.1','--port','8788') -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $apiOut -RedirectStandardError $apiErr -PassThru
        $pnpmCommand = Get-Command pnpm.cmd -CommandType Application -ErrorAction Stop | Select-Object -First 1
        $web = Start-Process -FilePath $pnpmCommand.Source -ArgumentList @('--filter','@nova/web','dev','--','--host','127.0.0.1','--port','8787') -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $webOut -RedirectStandardError $webErr -PassThru
    } catch {
        if ($api) { Stop-OwnedProcess $api.Id $api.StartTime.ToString('o') }
        if ($web) { Stop-OwnedProcess $web.Id $web.StartTime.ToString('o') }
        Fail-Nova 'NOVA-BOOT-1004' 'The Lite profile could not start its local processes.' $_.Exception.Message 'Verify uv and pnpm.cmd are available, then run .\nova.ps1 start --lite again.'
    }

    $state = [ordered]@{
        profile = 'lite'
        api_pid = $api.Id
        api_started_at = $api.StartTime.ToString('o')
        web_pid = $web.Id
        web_started_at = $web.StartTime.ToString('o')
    }
    $state | ConvertTo-Json | Set-Content -LiteralPath $LiteStatePath -Encoding utf8

    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8788/healthz' -TimeoutSec 2
            $webReady = (Invoke-WebRequest -Uri $WebUrl -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200
            if ($health.status -eq 'ok' -and $webReady) { return }
        } catch {}
        Start-Sleep -Milliseconds 500
    }

    Stop-OwnedProcess $api.Id $state.api_started_at
    Stop-OwnedProcess $web.Id $state.web_started_at
    Remove-Item -LiteralPath $LiteStatePath -ErrorAction SilentlyContinue
    Fail-Nova 'NOVA-BOOT-1004' 'The Lite profile did not become healthy.' 'The native API or web process exited during startup.' '.\nova.ps1 logs api'
}

function Invoke-Api([string]$Path, [string]$Method = 'GET') {
    try {
        return Invoke-RestMethod -Uri "$ApiBase$Path" -Method $Method -TimeoutSec 15
    } catch {
        Fail-Nova 'NOVA-API-1001' 'NOVA API is not reachable.' $_.Exception.Message 'Run .\nova.ps1 status, then .\nova.ps1 logs api.'
    }
}

function Show-Help {
    @'
NOVA operator CLI

  .\nova.ps1 start [--lite]        Start; automatically uses Lite when Docker is off
  .\nova.ps1 stop                  Stop dev services without deleting data
  .\nova.ps1 status                Show container and engine health
  .\nova.ps1 doctor [--json]       Diagnose Docker and zero-cost Lite runtimes
  .\nova.ps1 logs [service]        Follow logs (api, web, postgres)
  .\nova.ps1 config validate       Validate Compose configuration
  .\nova.ps1 target list|test ID   Inspect or probe engine deployments
  .\nova.ps1 backup create|list    Back up PostgreSQL metadata
  .\nova.ps1 upgrade --check       Verify upstream locks and local readiness
  .\nova.ps1 support-bundle        Create a redacted local diagnostic bundle
  .\nova.ps1 dx report             Show local onboarding timing evidence
'@ | Write-Host
}

switch ($Command) {
    'doctor' {
        if ($Rest -contains '--explain') {
            Write-Host 'NOVA-DOC-1002: Docker Desktop must be installed and its engine running. NOVA requires Compose v2 and at least 5 GB free disk.'
            exit 0
        }
        Invoke-Doctor -Json:($Rest -contains '--json')
    }
    'start' {
        $started = Get-Date
        Invoke-Doctor
        New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
        $lite = ($Rest -contains '--lite') -or -not (Test-DockerReady)
        if ($lite) {
            Write-Step '1/4' 'Starting zero-cost Lite profile (SQLite + local web)...'
            Start-Lite
        } else {
            Write-Step '1/4' 'Building the NOVA web workspace...'
            Push-Location $Root
            try { pnpm --filter @nova/web build } finally { Pop-Location }
            if ($LASTEXITCODE -ne 0) { Fail-Nova 'NOVA-BOOT-1003' 'The web workspace did not build.' 'TypeScript or Vite returned an error.' 'pnpm --filter @nova/web build' }
            Write-Step '2/4' 'Building and starting NOVA dev profile...'
            docker compose -f $ComposeFile up -d --build --wait
            if ($LASTEXITCODE -ne 0) { Fail-Nova 'NOVA-BOOT-1001' 'The dev profile did not become healthy.' 'One or more containers failed to build or start.' '.\nova.ps1 logs api' }
        }
        Write-Step '3/4' 'Services are healthy.' Green
        $elapsed = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
        @{ started_at = $started.ToString('o'); health_ready_seconds = $elapsed; profile = $(if ($lite) {'lite'} else {'dev'}) } | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $StateDir 'last-start.json')
        Write-Step '4/4' "NOVA ready in ${elapsed}s: $WebUrl" Green
        if ($Rest -notcontains '--no-open') { Start-Process $WebUrl }
    }
    'stop' {
        $state = Get-LiteState
        if ($state) {
            Stop-OwnedProcess $state.api_pid $state.api_started_at
            Stop-OwnedProcess $state.web_pid $state.web_started_at
            Remove-Item -LiteralPath $LiteStatePath -ErrorAction SilentlyContinue
            Write-Step 'stop' 'NOVA Lite processes stopped. Data was preserved.' Green
        } elseif (Test-DockerReady) { docker compose -f $ComposeFile down }
        else { Write-Host 'NOVA is not running.' }
    }
    'status' {
        $state = Get-LiteState
        if ($state) {
            Write-Host "Lite API PID $($state.api_pid): $(if (Test-OwnedProcess $state.api_pid $state.api_started_at) {'running'} else {'stopped'})"
            Write-Host "Lite Web PID $($state.web_pid): $(if (Test-OwnedProcess $state.web_pid $state.web_started_at) {'running'} else {'stopped'})"
        } elseif (Test-DockerReady) { docker compose -f $ComposeFile ps }
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8788/healthz' -TimeoutSec 3
            Write-Host ($health | ConvertTo-Json -Depth 5)
        } catch { Write-Host 'API health unavailable.' -ForegroundColor Yellow }
    }
    'logs' {
        $service = if ($Rest.Count -gt 0) { $Rest[0] } else { 'api' }
        if (Get-LiteState) {
            Get-Content -LiteralPath @((Join-Path $LogDir "$service.out.log"), (Join-Path $LogDir "$service.err.log")) -Tail 200 -Wait
        } else { docker compose -f $ComposeFile logs --tail 200 -f $service }
    }
    'config' {
        if ($Rest[0] -ne 'validate') { Fail-Nova 'NOVA-CLI-1001' 'Unknown config action.' 'Only config validate is available in v0.1.' '.\nova.ps1 config validate' }
        docker compose -f $ComposeFile config --quiet
        if ($LASTEXITCODE -eq 0) { Write-Step 'config' 'Compose configuration is valid.' Green }
    }
    'target' {
        switch ($Rest[0]) {
            'list' { Invoke-Api '/engine-deployments' | ConvertTo-Json -Depth 8 }
            'test' {
                if ($Rest.Count -lt 2) { Fail-Nova 'NOVA-CLI-1002' 'A target ID is required.' 'No deployment ID was supplied.' '.\nova.ps1 target test mock-render' }
                Invoke-Api "/engine-deployments/$($Rest[1])/probe" 'POST' | ConvertTo-Json -Depth 8
            }
            default { Write-Host 'target bootstrap/add/reconcile require a configured full-profile adapter; target list/test work in dev.' }
        }
    }
    'backup' {
        New-Item -ItemType Directory -Force -Path (Join-Path $Root 'data\backups') | Out-Null
        if ($Rest[0] -eq 'list') { Get-ChildItem (Join-Path $Root 'data\backups') -Filter '*.sql' -ErrorAction SilentlyContinue; break }
        if ($Rest[0] -ne 'create') { Fail-Nova 'NOVA-CLI-1003' 'Unknown backup action.' 'Use create or list.' '.\nova.ps1 backup create' }
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $path = Join-Path $Root "data\backups\nova-$stamp.sql"
        docker compose -f $ComposeFile exec -T postgres pg_dump -U nova -d nova | Set-Content -Encoding utf8 $path
        Write-Step 'backup' "Created $path" Green
    }
    'upgrade' {
        if ($Rest -notcontains '--check') { Write-Host 'Upgrade execution is intentionally gated until signed release images exist. Use --check.'; break }
        Invoke-Doctor
        $lock = Get-Content (Join-Path $Root 'upstream-lock.yml') -Raw
        if ($lock -match 'UNRESOLVED_NETWORK_GATE') {
            Write-Host 'NOVA-UPG-2001 Upstream commit locks are unresolved; real-engine upgrade is blocked.' -ForegroundColor Yellow
        } else { Write-Step 'upgrade' 'Upstream locks are resolved.' Green }
    }
    'support-bundle' {
        $bundle = Join-Path $Root ("data\support-bundle-" + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.txt')
        New-Item -ItemType Directory -Force -Path (Split-Path $bundle) | Out-Null
        @('NOVA redacted support bundle', (Get-Date).ToString('o'), (docker --version), (docker compose version)) | Set-Content -Encoding utf8 $bundle
        docker compose -f $ComposeFile ps --format json 2>&1 | Add-Content -Encoding utf8 $bundle
        Write-Step 'support' "Created $bundle. Media, cookies, keys and signed URLs are not included." Green
    }
    'dx' {
        if ($Rest[0] -ne 'report') { Fail-Nova 'NOVA-CLI-1004' 'Unknown DX action.' 'Only dx report is available.' '.\nova.ps1 dx report' }
        $path = Join-Path $StateDir 'last-start.json'
        if (Test-Path $path) { Get-Content $path } else { Write-Host 'No local start timing has been recorded yet.' }
    }
    'rollback' { Write-Host 'Rollback is gated until the first signed release exists.' }
    default { Show-Help }
}

<#
Starts, stops or checks all implemented local APIs and workers in the background.

  powershell -ExecutionPolicy Bypass -File dev/local_stack.ps1 start
  powershell -ExecutionPolicy Bypass -File dev/local_stack.ps1 status
  powershell -ExecutionPolicy Bypass -File dev/local_stack.ps1 stop

Assumes the one-time setup in docs/I01-local-journey.md and docs/I02-local-journey.md
is done: containers created, schemas migrated, service .env files and venvs in place.
Logs and PIDs go to .local/stack/. Containers are left running on stop.
#>
param(
    [ValidateSet('start', 'stop', 'status')]
    [string]$Action = 'start',
    # Serve a built frontend without Vite's live-update websocket/reload client.
    [switch]$StableFrontend,
    # Stripe CLI executable; skipped with a warning when not found.
    [string]$StripeCli = 'stripe'
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$StateDir = Join-Path $Root '.local\stack'

function Venv($service) { Join-Path $Root "services\$service\.venv\Scripts\python.exe" }

# APIs first (with ports), then workers.
$Apis = @(
    @{ Name = 'identity';     Dir = 'services\identity';         Exe = (Venv identity);         Args = '-m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8001'; Port = 8001 }
    @{ Name = 'tenant';       Dir = 'services\tenant';           Exe = (Venv identity);         Args = '-m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8002'; Port = 8002 }
    @{ Name = 'scheduling';   Dir = 'services\scheduling';       Exe = (Venv scheduling);       Args = '-m app'; Port = 8003 }
    @{ Name = 'consultation'; Dir = 'services\consultation';     Exe = (Venv consultation);     Args = '-m app'; Port = 8004 }
    @{ Name = 'records';      Dir = 'services\clinical_records'; Exe = (Venv clinical_records); Args = '-m app'; Port = 8005 }
    @{ Name = 'fulfilment';   Dir = 'services\fulfilment';       Exe = (Venv fulfilment);       Args = '-m app'; Port = 8006 }
    @{ Name = 'document';     Dir = 'services\document';         Exe = (Venv document);         Args = '-m uvicorn app.main:create_app --factory --port 8007 --no-access-log'; Port = 8007 }
    @{ Name = 'billing';      Dir = 'services\billing';          Exe = (Venv billing);          Args = '-m app'; Port = 8009 }
    @{ Name = 'vite';         Dir = 'apps\web';                  Exe = 'npm.cmd';               Args = 'run dev -- --host 0.0.0.0'; Port = 5173 }
)
$Workers = @(
    @{ Name = 'sched-expiry';       Dir = 'services\scheduling';       Exe = (Venv scheduling);       Args = '-m app.expire_holds' }
    @{ Name = 'sched-consumer';     Dir = 'services\scheduling';       Exe = (Venv scheduling);       Args = '-m app.payment_worker' }
    @{ Name = 'sched-publisher';    Dir = 'services\scheduling';       Exe = (Venv scheduling);       Args = '-m app.payment_worker --publish' }
    @{ Name = 'sched-resolver';     Dir = 'services\scheduling';       Exe = (Venv scheduling);       Args = '-m app.payment_worker --resolve' }
    @{ Name = 'bill-expiry';        Dir = 'services\billing';          Exe = (Venv billing);          Args = '-m app.expire_checkouts' }
    @{ Name = 'bill-processor';     Dir = 'services\billing';          Exe = (Venv billing);          Args = '-m app.payment_worker' }
    @{ Name = 'bill-publisher';     Dir = 'services\billing';          Exe = (Venv billing);          Args = '-m app.payment_worker --publish' }
    @{ Name = 'fulfilment-payment-worker'; Dir = 'services\fulfilment'; Exe = (Venv fulfilment); Args = '-m app.payment_worker' }
    @{ Name = 'delivery-worker';    Dir = 'services\fulfilment';      Exe = (Venv fulfilment);      Args = '-m app.delivery_worker' }
    @{ Name = 'delivery-resolver';  Dir = 'services\fulfilment';      Exe = (Venv fulfilment);      Args = '-m app.delivery_worker --resolve' }
    @{ Name = 'delivery-publisher'; Dir = 'services\fulfilment';      Exe = (Venv fulfilment);      Args = '-m app.delivery_worker --publish' }
    @{ Name = 'delivery-tracker';   Dir = 'services\fulfilment';      Exe = (Venv fulfilment);      Args = '-m app.tracking_worker' }
    @{ Name = 'records-publisher';  Dir = 'services\clinical_records'; Exe = (Venv clinical_records); Args = '-m app.publish_events' }
    @{ Name = 'document-worker';    Dir = 'services\document';         Exe = (Venv document);         Args = '-m app.worker' }
    @{ Name = 'document-publisher'; Dir = 'services\document';         Exe = (Venv document);         Args = '-m app.publish_events' }
    @{ Name = 'notification-worker'; Dir = 'services\notification';   Exe = (Venv notification);     Args = '-m app.worker' }
)
$StripeEvents = 'checkout.session.completed,checkout.session.async_payment_succeeded,checkout.session.async_payment_failed,checkout.session.expired,payment_intent.succeeded,payment_intent.payment_failed'

function PidFile($name) { Join-Path $StateDir "$name.pid" }

function Get-RunningPid($name) {
    $file = PidFile $name
    if (-not (Test-Path $file)) { return $null }
    $id = [int](Get-Content $file)
    if (Get-Process -Id $id -ErrorAction SilentlyContinue) { return $id }
    return $null
}

function Test-Port($port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try { return $client.ConnectAsync('127.0.0.1', $port).Wait(500) } catch { return $false } finally { $client.Dispose() }
}

function Test-Ready($p) {
    if (-not (Test-Port $p.Port)) { return $false }
    $path = if ($p.Name -eq 'vite') { '/' } else { '/health/ready' }
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$($p.Port)$path" -UseBasicParsing -TimeoutSec 5
        return $response.StatusCode -eq 200
    } catch { return $false }
}

function Start-One($p) {
    if (Get-RunningPid $p.Name) { Write-Host "  $($p.Name) already running"; return }
    $proc = Start-Process -FilePath $p.Exe -ArgumentList $p.Args -WorkingDirectory (Join-Path $Root $p.Dir) `
        -RedirectStandardOutput (Join-Path $StateDir "$($p.Name).out.log") `
        -RedirectStandardError (Join-Path $StateDir "$($p.Name).err.log") `
        -WindowStyle Hidden -PassThru
    Set-Content (PidFile $p.Name) $proc.Id
    Write-Host "  started $($p.Name) (pid $($proc.Id))"
}

function Read-DotEnv($path, $key) {
    $line = Get-Content $path | Where-Object { $_ -match "^$key=" } | Select-Object -First 1
    if ($line) { return $line.Substring($key.Length + 1).Trim('"') }
    return $null
}

function Start-Containers {
    Write-Host 'Containers'
    docker start telelink-clinic-postgres | Out-Null
    Push-Location $Root
    try { docker compose up -d redis floci } finally { Pop-Location }
    Push-Location (Join-Path $Root 'services\signalling')
    try { docker compose -f compose.yaml -f compose.app.yaml up -d --wait --wait-timeout 90 } finally { Pop-Location }
    for ($i = 0; $i -lt 30; $i++) {
        docker exec telelink-clinic-postgres pg_isready -U postgres -d telelink 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { return }
        Start-Sleep -Seconds 1
    }
    throw 'telelink-clinic-postgres did not become ready'
}

function Test-StripeContainer {
    try {
        $names = & docker ps --filter 'name=^/telelink-local-stripe-forwarder$' --filter 'status=running' --format '{{.Names}}' 2>$null
        return $names -contains 'telelink-local-stripe-forwarder'
    } catch { return $false }
}

function Start-Stripe {
    if (Test-StripeContainer) { Write-Host '  Stripe forwarder already running (Docker)'; return }
    if (Get-RunningPid 'stripe-listen') { Write-Host '  Stripe forwarder already running'; return }
    if (-not (Get-Command $StripeCli -ErrorAction SilentlyContinue)) {
        Write-Warning "Stripe CLI '$StripeCli' not found; payments will not confirm. Pass -StripeCli <path to stripe.exe>."
        return
    }
    $billingEnv = Join-Path $Root 'services\billing\.env'
    if (-not $env:STRIPE_API_KEY) { $env:STRIPE_API_KEY = Read-DotEnv $billingEnv 'SERVICE_STRIPE_SECRET_KEY' }
    $secret = (& $StripeCli listen --print-secret).Trim()
    if ($secret -ne (Read-DotEnv $billingEnv 'SERVICE_STRIPE_WEBHOOK_SECRET')) {
        Write-Warning 'Stripe webhook signing secret differs from services/billing/.env. Update SERVICE_STRIPE_WEBHOOK_SECRET privately, then restart billing.'
    }
    Start-One @{ Name = 'stripe-listen'; Dir = '.'; Exe = (Get-Command $StripeCli).Source
                 Args = "listen --events $StripeEvents --forward-to http://127.0.0.1:8009/webhooks/stripe" }
}

function Start-Stack {
    New-Item -ItemType Directory -Force $StateDir | Out-Null
    $frontendModePath = Join-Path $StateDir 'frontend-mode.txt'
    $frontendMode = if ($StableFrontend) { 'preview' } elseif (Test-Path $frontendModePath) { (Get-Content $frontendModePath -Raw).Trim() } else { 'dev' }
    if ($frontendMode -eq 'preview') {
        Push-Location (Join-Path $Root 'apps\web')
        try {
            & npm.cmd run build
            if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed; existing frontend left running.' }
        } finally { Pop-Location }
        $previousMode = if (Test-Path $frontendModePath) { (Get-Content $frontendModePath -Raw).Trim() } else { 'dev' }
        if ($previousMode -ne 'preview') {
            $frontendPid = Get-RunningPid 'vite'
            if ($frontendPid) {
                $frontendProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$frontendPid"
                if (-not $frontendProcess.CommandLine.Contains('npm')) { throw 'Frontend process identity mismatch.' }
                taskkill /PID $frontendPid /T /F | Out-Null
            }
        }
        ($Apis | Where-Object { $_.Name -eq 'vite' }).Args = 'run preview -- --host 0.0.0.0'
    }
    Set-Content $frontendModePath $frontendMode
    # Floci EventBridge/SQS clients read credentials from the process environment only.
    $env:AWS_ACCESS_KEY_ID = 'test'
    $env:AWS_SECRET_ACCESS_KEY = 'test'

    Start-Containers
    Write-Host 'APIs'
    $Apis | ForEach-Object { Start-One $_ }
    Write-Host 'Waiting for API readiness...'
    $deadline = (Get-Date).AddSeconds(120)
    do {
        $unready = @($Apis | Where-Object { -not (Test-Ready $_) })
        if ($unready.Count -eq 0) { break }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    if ($unready.Count) { throw "APIs not ready: $($unready.Name -join ', '). Inspect .local/stack logs." }
    Write-Host 'Workers'
    $Workers | ForEach-Object { Start-One $_; Start-Sleep -Milliseconds 500 }
    Start-Stripe
    Start-Sleep -Seconds 2
    Show-Status
    $stopped = $Workers | Where-Object { -not (Get-RunningPid $_.Name) }
    if ($stopped) { throw "Workers failed to start: $($stopped.Name -join ', '). Inspect .local/stack logs." }
    Write-Host "`nOpen https://localhost:8443  (logs: .local\stack\<name>.err.log)"
}

function Stop-Stack {
    Get-ChildItem $StateDir -Filter *.pid -ErrorAction SilentlyContinue | ForEach-Object {
        $id = Get-RunningPid $_.BaseName
        if ($id) { taskkill /PID $id /T /F | Out-Null; Write-Host "  stopped $($_.BaseName)" }
        Remove-Item $_.FullName
    }
}

function Show-Status {
    Write-Host "`nStatus"
    foreach ($p in $Apis + $Workers + @(@{ Name = 'stripe-listen' })) {
        $state = if (Get-RunningPid $p.Name) { 'running' } else { 'STOPPED' }
        if ($p.Name -eq 'stripe-listen' -and (Test-StripeContainer)) { $state = 'running (Docker)' }
        if ($p.Port -and $state -eq 'running' -and -not (Test-Port $p.Port)) { $state = "running, port $($p.Port) not open" }
        '  {0,-20} {1}' -f $p.Name, $state | Write-Host
    }
    $https = if (Test-Port 8443) { 'open' } else { 'CLOSED' }
    '  {0,-20} {1}' -f 'https proxy (8443)', $https | Write-Host
}

switch ($Action) {
    'start'  { Start-Stack }
    'stop'   { Stop-Stack }
    'status' { Show-Status }
}

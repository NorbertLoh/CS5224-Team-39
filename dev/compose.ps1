<#
Full local Compose application; no host Python or Node required.
  ./dev/compose.ps1 setup -UseExistingDatabase -Payments
  ./dev/compose.ps1 up -Payments -Development
  ./dev/compose.ps1 check
  ./dev/compose.ps1 status
  ./dev/compose.ps1 down
See docs/compose-stack.md. Never removes volumes or resets data.
#>
param(
    [ValidateSet('setup', 'up', 'check', 'status', 'down', 'logs')]
    [string]$Action = 'up',
    [switch]$UseExistingDatabase,
    [switch]$Payments,
    [switch]$Development
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$State = Join-Path $Root '.local/compose'
$Services = @('identity', 'tenant', 'scheduling', 'consultation', 'clinical_records', 'fulfilment', 'document', 'billing', 'notification-image')
New-Item -ItemType Directory -Force $State | Out-Null

function Write-Utf8($Path, $Value) {
    [IO.File]::WriteAllText($Path, $Value, (New-Object Text.UTF8Encoding $false))
}

function Set-ComposeArgs {
    $script:ComposeArgs = @('compose', '--project-directory', $Root)
    if (Test-Path (Join-Path $Root '.env')) {
        $script:ComposeArgs += @('--env-file', (Join-Path $Root '.env'))
    }
    if (Test-Path (Join-Path $State 'compose.env')) {
        $script:ComposeArgs += @('--env-file', (Join-Path $State 'compose.env'))
    }
    $script:ComposeArgs += @('-f', (Join-Path $Root 'compose.yaml'), '-f', (Join-Path $Root 'compose.app.yaml'))
    if (Test-Path (Join-Path $State 'database.yaml')) {
        $script:ComposeArgs += @('-f', (Join-Path $State 'database.yaml'))
    }
    if ($Development) { $script:ComposeArgs += @('-f', (Join-Path $Root 'compose.dev.yaml')) }
    if ($Payments) { $script:ComposeArgs += @('--profile', 'payments') }
}

function Compose {
    & docker @script:ComposeArgs @args
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose failed ($LASTEXITCODE). See the output above." }
}

function Build-Stack {
    # Keep the first build usable on a 16 GB Windows development machine.
    $targets = @($Services) + @('web', 'signalling', 'setup')
    for ($index = 0; $index -lt $targets.Count; $index += 2) {
        $batch = @($targets[$index])
        if ($index + 1 -lt $targets.Count) { $batch += $targets[$index + 1] }
        # A file avoids Compose/Bake's intermittent closed-stdin pipe error.
        $definition = Compose --profile setup build --print @batch
        $buildFile = Join-Path $State 'build.json'
        Write-Utf8 $buildFile (($definition -join "`n") + "`n")
        & docker buildx bake --file $buildFile --progress plain
        if ($LASTEXITCODE -ne 0) { throw "Docker image build failed ($LASTEXITCODE)." }
    }
}

function Stop-HostStack {
    # Only processes tracked by the established host launcher are stopped.
    & (Join-Path $PSScriptRoot 'local_stack.ps1') stop
    $legacy = @(& docker ps --filter 'label=com.docker.compose.project=telelink-signalling' --format '{{.ID}}')
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect the legacy signalling stack' }
    if ($legacy.Count -gt 0) {
        & docker stop @legacy
        if ($LASTEXITCODE -ne 0) { throw 'Could not stop the legacy signalling stack' }
    }
}

function Adopt-Database {
    if (Test-Path (Join-Path $State 'database.yaml')) {
        Write-Host 'Existing database adoption configuration preserved.'
        return
    }
    $details = & docker inspect telelink-clinic-postgres | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw 'Existing telelink-clinic-postgres container not found.' }
    $mount = $details[0].Mounts | Where-Object { $_.Destination -eq '/var/lib/postgresql/data' }
    if ($mount.Type -ne 'volume' -or $mount.Name -notmatch '^[a-zA-Z0-9_.-]+$') {
        throw 'Expected the existing PostgreSQL named/anonymous Docker volume; no changes made.'
    }
    $password = ($details[0].Config.Env | Where-Object { $_ -like 'POSTGRES_PASSWORD=*' } | Select-Object -First 1).Substring(18)
    if (-not $password -or $password -match '[\r\n]') { throw 'Cannot read the local PostgreSQL administrator configuration.' }
    Stop-HostStack
    & docker stop telelink-clinic-postgres
    if ($LASTEXITCODE -ne 0) { throw 'Could not stop the legacy database; refusing concurrent volume access.' }
    Write-Utf8 (Join-Path $State 'compose.env') "POSTGRES_PASSWORD=$password`n"
    $databaseConfig = @"
services:
  postgres:
    volumes: !override
      - existing_clinic_data:/var/lib/postgresql/data
volumes:
  existing_clinic_data:
    external: true
    name: $($mount.Name)
"@
    Write-Utf8 (Join-Path $State 'database.yaml') ($databaseConfig + "`n")
    Write-Host 'Existing PostgreSQL volume adopted. The legacy container remains stopped for rollback.'
}

function Configure-Stripe {
    if (-not $Payments) { return }
    $output = & docker @script:ComposeArgs run --rm --no-deps -T stripe listen --print-secret
    if ($LASTEXITCODE -ne 0) { throw 'Stripe test listener setup failed.' }
    $secret = ($output | Where-Object { $_ -match '^whsec_[A-Za-z0-9_]+$' } | Select-Object -First 1)
    if (-not $secret) { throw 'Stripe CLI did not return a webhook signing secret.' }
    $path = Join-Path $State 'billing.env'
    $lines = @(Get-Content -LiteralPath $path | Where-Object { $_ -notmatch '^SERVICE_STRIPE_WEBHOOK_SECRET=' })
    $lines += "SERVICE_STRIPE_WEBHOOK_SECRET=$secret"
    Write-Utf8 $path (($lines -join "`n") + "`n")
    Write-Host 'Stripe test webhook secret configured (value kept private).'
}

function Assert-DatabaseExclusive {
    if (-not (Test-Path (Join-Path $State 'database.yaml'))) { return }
    $running = & docker ps --filter 'name=^/telelink-clinic-postgres$' --format '{{.ID}}'
    if ($LASTEXITCODE -ne 0) { throw 'Could not check the legacy database container.' }
    if ($running) { throw 'Stop telelink-clinic-postgres before using Compose with its adopted volume.' }
}

Push-Location $Root
try {
    Set-ComposeArgs
    if ($UseExistingDatabase -and $Action -ne 'setup') { throw '-UseExistingDatabase is only supported with setup.' }
    switch ($Action) {
        'setup' {
            if ($UseExistingDatabase) { Adopt-Database; Set-ComposeArgs }
            Assert-DatabaseExclusive
            Compose up -d --wait --wait-timeout 600 postgres redis floci
            Build-Stack
            Compose run --rm -T bootstrap
            Compose --profile setup run --rm -T setup configure
            Set-ComposeArgs
            foreach ($service in $Services) {
                Write-Host "Migrating $service"
                Compose --profile setup run --rm --no-deps -T $service python -m alembic upgrade head
            }
            Compose --profile setup run --rm -T setup seed
            Configure-Stripe
            Stop-HostStack
            Compose up -d --wait --wait-timeout 600
            Compose --profile setup run --rm -T setup check
            Write-Host 'Open https://localhost:8443'
        }
        'up' {
            if (-not (Test-Path (Join-Path $State 'web.env'))) { throw 'Run ./dev/compose.ps1 setup first.' }
            Assert-DatabaseExclusive
            Configure-Stripe
            Compose up -d --wait --wait-timeout 600
            Write-Host 'Open https://localhost:8443'
        }
        'check' { Compose --profile setup run --rm -T setup check }
        'status' { Compose ps --all }
        'down' { Compose --profile payments --profile setup down }
        'logs' { Compose logs --tail 80 }
    }
} finally { Pop-Location }

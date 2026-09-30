param(
    [switch]$PrepareWheels
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$wheelhouse = Join-Path $root "wheels"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is unavailable. Run this script on a machine with Docker Desktop."
}

Push-Location $root
try {
    if ($PrepareWheels) {
        if (-not (Test-Path $python)) {
            throw "Project .venv Python was not found at $python"
        }
        & $python -m pip wheel --no-deps --wheel-dir $wheelhouse .
        if ($LASTEXITCODE -ne 0) {
            throw "Could not build the RosettaLog wheel."
        }
        & $python -m pip download `
            --dest $wheelhouse `
            --find-links $wheelhouse `
            --only-binary=:all: `
            --platform manylinux2014_x86_64 `
            --platform manylinux_2_28_x86_64 `
            --python-version 3.11 `
            --implementation cp `
            --abi cp311 `
            --abi abi3 `
            --abi none `
            -r requirements-container.txt
        if ($LASTEXITCODE -ne 0) {
            throw "Could not prepare Linux x86_64 runtime wheels."
        }
    }

    $projectWheel = Get-ChildItem $wheelhouse -Filter "rosettalog-0.1.0-py3-none-any.whl"
    if (-not $projectWheel) {
        throw "Wheelhouse is incomplete. Prepare it on a connected machine with -PrepareWheels."
    }
    & docker compose build --network none --no-cache
    if ($LASTEXITCODE -ne 0) {
        throw "Offline container image build failed."
    }
    & docker compose up -d
    if ($LASTEXITCODE -ne 0) {
        throw "Could not start the internal-only Compose stack."
    }

    $healthy = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $api = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 3
            $ui = Invoke-WebRequest -Uri "http://127.0.0.1:8501/_stcore/health" -TimeoutSec 3
            if ($api.status -eq "ok" -and $ui.StatusCode -eq 200) {
                $healthy = $true
                break
            }
        }
        catch {
            Start-Sleep -Seconds 2
        }
    }
    if (-not $healthy) {
        throw "API and UI did not become healthy on the internal-only Compose network."
    }
}
finally {
    & docker compose down
    Pop-Location
}

Write-Output "Airgap container smoke test passed."

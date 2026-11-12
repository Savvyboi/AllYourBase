[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8766,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$toolUrl = "http://127.0.0.1:$Port/"
$expectedTitle = '<title>AllYourBase monitor sites</title>'
$browserJob = $null
$exitCode = 0
$repository = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))

try {
    $alreadyRunning = $false
    try {
        $response = Invoke-WebRequest -Uri $toolUrl -UseBasicParsing -TimeoutSec 1
        $alreadyRunning = $response.Content.Contains($expectedTitle)
    }
    catch {
        # A closed port is normal before the first launch.
    }
    if ($alreadyRunning) {
        Write-Host "The local tool is already running: $toolUrl"
        if (-not $NoBrowser) { Start-Process $toolUrl }
        exit 0
    }

    $listeners = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
    if ($listeners | Where-Object { $_.Port -eq $Port }) {
        throw "Port $Port is used by another app. Close it and try again."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $repository 'sites.yaml'))) {
        throw 'sites.yaml is missing. Keep this launcher with the AllYourBase repository.'
    }

    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    $uvPath = if ($uvCommand) { $uvCommand.Source } else { $null }
    if (-not $uvPath) {
        $candidates = @(
            (Join-Path $env:LOCALAPPDATA 'hermes\bin\uv.exe'),
            (Join-Path $env:USERPROFILE '.local\bin\uv.exe'),
            (Join-Path $env:USERPROFILE '.cargo\bin\uv.exe'),
            (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\uv.exe')
        )
        $uvPath = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
    if (-not $uvPath) {
        throw 'uv was not found. Install uv as described in README.md, then double-click again.'
    }

    # A dedicated environment avoids the legacy review tool's locked executable.
    $env:UV_PROJECT_ENVIRONMENT = Join-Path (Split-Path $repository -Parent) 'monitor-tool-env'
    Write-Host 'Starting the AllYourBase local tool...'
    Write-Host 'The first start may take a moment to prepare dependencies.'
    Write-Host "Address: $toolUrl"
    Write-Host 'Keep this window open. Close it to stop the tool.'
    Write-Host ''

    if (-not $NoBrowser) {
        $browserJob = Start-Job -ArgumentList $toolUrl, $expectedTitle -ScriptBlock {
            param($url, $title)
            for ($attempt = 0; $attempt -lt 600; $attempt++) {
                try {
                    $page = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 1 -ErrorAction Stop
                    if ($page.Content.Contains($title)) {
                        Start-Process $url
                        return
                    }
                }
                catch { }
                Start-Sleep -Milliseconds 500
            }
        }
    }

    Push-Location -LiteralPath $repository
    try {
        & $uvPath run --locked --extra monitor --extra review --no-dev --python 3.12 python -m allyourbase monitor review --port $Port
        if ($LASTEXITCODE -ne 0) { throw "The local tool exited with code $LASTEXITCODE." }
    }
    finally {
        Pop-Location
    }
}
catch {
    Write-Host "Unable to start the local tool: $($_.Exception.Message)" -ForegroundColor Red
    $exitCode = 1
}
finally {
    if ($browserJob) {
        Stop-Job -Job $browserJob -ErrorAction SilentlyContinue
        Remove-Job -Job $browserJob -Force -ErrorAction SilentlyContinue
    }
}
exit $exitCode

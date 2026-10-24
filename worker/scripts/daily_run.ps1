# Paper2Career daily local ingestion runner
# Can be scheduled in Windows Task Scheduler to run every morning at 06:30 IST.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkerDir = Split-Path -Parent $ScriptDir
Set-Location $WorkerDir

$VenvPython = Join-Path $WorkerDir ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment not found at $VenvPython. Please run: py -3.12 -m venv .venv"
}

Write-Host "Starting Paper2Career daily ingestion..." -ForegroundColor Cyan
& $VenvPython -m paper2career run --auto-publish --trigger "scheduled_local"

Write-Host "Daily ingestion completed successfully!" -ForegroundColor Green

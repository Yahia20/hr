<#
  run-local.ps1 — start the HR Disciplinary System locally (backend + frontend).

  Usage:
    powershell -ExecutionPolicy Bypass -File .\run-local.ps1            # start both
    powershell -ExecutionPolicy Bypass -File .\run-local.ps1 -Backend   # backend only
    powershell -ExecutionPolicy Bypass -File .\run-local.ps1 -Frontend  # frontend only

  Backend : http://localhost:8000  (FastAPI + SQLite)
  Frontend: http://localhost:5173  (React + Vite, proxies /api -> :8000)
  Login   : hr / admin123   (override via $env:HR_ADMIN_USERNAME / $env:HR_ADMIN_PASSWORD)
#>
param(
  [switch]$Backend,
  [switch]$Frontend
)

$ErrorActionPreference = "Stop"
$root     = $PSScriptRoot
$nodeDir  = Join-Path $root ".tools\node-v20.18.1-win-x64"

# Pick a Python that has the backend deps installed. The repo venv is optional;
# we prefer it, then fall back to the user/system Python (which already has
# fastapi/uvicorn/openpyxl installed on this machine).
$venvPy = Join-Path $root "backend\.venv\Scripts\python.exe"
$sysPy  = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
$python = if (Test-Path $venvPy) { $venvPy } elseif (Test-Path $sysPy) { $sysPy } else { "python" }

# default: run both
if (-not $Backend -and -not $Frontend) { $Backend = $true; $Frontend = $true }

if ($Backend) {
  Write-Host "Starting backend on http://localhost:8000 (python: $python) ..." -ForegroundColor Cyan
  if (-not $env:HR_ADMIN_USERNAME) { $env:HR_ADMIN_USERNAME = "hr" }
  if (-not $env:HR_ADMIN_PASSWORD) { $env:HR_ADMIN_PASSWORD = "admin123" }
  Start-Process -FilePath $python `
    -ArgumentList "-m","uvicorn","app.main:app","--port","8000","--host","127.0.0.1" `
    -WorkingDirectory (Join-Path $root "backend")
}

if ($Frontend) {
  $npm = Join-Path $nodeDir "npm.cmd"
  if (-not (Test-Path $npm)) { throw "Portable Node missing at $nodeDir" }
  Write-Host "Starting frontend on http://localhost:5173 ..." -ForegroundColor Cyan
  $env:Path = "$nodeDir;$env:Path"
  Start-Process -FilePath $npm `
    -ArgumentList "run","dev" `
    -WorkingDirectory (Join-Path $root "frontend")
}

Write-Host ""
Write-Host "HR System starting up." -ForegroundColor Green
Write-Host "  Frontend : http://localhost:5173"
Write-Host "  Backend  : http://localhost:8000/health  (docs at /docs)"
Write-Host "  Login    : hr / admin123"

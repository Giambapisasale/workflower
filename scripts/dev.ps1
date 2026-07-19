# Workflower — avvia backend + frontend in terminali separati
param(
    [switch]$BackendOnly,
    [switch]$FrontendOnly
)

$root = Split-Path -Parent $PSScriptRoot
$py   = "$root/backend/.venv/Scripts/python.exe"

function Start-Backend {
    Write-Host "== Avvio Backend (FastAPI :8000) ==" -ForegroundColor Cyan
    Start-Process pwsh -ArgumentList "-NoExit", "-Command", "cd '$root'; & '$py' -m uvicorn app.main:app --reload --app-dir backend --port 8000"
}

function Start-Frontend {
    Write-Host "== Avvio Frontend (Vite :5173) ==" -ForegroundColor Cyan
    Start-Process pwsh -ArgumentList "-NoExit", "-Command", "cd '$root'; npm --prefix frontend run dev"
}

if ($FrontendOnly) {
    Start-Frontend
} elseif ($BackendOnly) {
    Start-Backend
} else {
    Start-Backend
    Start-Sleep -Seconds 2
    Start-Frontend
    Write-Host ""
    Write-Host "Backend:  http://localhost:8000" -ForegroundColor Green
    Write-Host "Frontend: http://localhost:5173" -ForegroundColor Green
    Write-Host ""
}

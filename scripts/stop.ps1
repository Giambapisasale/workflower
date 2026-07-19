# Workflower — ferma tutti i processi di sviluppo
param(
    [switch]$BackendOnly,
    [switch]$FrontendOnly
)

function Stop-Port {
    param([int]$Port, [string]$Label)
    $conns = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if (-not $conns) {
        Write-Host "$Label (porta $Port): già fermo" -ForegroundColor Gray
        return
    }
    $ids = $conns.OwningProcess | Select-Object -Unique
    foreach ($id in $ids) {
        $proc = Get-Process -Id $id -ErrorAction SilentlyContinue
        if ($proc) {
            Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
            Write-Host "$Label (porta $Port): fermato PID $id ($($proc.ProcessName))" -ForegroundColor Yellow
        }
    }
}

if ($FrontendOnly) {
    Stop-Port -Port 5173 -Label "Frontend"
} elseif ($BackendOnly) {
    Stop-Port -Port 8000 -Label "Backend"
} else {
    Stop-Port -Port 5173 -Label "Frontend"
    Stop-Port -Port 8000 -Label "Backend"
    Write-Host "`nTutti i processi fermati." -ForegroundColor Green
}

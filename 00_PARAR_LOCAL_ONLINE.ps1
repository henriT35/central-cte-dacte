$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $Root ".local_online_pids.json"
if (Test-Path $PidFile) {
    try {
        $p = Get-Content -Raw $PidFile | ConvertFrom-Json
        foreach ($id in @($p.tunnel_pid, $p.server_pid)) {
            if ($id) { Stop-Process -Id ([int]$id) -Force -ErrorAction SilentlyContinue }
        }
    } catch {}
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}
Write-Host "Central CT-e local/online encerrada." -ForegroundColor Green

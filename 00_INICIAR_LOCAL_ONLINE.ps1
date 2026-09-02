$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Server = Join-Path $Root "web_local\server.py"
$Tools = Join-Path $Root "tools"
$Cloudflared = Join-Path $Tools "cloudflared.exe"
$LogDir = Join-Path $Root "logs"
$TunnelLog = Join-Path $LogDir "cloudflare_quick_tunnel.log"
$PidFile = Join-Path $Root ".local_online_pids.json"
$UrlFile = Join-Path $Root "URL_ONLINE.txt"
$LocalUrl = "http://127.0.0.1:8765"
$ExpectedVersion = "RC27.14 WEB/WINDOWS MVP13 R12.13.9"

function Find-Python {
    foreach ($candidate in @("py.exe", "python.exe")) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($cmd) { return $candidate }
    }
    return $null
}

function Stop-OldProcesses {
    if (-not (Test-Path $PidFile)) { return }
    try {
        $p = Get-Content -Raw $PidFile | ConvertFrom-Json
        foreach ($id in @($p.tunnel_pid, $p.server_pid)) {
            if ($id) { Stop-Process -Id ([int]$id) -Force -ErrorAction SilentlyContinue }
        }
    } catch {}
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

function Wait-Health {
    param([int]$Seconds = 60)
    $end = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $end) {
        Start-Sleep -Milliseconds 500
        try {
            $h = Invoke-RestMethod -TimeoutSec 2 -Uri "$LocalUrl/api/health" -Headers @{Host="127.0.0.1"}
            if ($h.ok) { return $h }
        } catch {}
    }
    return $null
}

try {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host " CENTRAL CT-e / DACTE R12.13.9 - LOCAL + ONLINE" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ""

    if (-not (Test-Path $Server)) { throw "web_local\server.py nao encontrado." }
    New-Item -ItemType Directory -Path $Tools -Force | Out-Null
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    Stop-OldProcesses

    $python = Find-Python
    if (-not $python) {
        Write-Host "Python nao foi encontrado neste PC." -ForegroundColor Yellow
        Write-Host "Instale Python 3.11 ou superior e marque 'Add Python to PATH'."
        Write-Host "Depois execute este arquivo novamente."
        try { Start-Process "https://www.python.org/downloads/windows/" } catch {}
        Read-Host "Pressione ENTER para fechar"
        exit 3
    }

    $busy = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($busy) {
        try {
            $health = Invoke-RestMethod -TimeoutSec 2 -Uri "$LocalUrl/api/health" -Headers @{Host="127.0.0.1"}
        } catch { $health = $null }
        if (-not $health -or -not $health.ok) {
            throw "A porta 8765 esta sendo usada por outro programa."
        }

        # R12.13.9: um hotfix pode trocar os arquivos enquanto um Python antigo
        # continua escutando a porta. Nesse caso o navegador exibe a versao
        # nova no disco, mas executa a logica antiga em memoria. Reinicia o
        # listener quando a versao de /api/health nao e exatamente a esperada.
        if ([string]$health.version -ne $ExpectedVersion) {
            Write-Host "[1/5] Reiniciando servidor antigo: $($health.version) -> $ExpectedVersion" -ForegroundColor Yellow
            try { Stop-Process -Id ([int]$busy.OwningProcess) -Force -ErrorAction Stop } catch { }
            for ($i=0; $i -lt 20; $i++) {
                Start-Sleep -Milliseconds 250
                if (-not (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue)) { break }
            }
            $busy = $null
            $health = $null
        } else {
            $serverProcess = $null
            Write-Host "[1/5] Servidor local R12.13.9 ja estava ativo." -ForegroundColor Green
        }
    }

    if (-not $busy) {
        Write-Host "[1/5] Iniciando servidor local..."
        $env:CENTRAL_CTE_HOST = "127.0.0.1"
        $env:CENTRAL_CTE_PORT = "8765"
        $env:CENTRAL_CTE_STRICT_PORT = "1"
        $env:CENTRAL_CTE_ALLOWED_HOSTS = "*.trycloudflare.com,127.0.0.1,localhost"
        $env:CENTRAL_CTE_HTTPS = "1"
        $env:CENTRAL_CTE_TRUST_PROXY = "1"

        if ($python -ieq "py.exe") {
            $args = @("-3", $Server, "--host", "127.0.0.1", "--port", "8765", "--strict-port", "--no-browser")
        } else {
            $args = @($Server, "--host", "127.0.0.1", "--port", "8765", "--strict-port", "--no-browser")
        }
        $serverProcess = Start-Process -FilePath $python -ArgumentList $args -WorkingDirectory $Root -WindowStyle Minimized -PassThru
        $health = Wait-Health -Seconds 90
        if (-not $health) {
            if ($serverProcess) { Stop-Process -Id $serverProcess.Id -Force -ErrorAction SilentlyContinue }
            throw "A Central nao respondeu em $LocalUrl."
        }
    }

    Write-Host "[2/5] Servidor OK: $($health.version) / motor $($health.engine)" -ForegroundColor Green

    if ($health.setup_required) {
        Write-Host ""
        Write-Host "Primeiro acesso: crie o usuario administrador/desenvolvedor." -ForegroundColor Yellow
        Write-Host "Abrindo $LocalUrl ..."
        Start-Process $LocalUrl
        Write-Host "Depois de concluir o cadastro no navegador, volte aqui."
        Read-Host "Pressione ENTER apos criar o usuario"
        $health = Wait-Health -Seconds 20
        if (-not $health) { throw "Servidor local deixou de responder." }
        if ($health.setup_required) {
            throw "O primeiro usuario ainda nao foi criado. Conclua o cadastro local e execute novamente."
        }
    }

    Write-Host "[3/5] Preparando Cloudflare Quick Tunnel..."
    if (-not (Test-Path $Cloudflared)) {
        Write-Host "Baixando cloudflared oficial..." -ForegroundColor Yellow
        Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile $Cloudflared
    }
    if (-not (Test-Path $Cloudflared)) { throw "Nao foi possivel obter cloudflared.exe." }

    Remove-Item $TunnelLog -Force -ErrorAction SilentlyContinue
    Remove-Item $UrlFile -Force -ErrorAction SilentlyContinue

    Write-Host "[4/5] Criando link publico temporario..."
    $profile = Join-Path $env:TEMP "CentralCTeQuickTunnelProfile"
    New-Item -ItemType Directory -Path (Join-Path $profile ".cloudflared") -Force | Out-Null
    $cmd = "set USERPROFILE=$profile&& set HOME=$profile&& `"$Cloudflared`" tunnel --no-autoupdate --url http://127.0.0.1:8765 > `"$TunnelLog`" 2>&1"
    $tunnelProcess = Start-Process -FilePath "cmd.exe" -ArgumentList @("/d","/c",$cmd) -WorkingDirectory $Root -WindowStyle Minimized -PassThru

    $publicUrl = $null
    for ($i=0; $i -lt 120; $i++) {
        Start-Sleep -Milliseconds 500
        if ($tunnelProcess.HasExited) {
            $details = if (Test-Path $TunnelLog) { Get-Content -Raw $TunnelLog } else { "Sem log." }
            throw "Cloudflare Tunnel encerrou antes de gerar o link.`n$details"
        }
        if (Test-Path $TunnelLog) {
            $text = Get-Content -Raw -ErrorAction SilentlyContinue $TunnelLog
            if (-not [string]::IsNullOrWhiteSpace([string]$text)) {
                $m = [regex]::Match(
                    [string]$text,
                    'https://[a-z0-9-]+\.trycloudflare\.com',
                    [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
                )
                if ($m.Success) { $publicUrl = $m.Value; break }
            }
        }
    }
    if (-not $publicUrl) { throw "O link trycloudflare.com nao foi gerado no tempo esperado." }

    [ordered]@{
        created_at = (Get-Date).ToString("o")
        local_url = $LocalUrl
        public_url = $publicUrl
        server_pid = if ($serverProcess) { $serverProcess.Id } else { $null }
        tunnel_pid = $tunnelProcess.Id
    } | ConvertTo-Json | Set-Content -Encoding UTF8 $PidFile

    Set-Content -Encoding UTF8 -Path $UrlFile -Value $publicUrl
    try { Set-Clipboard $publicUrl } catch {}

    Write-Host "[5/5] PRONTO." -ForegroundColor Green
    Write-Host ""
    Write-Host "LOCAL : $LocalUrl" -ForegroundColor Cyan
    Write-Host "ONLINE: $publicUrl" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "O link online foi copiado e salvo em URL_ONLINE.txt."
    Write-Host "O computador precisa ficar ligado enquanto o link estiver sendo usado." -ForegroundColor Yellow
    Write-Host "Para desligar, execute 00_PARAR_LOCAL_ONLINE.bat."
    Start-Process $publicUrl
    Read-Host "Pressione ENTER para fechar esta janela (o servidor continua ativo)"
    exit 0
} catch {
    Write-Host ""
    Write-Host ("ERRO: " + $_.Exception.Message) -ForegroundColor Red
    Write-Host ""
    Write-Host "Se existir, consulte: $TunnelLog"
    Read-Host "Pressione ENTER para fechar"
    exit 10
}

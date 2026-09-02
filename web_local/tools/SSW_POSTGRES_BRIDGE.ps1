# Central CT-e / DACTE R12.12
# Ponte local PostgreSQL SSW -> Central Web
# A ponte SOMENTE LÊ staging.stg_ssw_455_fretes e publica um snapshot sombra.
# Ela não grava no PostgreSQL e não substitui a Base SSW oficial.

[CmdletBinding()]
param(
    [string]$CentralUrl = "https://centraldacte.testeprojetosricky.com.br",
    [string]$BridgeToken = "",
    [string]$DbHost = "192.168.0.247",
    [int]$DbPort = 5432,
    [string]$DbName = "api_atlas",
    [string]$DbUser = "dwop",
    [string]$Schema = "staging",
    [string]$Table = "stg_ssw_455_fretes"
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Convert-SecureStringToPlainText([Security.SecureString]$Secure) {
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

function Get-ReaderValue($Reader, [string]$Name) {
    $value = $Reader[$Name]
    if ($null -eq $value -or $value -is [DBNull]) { return $null }
    return $value
}

if ($Schema -notmatch '^[a-z_][a-z0-9_]{0,62}$' -or $Table -notmatch '^[a-z_][a-z0-9_]{0,62}$') {
    throw "Schema/tabela inválidos."
}

if ([string]::IsNullOrWhiteSpace($BridgeToken)) {
    $BridgeToken = Read-Host "Cole o token da ponte gerado no perfil Desenvolvedor do Central"
}
if ([string]::IsNullOrWhiteSpace($BridgeToken)) { throw "Token da ponte não informado." }

$DbPasswordSecure = Read-Host "Senha PostgreSQL do usuário $DbUser" -AsSecureString
$DbPassword = Convert-SecureStringToPlainText $DbPasswordSecure

try {
    try {
        Add-Type -AssemblyName Npgsql -ErrorAction Stop
    }
    catch {
        throw "Npgsql não foi localizado pelo PowerShell. Confirme a instalação do Npgsql 4.0.17 usada pelo Excel. Erro: $($_.Exception.Message)"
    }

    $builder = New-Object Npgsql.NpgsqlConnectionStringBuilder
    $builder.Host = $DbHost
    $builder.Port = $DbPort
    $builder.Database = $DbName
    $builder.Username = $DbUser
    $builder.Password = $DbPassword
    $builder.Timeout = 10
    $builder.CommandTimeout = 180
    $builder.ApplicationName = "CentralCTe-SSW-Bridge-R12.12"

    Write-Host "Conectando ao PostgreSQL $DbHost`:$DbPort / $DbName..." -ForegroundColor Cyan
    $connection = New-Object Npgsql.NpgsqlConnection($builder.ConnectionString)
    $connection.Open()

    try {
        $guard = $connection.CreateCommand()
        $guard.CommandText = "SET default_transaction_read_only = on; SET statement_timeout = 180000;"
        [void]$guard.ExecuteNonQuery()

        $columns = @(
            "serie_numero_ctrc", "serie_numero_ct_e", "tipo_do_documento",
            "data_de_emissao", "data_de_autorizacao", "chave_ct_e",
            "cnpj_remetente", "cnpj_pagador", "cnpj_destinatario", "cnpj_recebedor",
            "numero_da_nota_fiscal", "valor_da_mercadoria", "valor_do_frete", "valor_do_frete_sem_icms",
            "cidade_de_entrega", "uf_de_entrega", "cidade_origem_da_prestacao", "uf_origem_da_prestacao",
            "tipo_de_baixa", "data_da_liquidacao",
            "frete_peso", "frete_valor", "despacho", "gris", "pedagio", "tda", "outros",
            "data_do_cancelamento", "motivo_do_cancelamento", "arquivo_origem", "data_carga"
        )

        $sql = "SELECT " + ($columns -join ", ") + " FROM $Schema.$Table ORDER BY data_de_emissao, serie_numero_ctrc"
        $command = $connection.CreateCommand()
        $command.CommandText = $sql
        $command.CommandTimeout = 180
        $reader = $command.ExecuteReader()
        $rows = New-Object 'System.Collections.Generic.List[object]'
        $count = 0
        try {
            while ($reader.Read()) {
                $item = [ordered]@{}
                foreach ($column in $columns) { $item[$column] = Get-ReaderValue $reader $column }
                $rows.Add([pscustomobject]$item)
                $count++
                if (($count % 10000) -eq 0) { Write-Host "  $count registros lidos..." }
                if ($count -gt 300000) { throw "A consulta ultrapassou o limite de segurança de 300.000 registros." }
            }
        }
        finally { $reader.Close() }

        if ($count -eq 0) { throw "A tabela retornou zero registros. O snapshot não será publicado." }
        Write-Host "$count registros lidos em modo somente leitura." -ForegroundColor Green

        $payload = [ordered]@{
            source = "$Schema.$Table"
            transport = "bridge"
            generated_at = [DateTimeOffset]::Now.ToString("o")
            rows = $rows
        }
        Write-Host "Serializando e compactando snapshot..." -ForegroundColor Cyan
        $json = $payload | ConvertTo-Json -Depth 6 -Compress
        $raw = [Text.Encoding]::UTF8.GetBytes($json)
        $memory = New-Object IO.MemoryStream
        $gzip = New-Object IO.Compression.GZipStream($memory, [IO.Compression.CompressionMode]::Compress, $true)
        $gzip.Write($raw, 0, $raw.Length)
        $gzip.Dispose()
        $compressed = $memory.ToArray()
        $memory.Dispose()

        $endpoint = $CentralUrl.TrimEnd('/') + "/api/integrations/ssw-postgres/publish"
        Write-Host "Enviando snapshot compactado ao Central..." -ForegroundColor Cyan
        $headers = @{
            Authorization = "Bearer $BridgeToken"
            "Content-Encoding" = "gzip"
        }
        $response = Invoke-RestMethod -Uri $endpoint -Method Post -Headers $headers -ContentType "application/json; charset=utf-8" -Body $compressed -TimeoutSec 600
        if (-not $response.ok) { throw "O Central recusou o snapshot." }
        Write-Host "Snapshot publicado com sucesso." -ForegroundColor Green
        Write-Host ("Registros: {0} | Arquivos 455: {1} | Ultima carga: {2}" -f $response.data.row_count, $response.data.arquivo_origem_count, $response.data.last_data_carga)
        Write-Host "A Base SSW oficial NÃO foi substituída." -ForegroundColor Yellow
    }
    finally {
        if ($null -ne $connection) { $connection.Close(); $connection.Dispose() }
    }
}
finally {
    $DbPassword = $null
    $DbPasswordSecure = $null
}

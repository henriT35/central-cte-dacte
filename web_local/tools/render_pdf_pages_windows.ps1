param(
    [Parameter(Mandatory = $true)][string]$PdfPath,
    [Parameter(Mandatory = $true)][string]$OutputDirectory,
    [int]$MaximumPages = 10,
    [int]$DestinationWidth = 1800
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime

# Força o carregamento dos tipos WinRT usados pelo renderizador nativo.
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Storage.FileAccessMode, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Data.Pdf.PdfDocument, Windows.Data.Pdf, ContentType = WindowsRuntime]
$null = [Windows.Data.Pdf.PdfPageRenderOptions, Windows.Data.Pdf, ContentType = WindowsRuntime]

$extensions = [System.WindowsRuntimeSystemExtensions].GetMethods()
$asTaskGeneric = $extensions |
    Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 } |
    Select-Object -First 1
$asTaskAction = $extensions |
    Where-Object { $_.Name -eq 'AsTask' -and -not $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 } |
    Select-Object -First 1

function Await-Result {
    param($Operation, [Type]$ResultType)
    $task = $asTaskGeneric.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    $task.GetAwaiter().GetResult()
}

function Await-Action {
    param($Operation)
    $task = $asTaskAction.Invoke($null, @($Operation))
    $task.GetAwaiter().GetResult()
}

$PdfPath = [IO.Path]::GetFullPath($PdfPath)
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
if (-not [IO.File]::Exists($PdfPath)) {
    throw "PDF não encontrado: $PdfPath"
}
[IO.Directory]::CreateDirectory($OutputDirectory) | Out-Null

$storageFile = Await-Result ([Windows.Storage.StorageFile]::GetFileFromPathAsync($PdfPath)) ([Windows.Storage.StorageFile])
$pdf = Await-Result ([Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($storageFile)) ([Windows.Data.Pdf.PdfDocument])
$count = [Math]::Min([int]$pdf.PageCount, [Math]::Max(1, [Math]::Min($MaximumPages, 10)))

for ($index = 0; $index -lt $count; $index++) {
    $page = $pdf.GetPage([uint32]$index)
    try {
        $targetPath = Join-Path $OutputDirectory ('pagina_{0:D2}.png' -f ($index + 1))
        [IO.File]::WriteAllBytes($targetPath, [byte[]]@())
        $targetFile = Await-Result ([Windows.Storage.StorageFile]::GetFileFromPathAsync($targetPath)) ([Windows.Storage.StorageFile])
        $stream = Await-Result ($targetFile.OpenAsync([Windows.Storage.FileAccessMode]::ReadWrite)) ([Windows.Storage.Streams.IRandomAccessStream])
        try {
            $options = [Windows.Data.Pdf.PdfPageRenderOptions]::new()
            $options.DestinationWidth = [uint32][Math]::Max(800, [Math]::Min($DestinationWidth, 3000))
            Await-Action ($page.RenderToStreamAsync($stream, $options))
            Await-Action ($stream.FlushAsync())
        }
        finally {
            if ($stream) { $stream.Dispose() }
        }
        if ((Get-Item -LiteralPath $targetPath).Length -lt 100) {
            throw "A página $($index + 1) não foi renderizada corretamente."
        }
        Write-Output $targetPath
    }
    finally {
        $page.Dispose()
    }
}

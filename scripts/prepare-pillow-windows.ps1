[CmdletBinding()]
param(
    [string]$OutputDirectory,
    [string]$PillowVersion = '12.3.0'
)

$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$allowedRoot = [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'build\embedded\python-packages'))

if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $allowedRoot 'windows-x64-release'
} elseif (-not [System.IO.Path]::IsPathRooted($OutputDirectory)) {
    $OutputDirectory = Join-Path $projectRoot $OutputDirectory
}
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)

if (-not $OutputDirectory.StartsWith($allowedRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Unsicherer Pillow-Ausgabepfad: $OutputDirectory"
}

$pillowMarker = Join-Path $OutputDirectory 'PIL\__init__.py'
if (Test-Path -LiteralPath $pillowMarker) {
    Write-Host "Pillow $PillowVersion ist bereits vorbereitet: $OutputDirectory"
    return
}

$pinnedWheelHashes = @{
    # pillow-12.3.0-cp312-cp312-win_amd64.whl
    '12.3.0' = 'a2b55dd6b2a4c4b7d87ffa56bdb33fdc5fdb9a462173861a7bc097f17d91cb09'
}
if (-not $pinnedWheelHashes.ContainsKey($PillowVersion)) {
    throw "Fuer Pillow $PillowVersion ist noch keine freigegebene Windows-Wheel-Pruefsumme hinterlegt."
}
$pinnedHash = $pinnedWheelHashes[$PillowVersion]

$tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$downloadDirectory = [System.IO.Path]::GetFullPath((Join-Path $tempRoot ('wavelog-pillow-' + [guid]::NewGuid().ToString('N'))))
if (-not $downloadDirectory.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Unsicherer temporaerer Pfad: $downloadDirectory"
}

try {
    # The portable Python runtime used by the application deliberately has no
    # pip module. Resolve the official CPython 3.12 x64 wheel through PyPI,
    # verify its published SHA-256 digest, and extract it directly.
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $metadataUri = "https://pypi.org/pypi/Pillow/$PillowVersion/json"
    Write-Host "Lade Pillow-Metadaten von PyPI ..."
    $metadata = Invoke-RestMethod -Uri $metadataUri -Headers @{ 'User-Agent' = 'DA6IT-Wavelog-Offline-Logger-Build' }
    $wheelSuffix = '-cp312-cp312-win_amd64.whl'
    $wheelAsset = @($metadata.urls) | Where-Object {
        $candidateName = [string]$_.filename
        $_.packagetype -eq 'bdist_wheel' -and $candidateName.EndsWith($wheelSuffix, [System.StringComparison]::OrdinalIgnoreCase)
    } | Select-Object -First 1
    if (-not $wheelAsset) {
        throw "Kein offizielles Pillow-$PillowVersion-Wheel fuer CPython 3.12 / Windows x64 gefunden."
    }

    $expectedHash = ([string]$wheelAsset.digests.sha256).Trim().ToLowerInvariant()
    if ($expectedHash -notmatch '^[0-9a-f]{64}$') {
        throw 'PyPI lieferte keine gueltige SHA-256-Pruefsumme fuer das Pillow-Wheel.'
    }
    if ($expectedHash -ne $pinnedHash) {
        throw "Die aktuelle PyPI-Pruefsumme weicht von der freigegebenen Pillow-Pruefsumme ab: $expectedHash != $pinnedHash"
    }

    New-Item -ItemType Directory -Path $downloadDirectory | Out-Null
    $wheelPath = Join-Path $downloadDirectory 'pillow.whl'
    Write-Host "Lade $($wheelAsset.filename) ..."
    Invoke-WebRequest -Uri ([string]$wheelAsset.url) -OutFile $wheelPath -UseBasicParsing -Headers @{ 'User-Agent' = 'DA6IT-Wavelog-Offline-Logger-Build' }
    $actualHash = (Get-FileHash -LiteralPath $wheelPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $pinnedHash) {
        throw "Pillow-Pruefsumme stimmt nicht: $actualHash != $pinnedHash"
    }

    if (Test-Path -LiteralPath $OutputDirectory) {
        Remove-Item -LiteralPath $OutputDirectory -Recurse -Force
    }
    New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($wheelPath, $OutputDirectory)

    if (-not (Test-Path -LiteralPath $pillowMarker)) {
        throw 'Das verifizierte Pillow-Wheel enthielt kein PIL-Paket.'
    }
    [System.IO.File]::WriteAllText(
        (Join-Path $OutputDirectory 'PILLOW_VERSION.txt'),
        "$PillowVersion`n",
        [System.Text.UTF8Encoding]::new($false)
    )
    Write-Host "Pillow $PillowVersion vorbereitet: $OutputDirectory"
} finally {
    if (Test-Path -LiteralPath $downloadDirectory) {
        Remove-Item -LiteralPath $downloadDirectory -Recurse -Force
    }
}

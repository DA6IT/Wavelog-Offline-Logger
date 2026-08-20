[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory,
    [string]$TruststoreVersion = '0.10.4',
    [string]$CertifiVersion = '2026.6.17'
)

$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$allowedRoot = [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'build\embedded\python-packages'))
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
if (-not $OutputDirectory.StartsWith($allowedRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Unsicherer Python-Paketpfad: $OutputDirectory"
}

$versionText = "truststore=$TruststoreVersion`ncertifi=$CertifiVersion`n"
$versionMarker = Join-Path $OutputDirectory 'NETWORK_TRUST_VERSIONS.txt'
if ((Test-Path -LiteralPath (Join-Path $OutputDirectory 'truststore\__init__.py')) -and
    (Test-Path -LiteralPath (Join-Path $OutputDirectory 'certifi\cacert.pem')) -and
    (Test-Path -LiteralPath $versionMarker) -and
    ([System.IO.File]::ReadAllText($versionMarker) -eq $versionText)) {
    Write-Host "Native TLS-Vertrauenspakete sind bereits vorbereitet: $OutputDirectory"
    return
}

$packages = @(
    @{
        Name = 'truststore'; Version = $TruststoreVersion
        FileName = "truststore-$TruststoreVersion-py3-none-any.whl"
        Sha256 = 'adaeaecf1cbb5f4de3b1959b42d41f6fab57b2b1666adb59e89cb0b53361d981'
    },
    @{
        Name = 'certifi'; Version = $CertifiVersion
        FileName = "certifi-$CertifiVersion-py3-none-any.whl"
        Sha256 = '2227dcbaafe0d2f59279d1762ddddc37783ed4354594f194ffc31d20f41fc3db'
    }
)

$tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$workDirectory = [System.IO.Path]::GetFullPath((Join-Path $tempRoot ('wavelog-network-trust-' + [guid]::NewGuid().ToString('N'))))
if (-not $workDirectory.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Unsicherer temporaerer Pfad: $workDirectory"
}

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    New-Item -ItemType Directory -Path $workDirectory -Force | Out-Null
    New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
    foreach ($package in $packages) {
        $metadataUri = "https://pypi.org/pypi/$($package.Name)/$($package.Version)/json"
        Write-Host "Lade $($package.Name)-Metadaten von PyPI ..."
        $metadata = Invoke-RestMethod -Uri $metadataUri -Headers @{ 'User-Agent' = 'DA6IT-Wavelog-Offline-Logger-Build' }
        $asset = @($metadata.urls) | Where-Object {
            $_.packagetype -eq 'bdist_wheel' -and ([string]$_.filename) -eq $package.FileName
        } | Select-Object -First 1
        if (-not $asset) {
            throw "Offizielles Wheel fehlt: $($package.FileName)"
        }
        $publishedHash = ([string]$asset.digests.sha256).Trim().ToLowerInvariant()
        if ($publishedHash -ne $package.Sha256) {
            throw "PyPI-Pruefsumme fuer $($package.Name) weicht ab: $publishedHash"
        }
        $archivePath = Join-Path $workDirectory ($package.Name + '.zip')
        Invoke-WebRequest -Uri ([string]$asset.url) -OutFile $archivePath -UseBasicParsing -Headers @{ 'User-Agent' = 'DA6IT-Wavelog-Offline-Logger-Build' }
        $actualHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualHash -ne $package.Sha256) {
            throw "Download-Pruefsumme fuer $($package.Name) stimmt nicht: $actualHash"
        }
        $extractPath = Join-Path $workDirectory ($package.Name + '-extract')
        Expand-Archive -LiteralPath $archivePath -DestinationPath $extractPath -Force
        Copy-Item -Path (Join-Path $extractPath '*') -Destination $OutputDirectory -Recurse -Force
    }
    if (-not (Test-Path -LiteralPath (Join-Path $OutputDirectory 'truststore\__init__.py')) -or
        -not (Test-Path -LiteralPath (Join-Path $OutputDirectory 'certifi\cacert.pem'))) {
        throw 'Die verifizierten TLS-Pakete wurden nicht vollständig entpackt.'
    }
    [System.IO.File]::WriteAllText($versionMarker, $versionText, [System.Text.UTF8Encoding]::new($false))
    Write-Host "Native TLS-Vertrauenspakete vorbereitet: $OutputDirectory"
} finally {
    if (Test-Path -LiteralPath $workDirectory) {
        Remove-Item -LiteralPath $workDirectory -Recurse -Force
    }
}

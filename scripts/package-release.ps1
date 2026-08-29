[CmdletBinding()]
param(
    [string]$OutputDirectory,
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $projectRoot 'dist'
} elseif (-not [System.IO.Path]::IsPathRooted($OutputDirectory)) {
    $OutputDirectory = Join-Path $projectRoot $OutputDirectory
}
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)

& (Join-Path $PSScriptRoot 'build-windows.ps1') -OutputDirectory $OutputDirectory -SkipTests:$SkipTests
if ($LASTEXITCODE -ne 0) {
    throw 'Windows-Build fehlgeschlagen.'
}

$coreText = Get-Content -LiteralPath (Join-Path $projectRoot 'logger_core.py') -Raw -Encoding UTF8
$versionMatch = [regex]::Match($coreText, '(?m)^VERSION\s*=\s*"([^"]+)"')
if (-not $versionMatch.Success) {
    throw 'Versionsnummer konnte nicht gelesen werden.'
}
$version = $versionMatch.Groups[1].Value
$exeName = "DA6IT.de-Wavelog-Offline-Logger-v$version-windows-x64.exe"
$zipName = "DA6IT.de-Wavelog-Offline-Logger-v$version-windows-x64.zip"
$exePath = Join-Path $OutputDirectory $exeName
$zipPath = Join-Path $OutputDirectory $zipName
$checksumPath = Join-Path $OutputDirectory 'SHA256SUMS.txt'

$tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$stage = Join-Path $tempRoot ("wavelog-offline-logger-release-" + [guid]::NewGuid().ToString('N'))
$stage = [System.IO.Path]::GetFullPath($stage)
if (-not $stage.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Unsicherer temporaerer Pfad: $stage"
}

try {
    New-Item -ItemType Directory -Path $stage | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $stage 'docs') | Out-Null
    Copy-Item -LiteralPath $exePath -Destination $stage
    Copy-Item -LiteralPath $checksumPath -Destination $stage
    Copy-Item -LiteralPath (Join-Path $projectRoot 'README.md') -Destination $stage
    Copy-Item -LiteralPath (Join-Path $projectRoot 'LICENSE') -Destination $stage
    Copy-Item -LiteralPath (Join-Path $projectRoot 'THIRD_PARTY_NOTICES.md') -Destination $stage
    Copy-Item -LiteralPath (Join-Path $projectRoot 'PRIVACY.md') -Destination $stage
    Copy-Item -LiteralPath (Join-Path $projectRoot 'CODE_SIGNING_POLICY.md') -Destination $stage
    Copy-Item -LiteralPath (Join-Path $projectRoot 'SECURITY.md') -Destination $stage
    Copy-Item -LiteralPath (Join-Path $projectRoot 'docs\USER_GUIDE.md') -Destination (Join-Path $stage 'docs')
    Copy-Item -LiteralPath (Join-Path $projectRoot 'docs\SCREENSHOTS.md') -Destination (Join-Path $stage 'docs')
    Copy-Item -LiteralPath (Join-Path $projectRoot 'docs\RELEASE_NOTES.md') -Destination (Join-Path $stage 'docs')
    Copy-Item -LiteralPath (Join-Path $projectRoot 'docs\TROUBLESHOOTING.md') -Destination (Join-Path $stage 'docs')
    Copy-Item -LiteralPath (Join-Path $projectRoot 'docs\SIGNPATH_SETUP.md') -Destination (Join-Path $stage 'docs')
    Copy-Item -LiteralPath (Join-Path $projectRoot 'docs\screenshots') -Destination (Join-Path $stage 'docs') -Recurse

    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }
    Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zipPath -CompressionLevel Optimal
} finally {
    if (Test-Path -LiteralPath $stage) {
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
}

$lines = foreach ($path in @($exePath, $zipPath)) {
    $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $([System.IO.Path]::GetFileName($path))"
}
[System.IO.File]::WriteAllText($checksumPath, (($lines -join "`n") + "`n"), [System.Text.UTF8Encoding]::new($false))

Write-Host "Release-Paket erfolgreich: $zipPath"
Write-Host "Pruefsummen: $checksumPath"

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

Push-Location $projectRoot
try {
    $python = (Get-Command python -ErrorAction Stop).Source
    $go = (Get-Command go -ErrorAction Stop).Source

    $pythonVersion = (& $python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $pythonVersion.StartsWith('3.12.')) {
        throw "Python 3.12.x wird benoetigt; gefunden: $pythonVersion"
    }

    $goVersion = (& $go version).Trim()
    if ($LASTEXITCODE -ne 0 -or $goVersion -notmatch '^go version go1\.23\.2\s') {
        throw "Go 1.23.2 wird fuer reproduzierbare Release-Builds benoetigt; gefunden: $goVersion"
    }

    $coreText = Get-Content -LiteralPath (Join-Path $projectRoot 'logger_core.py') -Raw -Encoding UTF8
    $bootstrapText = Get-Content -LiteralPath (Join-Path $projectRoot 'bootstrap_windows.go') -Raw -Encoding UTF8
    $coreMatch = [regex]::Match($coreText, '(?m)^VERSION\s*=\s*"([^"]+)"')
    $bootstrapMatch = [regex]::Match($bootstrapText, '(?m)^\s*appVersion\s*=\s*"([^"]+)"')
    if (-not $coreMatch.Success -or -not $bootstrapMatch.Success) {
        throw 'Versionsnummer konnte nicht aus den Quelldateien gelesen werden.'
    }

    $version = $coreMatch.Groups[1].Value
    if ($version -ne $bootstrapMatch.Groups[1].Value) {
        throw "Versionskonflikt: logger_core.py=$version, bootstrap_windows.go=$($bootstrapMatch.Groups[1].Value)"
    }

    $expectedAppDir = 'app-v' + $version.Replace('.', '')
    if ($bootstrapText -notmatch [regex]::Escape('"' + $expectedAppDir + '"')) {
        throw "Der Bootstrap-Appordner muss zur Version passen: $expectedAppDir"
    }

    if ($env:GITHUB_REF_TYPE -eq 'tag') {
        $expectedTag = 'v' + $version
        if ($env:GITHUB_REF_NAME -ne $expectedTag) {
        throw "Tag und Quellversion stimmen nicht ueberein: $($env:GITHUB_REF_NAME) != $expectedTag"
        }
    }

    if (-not $SkipTests) {
        & $python (Join-Path $projectRoot 'selftest.py')
        if ($LASTEXITCODE -ne 0) {
            throw 'Selftests fehlgeschlagen.'
        }
    }

    # Keep release staging separate from caches created by Codex or another
    # Windows account. Some sandbox-created Pillow folders carry child ACLs
    # that an interactive user cannot traverse even when the repository root
    # itself is writable.
    $pythonPackages = [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'build\embedded\python-packages\windows-x64-release'))
    $expectedPackagesRoot = [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'build\embedded\python-packages'))
    if (-not $pythonPackages.StartsWith($expectedPackagesRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsicherer Python-Paketpfad: $pythonPackages"
    }
    & (Join-Path $PSScriptRoot 'prepare-pillow-windows.ps1') -OutputDirectory $pythonPackages -PillowVersion '12.3.0'
    & (Join-Path $PSScriptRoot 'prepare-network-trust-windows.ps1') -OutputDirectory $pythonPackages `
        -TruststoreVersion '0.10.4' -CertifiVersion '2026.6.17'

    & (Join-Path $PSScriptRoot 'prepare-hamlib-windows.ps1')
    if ($LASTEXITCODE -ne 0) {
        throw 'Hamlib konnte nicht fuer den Windows-Build vorbereitet werden.'
    }

    New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
    $fileName = "DA6IT.de-Wavelog-Offline-Logger-v$version-windows-x64.exe"
    $outputPath = Join-Path $OutputDirectory $fileName

    $env:GOOS = 'windows'
    $env:GOARCH = 'amd64'
    $env:CGO_ENABLED = '0'
    # Keep the compiler cache inside the ignored build directory. This also
    # makes local builds work when the interactive user and workspace owner
    # differ and the default %LOCALAPPDATA% Go cache is not writable.
    $goCache = [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'build\go-cache'))
    $expectedBuildRoot = [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'build'))
    if (-not $goCache.StartsWith($expectedBuildRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsicherer Go-Cache-Pfad: $goCache"
    }
    New-Item -ItemType Directory -Path $goCache -Force | Out-Null
    $env:GOCACHE = $goCache
    $buildArgs = @(
        'build',
        '-trimpath',
        '-buildvcs=false',
        '-ldflags=-H windowsgui -s -w -buildid=',
        '-o', $outputPath,
        'bootstrap_windows.go'
    )
    & $go @buildArgs
    if ($LASTEXITCODE -ne 0) {
        throw 'Windows-Build fehlgeschlagen.'
    }

    $hash = (Get-FileHash -LiteralPath $outputPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $checksumPath = Join-Path $OutputDirectory 'SHA256SUMS.txt'
    $checksumLine = "$hash  $fileName`n"
    [System.IO.File]::WriteAllText($checksumPath, $checksumLine, [System.Text.UTF8Encoding]::new($false))

    Write-Host "Build erfolgreich: $outputPath"
    Write-Host "SHA-256: $hash"
} finally {
    Pop-Location
}

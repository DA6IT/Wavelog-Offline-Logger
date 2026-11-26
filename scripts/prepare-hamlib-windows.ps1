[CmdletBinding()]
param(
    [ValidateSet('x64', 'x86')]
    [string]$Arch = 'x64'
)

$ErrorActionPreference = 'Stop'
$hamlibVersion = '4.7.2'
$bits = if ($Arch -eq 'x86') { '32' } else { '64' }
$archiveName = "hamlib-w$bits-$hamlibVersion.zip"
$archiveUrl = "https://github.com/Hamlib/Hamlib/releases/download/$hamlibVersion/$archiveName"
# Official Hamlib release assets (SHA-256 as published by GitHub for the release).
$archiveSha256 = if ($Arch -eq 'x86') {
    '5e1a7d39de079488c3c9b3b10197d9bae923c7f2d6e9c107ae2182633ba313f8'  # pragma: allowlist secret (public release asset SHA-256)
} else {
    '8553bc6c5c6032e8debf99c017e98f58fed7e07e7c25d04815dc3e8bbe3304c7'  # pragma: allowlist secret (public release asset SHA-256)
}
$gccRuntime = if ($Arch -eq 'x86') { 'libgcc_s_dw2-1.dll' } else { 'libgcc_s_seh-1.dll' }

$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$buildRoot = [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'build'))
$downloadRoot = Join-Path $buildRoot 'downloads'
$archivePath = Join-Path $downloadRoot $archiveName
$embeddedRoot = [System.IO.Path]::GetFullPath((Join-Path $buildRoot "embedded\hamlib\windows-$Arch"))

if (-not $embeddedRoot.StartsWith($buildRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Unsicherer Hamlib-Ausgabepfad: $embeddedRoot"
}

New-Item -ItemType Directory -Path $downloadRoot -Force | Out-Null

$archiveValid = $false
if (Test-Path -LiteralPath $archivePath) {
    $existingHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $archiveValid = $existingHash -eq $archiveSha256
    if (-not $archiveValid) {
        Remove-Item -LiteralPath $archivePath -Force
    }
}

if (-not $archiveValid) {
    $temporaryPath = $archivePath + '.tmp'
    if (Test-Path -LiteralPath $temporaryPath) {
        Remove-Item -LiteralPath $temporaryPath -Force
    }
    $curl = (Get-Command curl.exe -ErrorAction Stop).Source
    & $curl --fail --location --silent --show-error --output $temporaryPath $archiveUrl
    if ($LASTEXITCODE -ne 0) {
        throw "Hamlib-Download fehlgeschlagen: $archiveUrl"
    }
    $downloadHash = (Get-FileHash -LiteralPath $temporaryPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($downloadHash -ne $archiveSha256) {
        Remove-Item -LiteralPath $temporaryPath -Force
        throw "Hamlib-Pruefsumme stimmt nicht: $downloadHash"
    }
    Move-Item -LiteralPath $temporaryPath -Destination $archivePath
}

if (Test-Path -LiteralPath $embeddedRoot) {
    Remove-Item -LiteralPath $embeddedRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $embeddedRoot -Force | Out-Null

Add-Type -AssemblyName System.IO.Compression.FileSystem
$prefix = "hamlib-w$bits-$hamlibVersion/"
$files = @(
    @{ Source = $prefix + 'bin/rigctld.exe'; Destination = 'rigctld.exe' },
    @{ Source = $prefix + 'bin/rotctld.exe'; Destination = 'rotctld.exe' },
    @{ Source = $prefix + 'bin/libhamlib-4.dll'; Destination = 'libhamlib-4.dll' },
    @{ Source = $prefix + 'bin/libusb-1.0.dll'; Destination = 'libusb-1.0.dll' },
    @{ Source = $prefix + "bin/$gccRuntime"; Destination = $gccRuntime },
    @{ Source = $prefix + 'bin/libwinpthread-1.dll'; Destination = 'libwinpthread-1.dll' },
    @{ Source = $prefix + 'COPYING.txt'; Destination = 'COPYING.txt' },
    @{ Source = $prefix + 'COPYING.LIB.txt'; Destination = 'COPYING.LIB.txt' },
    @{ Source = $prefix + 'LICENSE.txt'; Destination = 'LICENSE.txt' },
    @{ Source = $prefix + 'AUTHORS.txt'; Destination = 'AUTHORS.txt' },
    @{ Source = $prefix + 'README.md.txt'; Destination = 'README.md.txt' },
    @{ Source = $prefix + "README.w$bits-bin.txt"; Destination = "README.w$bits-bin.txt" }
)

$archive = [System.IO.Compression.ZipFile]::OpenRead($archivePath)
try {
    foreach ($file in $files) {
        $entry = $archive.GetEntry($file.Source)
        if ($null -eq $entry) {
            throw "Datei fehlt im offiziellen Hamlib-Archiv: $($file.Source)"
        }
        $destination = Join-Path $embeddedRoot $file.Destination
        $inputStream = $entry.Open()
        $outputStream = [System.IO.File]::Create($destination)
        try {
            $inputStream.CopyTo($outputStream)
        } finally {
            $outputStream.Dispose()
            $inputStream.Dispose()
        }
    }
} finally {
    $archive.Dispose()
}

$versionText = @"
Hamlib $hamlibVersion (Windows $Arch)
Official source: $archiveUrl
Archive SHA-256: $archiveSha256
Hamlib is distributed under the license terms included in this directory.
"@
[System.IO.File]::WriteAllText(
    (Join-Path $embeddedRoot 'HAMLIB_VERSION.txt'),
    $versionText,
    [System.Text.UTF8Encoding]::new($false)
)

& (Join-Path $embeddedRoot 'rigctld.exe') --version
if ($LASTEXITCODE -ne 0) {
    throw 'Die vorbereitete rigctld.exe konnte nicht ausgefuehrt werden.'
}
& (Join-Path $embeddedRoot 'rotctld.exe') --version
if ($LASTEXITCODE -ne 0) {
    throw 'Die vorbereitete rotctld.exe konnte nicht ausgefuehrt werden.'
}

Write-Host "Hamlib $hamlibVersion vorbereitet: $embeddedRoot"

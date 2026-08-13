[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$hamlibVersion = '4.7.2'
$archiveName = "hamlib-w64-$hamlibVersion.zip"
$archiveUrl = "https://github.com/Hamlib/Hamlib/releases/download/$hamlibVersion/$archiveName"
$archiveSha256 = '8553bc6c5c6032e8debf99c017e98f58fed7e07e7c25d04815dc3e8bbe3304c7'

$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$buildRoot = [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'build'))
$downloadRoot = Join-Path $buildRoot 'downloads'
$archivePath = Join-Path $downloadRoot $archiveName
$embeddedRoot = [System.IO.Path]::GetFullPath((Join-Path $buildRoot 'embedded\hamlib\windows-x64'))

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
$prefix = "hamlib-w64-$hamlibVersion/"
$files = @(
    @{ Source = $prefix + 'bin/rigctld.exe'; Destination = 'rigctld.exe' },
    @{ Source = $prefix + 'bin/libhamlib-4.dll'; Destination = 'libhamlib-4.dll' },
    @{ Source = $prefix + 'bin/libusb-1.0.dll'; Destination = 'libusb-1.0.dll' },
    @{ Source = $prefix + 'bin/libgcc_s_seh-1.dll'; Destination = 'libgcc_s_seh-1.dll' },
    @{ Source = $prefix + 'bin/libwinpthread-1.dll'; Destination = 'libwinpthread-1.dll' },
    @{ Source = $prefix + 'COPYING.txt'; Destination = 'COPYING.txt' },
    @{ Source = $prefix + 'COPYING.LIB.txt'; Destination = 'COPYING.LIB.txt' },
    @{ Source = $prefix + 'LICENSE.txt'; Destination = 'LICENSE.txt' },
    @{ Source = $prefix + 'AUTHORS.txt'; Destination = 'AUTHORS.txt' },
    @{ Source = $prefix + 'README.md.txt'; Destination = 'README.md.txt' },
    @{ Source = $prefix + 'README.w64-bin.txt'; Destination = 'README.w64-bin.txt' }
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
Hamlib $hamlibVersion (Windows x64)
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

Write-Host "Hamlib $hamlibVersion vorbereitet: $embeddedRoot"

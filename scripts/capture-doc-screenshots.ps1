param(
    [string]$OutputDirectory = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $projectRoot "docs\screenshots"
}

$pythonCandidates = @(
    (Join-Path $env:LOCALAPPDATA "AFU-Tools\WavelogOfflineLogger\runtime\python312\python.exe"),
    (Join-Path $projectRoot "build\embedded\python312\python.exe"),
    (Join-Path $projectRoot "build\doc-python312\python.exe")
)
$python = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $python) {
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($command -and $command.Source -notlike "*WindowsApps*") {
        $python = $command.Source
    }
}
if (-not $python) {
    throw "Keine nutzbare Python-Laufzeit gefunden. Bitte zuerst scripts\build-windows.ps1 ausfuehren."
}

Write-Host "Erzeuge vollstaendigen Screenshot-Satz mit isolierten Demo-Daten ..."
& $python (Join-Path $PSScriptRoot "capture-doc-screenshots.py") --output $OutputDirectory
if ($LASTEXITCODE -ne 0) {
    throw "Screenshot-Aufnahme fehlgeschlagen ($LASTEXITCODE)."
}

$required = @(
    "qso-logging.png", "fast-log.png", "contest-logging.png", "xota.png", "logbook-sync.png",
    "statistics.png", "cat-setup.png", "dx-cluster.png", "udp-logging.png",
    "settings-general.png", "settings-wavelog.png", "settings-callbook.png",
    "settings-data-connections.png", "sync-progress-running.png", "sync-progress-complete.png",
    "en/qso-logging.png", "en/fast-log.png", "en/contest-logging.png", "en/xota.png",
    "en/logbook-sync.png", "en/statistics.png", "en/cat-setup.png", "en/dx-cluster.png",
    "en/udp-logging.png", "en/settings-general.png", "en/settings-wavelog.png",
    "en/settings-callbook.png", "en/settings-data-connections.png",
    "en/sync-progress-running.png", "en/sync-progress-complete.png"
)
$missing = $required | Where-Object { -not (Test-Path -LiteralPath (Join-Path $OutputDirectory $_)) }
if ($missing) {
    throw "Folgende Pflicht-Screenshots fehlen: $($missing -join ', ')"
}

Write-Host "Screenshots vollstaendig: $OutputDirectory"

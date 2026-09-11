param(
    [string]$OutputDirectory = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $projectRoot "docs\screenshots"
}

$pythonCandidates = @()

if ($env:VIRTUAL_ENV) {
    $pythonCandidates += (Join-Path $env:VIRTUAL_ENV "Scripts\python.exe")
}

$command = Get-Command python -ErrorAction SilentlyContinue
if ($command -and $command.Source -notlike "*WindowsApps*") {
    $pythonCandidates += $command.Source
}

$pythonCandidates += @(
    (Join-Path $env:LOCALAPPDATA "AFU-Tools\WavelogOfflineLogger\runtime\python312\python.exe"),
    (Join-Path $projectRoot "build\embedded\python312\python.exe"),
    (Join-Path $projectRoot "build\doc-python312\python.exe")
)

$python = $null
foreach ($candidate in ($pythonCandidates | Select-Object -Unique)) {
    if (-not (Test-Path -LiteralPath $candidate)) {
        continue
    }

    & $candidate -c "import tkinter; from PIL import Image, ImageGrab" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $python = $candidate
        break
    }

    Write-Warning "Python-Laufzeit ohne benoetigte Screenshot-Abhaengigkeiten wird uebersprungen: $candidate"
}

if (-not $python) {
    throw "Keine Python-Laufzeit mit tkinter und Pillow gefunden. Aktiviere die Projekt-.venv oder installiere Pillow darin."
}

Write-Host "Screenshot-Python: $python"

Write-Host "Erzeuge vollstaendigen Screenshot-Satz mit isolierten Demo-Daten ..."
& $python (Join-Path $PSScriptRoot "capture-doc-screenshots.py") --output $OutputDirectory
if ($LASTEXITCODE -ne 0) {
    throw "Screenshot-Aufnahme fehlgeschlagen ($LASTEXITCODE)."
}

$required = @(
    "qso-logging.png", "qso-logging-english-dark.png", "fast-log.png", "contest-logging.png", "xota.png", "logbook-sync.png",
    "statistics.png", "qsl-card-manager.png", "qsl-recommendations.png", "usage-statistics-notice.png",
    "settings-usage-statistics.png", "cat-setup.png", "cat-flrig.png", "dx-cluster.png", "udp-logging.png",
    "settings-general.png", "settings-wavelog.png", "settings-callbook.png",
    "settings-data-connections.png", "sync-progress-running.png", "sync-progress-complete.png",
    "en/qso-logging.png", "en/fast-log.png", "en/contest-logging.png", "en/xota.png",
    "en/logbook-sync.png", "en/statistics.png", "en/qsl-card-manager.png", "en/qsl-recommendations.png",
    "en/usage-statistics-notice.png", "en/settings-usage-statistics.png",
    "en/cat-setup.png", "en/cat-flrig.png", "en/dx-cluster.png",
    "en/udp-logging.png", "en/settings-general.png", "en/settings-wavelog.png",
    "en/settings-callbook.png", "en/settings-data-connections.png",
    "en/sync-progress-running.png", "en/sync-progress-complete.png"
)
$missing = $required | Where-Object { -not (Test-Path -LiteralPath (Join-Path $OutputDirectory $_)) }
if ($missing) {
    throw "Folgende Pflicht-Screenshots fehlen: $($missing -join ', ')"
}

Write-Host "Screenshots vollstaendig: $OutputDirectory"

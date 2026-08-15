# Release-Prozess

## Voraussetzungen

- Python 3.12.10
- Go 1.23.2
- für lokale macOS-Pakete: macOS 11 oder neuer mit Xcode Command Line Tools und einer vollständigen Python-Installation (`pip` wird bei Bedarf über `ensurepip` aktiviert)
- für lokale Linux-Pakete: Debian/Ubuntu mit Build-Essentials, Tk, `python3-pip`, `dpkg-deb`, SquashFS und Zstandard
- saubere Arbeitskopie
- erfolgreich abgeschlossener praktischer Start- und Sync-Test

Eine lokale `pip`-Installation ist für den unterstützten Windows-Build nicht erforderlich. Das Buildskript lädt das offizielle Pillow-Wheel anhand der PyPI-Metadaten, prüft dessen veröffentlichte SHA-256-Prüfsumme und bettet es anschließend ein. Für einen frischen Build wird deshalb eine Internetverbindung benötigt.

## Vollständige Freigabe von Windows aus

Für v0.16.0 übernimmt das vorbereitete Skript Screenshot-Erzeugung mit isolierten Demo-Daten, Tests, lokalen Windows-Build, Branch, Pull Request, CI-Prüfung, Merge, Tag und das Warten auf alle Plattformpakete:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\publish-v0.16.0.ps1"
```

Der Push wird bewusst aus der normalen PowerShell des Repository-Eigentümers ausgeführt. Das Skript prüft vor dem Commit, dass weder `AGENTS.md`, Build-Verzeichnisse, ADI/SQLite-Dateien noch lokale Profil- oder Token-Dateien gestaged sind.

## Release Candidate bauen

```powershell
python selftest.py
.\scripts\capture-doc-screenshots.ps1
.\scripts\package-release.ps1
```

Anschließend EXE und ZIP aus `dist\` auf einem Windows-Testsystem prüfen.

## Version finalisieren

Für ein Release müssen mindestens diese Stellen konsistent auf dieselbe Version gesetzt werden:

- `logger_core.py`: `VERSION`
- `bootstrap_windows.go`: `appVersion`
- `bootstrap_windows.go`: versionsabhängiger `appDir`
- `packaging/arch/PKGBUILD`
- `CHANGELOG.md`
- `docs/RELEASE_NOTES.md`
- vollständiger Screenshot-Satz unter `docs/screenshots/`

Danach Tests und Paket-Build erneut ausführen.

## GitHub-Release

Der Workflow `.github/workflows/release.yml` reagiert auf Tags im Format `v*` und prüft, dass Tag und Quellversion übereinstimmen.

```powershell
git tag -a v0.16.0 -m "DA6IT.de Wavelog Offline Logger v0.16.0"
git push origin v0.16.0
```

Der Workflow:

1. führt die Selftests aus,
2. baut den Windows-x64-Bootstrapper,
3. erstellt das GitHub-Release mit Windows-EXE, ZIP und SHA-256-Prüfsummen,
4. baut anschließend auf echten GitHub-macOS-Runnern getrennte App-Bundles für Apple Silicon und Intel,
5. lädt beide macOS-ZIPs und ihre SHA-256-Dateien in dasselbe Release,
6. baut auf nativen Linux-x64- und Linux-ARM64-Runnern DEB, AppImage und ein Arch-Paket und lädt sie in dasselbe Release.

Tags mit Bindestrich wie `v0.11.2-rc1` werden als Vorabversion veröffentlicht.

## Manuelle Freigabeprüfung

- frische Windows-Benutzerumgebung
- Erststart einschließlich Runtime-Download
- bestehende Installation und Profilmigration
- lokales Logging ohne Internet
- Upload, Download, Konflikt und bewusste Löschung
- Profilwechsel und Profilduplikat
- Contest-Session
- Prüfsummen aus dem Release
- macOS Apple Silicon: Entpacken, Erststart per Rechtsklick **Öffnen**, lokales QSO und CAT
- macOS Intel: Entpacken, Erststart per Rechtsklick **Öffnen**, lokales QSO und CAT
- Linux x64: DEB und AppImage starten, lokales QSO, QRZ-Foto und CAT prüfen
- Linux ARM64: DEB und AppImage starten, lokales QSO und CAT prüfen

Die macOS-Pakete sind ad-hoc signiert, aber ohne Apple-Developer-Zertifikat nicht notarisiert. Vor jeder stabilen Freigabe müssen deshalb mindestens die erzeugten CI-Artefakte praktisch auf einem Apple-Silicon-Mac und einem Intel-Mac getestet werden.

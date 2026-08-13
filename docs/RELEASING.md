# Release-Prozess

## Voraussetzungen

- Python 3.12.10
- Go 1.23.2
- für lokale macOS-Pakete: macOS 11 oder neuer mit Xcode Command Line Tools
- saubere Arbeitskopie
- erfolgreich abgeschlossener praktischer Start- und Sync-Test

## Release Candidate bauen

```powershell
python selftest.py
.\scripts\package-release.ps1
```

Anschließend EXE und ZIP aus `dist\` auf einem Windows-Testsystem prüfen.

## Version finalisieren

Für ein Release müssen mindestens diese Stellen konsistent auf dieselbe Version gesetzt werden:

- `logger_core.py`: `VERSION`
- `bootstrap_windows.go`: `appVersion`
- `bootstrap_windows.go`: versionsabhängiger `appDir`
- `README.md`
- `CHANGELOG.md`

Danach Tests und Paket-Build erneut ausführen.

## GitHub-Release

Der Workflow `.github/workflows/release.yml` reagiert auf Tags im Format `v*` und prüft, dass Tag und Quellversion übereinstimmen.

```powershell
git tag -a v0.12.0-rc2 -m "DA6IT.de Wavelog Offline Logger v0.12.0-rc2"
git push origin v0.12.0-rc2
```

Der Workflow:

1. führt die Selftests aus,
2. baut den Windows-x64-Bootstrapper,
3. erstellt das GitHub-Release mit Windows-EXE, ZIP und SHA-256-Prüfsummen,
4. baut anschließend auf echten GitHub-macOS-Runnern getrennte App-Bundles für Apple Silicon und Intel,
5. lädt beide macOS-ZIPs und ihre SHA-256-Dateien in dasselbe Release.

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

Die macOS-Pakete sind ad-hoc signiert, aber ohne Apple-Developer-Zertifikat nicht notarisiert. Vor jeder stabilen Freigabe müssen deshalb mindestens die erzeugten CI-Artefakte praktisch auf einem Apple-Silicon-Mac und einem Intel-Mac getestet werden.

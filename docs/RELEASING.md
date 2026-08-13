# Release-Prozess

## Voraussetzungen

- Python 3.12.10
- Go 1.23.2
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
3. erzeugt ZIP und SHA-256-Prüfsummen,
4. erstellt das GitHub-Release mit automatisch erzeugten Release Notes.

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

macOS-Artefakte sind in diesem Repository-Stand noch nicht automatisiert, weil der dafür dokumentierte Launcher beziehungsweise das App-Bundle hier noch nicht als vollständiger Buildquelltext vorliegt.

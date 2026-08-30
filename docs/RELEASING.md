# Release-Prozess

## Voraussetzungen unter Windows

- Git for Windows
- GitHub CLI, mit `gh auth login` am Repository angemeldet
- Go 1.23.2 oder eine kompatible neuere Version
- die vom Logger eingerichtete private Python-3.12-Laufzeit oder eine lokale Python-Installation
- Internetzugang für Abhängigkeiten, GitHub und die Plattform-Builds
- erfolgreich abgeschlossener praktischer App-, Profil- und Sync-Test

Eine lokale `pip`-Installation ist für den unterstützten Windows-Build nicht erforderlich. Die Buildskripte laden benötigte Wheels anhand der offiziellen PyPI-Metadaten, prüfen festgelegte SHA-256-Prüfsummen und betten sie anschließend ein.

## Vollständige Freigabe von Windows aus

Das wiederverwendbare Skript liest die Version aus `logger_core.py` und prüft sie gegen den Windows-Bootstrapper und das Arch-Paket. Anschließend übernimmt es:

1. GitHub-Anmeldung und Werkzeugprüfung
2. vollständige Dokumentations-Screenshots
3. Python-Selftests sowie PowerShell-, Shell- und Go-Prüfungen
4. lokalen Windows-Release-Build
5. Release-Branch und kontrolliertes Staging ausschließlich freigegebener Dateien
6. Pull Request, alle CI-Prüfungen und Merge
7. Tag auf exakt dem bestätigten Merge-Commit
8. Warten auf Windows-, macOS- und Linux-Pakete im GitHub-Release

Aus einer normalen PowerShell starten:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\publish-release.ps1"
```

Das Skript prüft vor dem Commit, dass weder `AGENTS.md`, Build-Verzeichnisse, ADI/SQLite-Dateien noch lokale Profil- oder Token-Dateien gestaged sind. Existiert der Release-Tag bereits auf GitHub, wird er nicht verschoben oder überschrieben.

Nur in begründeten Fällen können bereits geprüfte Schritte übersprungen werden:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\publish-release.ps1" -SkipScreenshotCapture
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\publish-release.ps1" -SkipLocalBuild
```

## Version finalisieren

Für ein Release müssen mindestens diese Stellen konsistent auf dieselbe Version gesetzt werden:

- `logger_core.py`: `VERSION`
- `bootstrap_windows.go`: `appVersion`
- `bootstrap_windows.go`: versionsabhängiger `appDir`
- `packaging/arch/PKGBUILD`
- `CHANGELOG.md`
- `docs/RELEASE_NOTES.md`

Vor der Freigabe außerdem README, Benutzerhandbuch, Fehlerhilfe, Architektur- und Lizenzhinweise auf inhaltliche Änderungen prüfen.

## GitHub-Release

Der Workflow `.github/workflows/release.yml` reagiert auf Tags im Format `v*` und prüft, dass Tag und Quellversion übereinstimmen. Er:

1. führt die Selftests aus,
2. baut Windows x64 als EXE und ZIP,
3. baut macOS getrennt für Apple Silicon und Intel,
4. baut Linux x64 und ARM64 als DEB, AppImage und Arch-Paket,
5. veröffentlicht alle Pakete und SHA-256-Dateien im selben GitHub-Release.

Tags mit Bindestrich wie `v0.17.0-rc1` werden als Vorabversion veröffentlicht.

## Windows-Code-Signierung

v0.18.3 wird noch unsigniert veröffentlicht und dient anschließend als bestehendes, dokumentiertes Referenzrelease für die SignPath-Bewerbung. Es enthält bereits die später einzuschränkenden Windows-`VERSIONINFO`-Werte. Die öffentlichen Voraussetzungen und Rollen stehen in `CODE_SIGNING_POLICY.md`, der Datenschutz in `PRIVACY.md`; die konkrete Maintainer-Checkliste befindet sich in `docs/SIGNPATH_SETUP.md`.

Erst nach Annahme des Projekts werden die echten SignPath-Kennungen und Secrets in GitHub eingerichtet und der Release-Workflow erweitert. Bis dahin darf kein Workflow mit geratenen Platzhaltern aktiviert werden. Nach der Integration muss die von SignPath zurückgegebene EXE vor Veröffentlichung mit `Get-AuthenticodeSignature` geprüft werden; die SHA-256-Datei wird erst für das endgültige signierte Artefakt erzeugt.

## Manuelle Freigabeprüfung

- frische Windows-Benutzerumgebung und bestehende Installation
- lokales Logging ohne Internet
- Profilwechsel mit getrennten lokalen und Wavelog-Stationsprofilen
- Upload, profilbezogener Download, sichtbarer Sync-Fehler und bewusste Konfliktlösung
- direkter QRZ.com-Lookup ohne Wavelog-Konfiguration
- TLS-Verbindung zu Wavelog und QRZ
- QSO-Benachrichtigung, UDP, CAT und DX-Cluster
- Prüfsummen aus dem Release
- Windows-Dateieigenschaften: Product Name, Product/File Version, Beschreibung und Originaldateiname
- macOS Apple Silicon und Intel: Entpacken, Erststart per Rechtsklick **Öffnen**, lokales QSO und CAT
- Linux x64 und ARM64: DEB und AppImage starten, lokales QSO, QRZ-Foto, Benachrichtigung und CAT

Die Windows-Pakete bleiben bis zur SignPath-Annahme unsigniert. Die macOS-Pakete sind ad-hoc signiert, aber ohne Apple-Developer-Zertifikat nicht notarisiert. Vor einer stabilen Freigabe sollten die erzeugten CI-Artefakte zusätzlich praktisch auf den verfügbaren Zielsystemen getestet werden.

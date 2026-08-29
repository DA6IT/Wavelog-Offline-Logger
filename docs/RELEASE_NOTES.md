# DA6IT.de Wavelog Offline Logger v0.18.1

v0.18.1 ist ein kleines, weiterhin unsigniertes SignPath-Readiness-Release. Die Windows-Datei besitzt erstmals vollständige, automatisch geprüfte Versions- und Produktmetadaten. Außerdem sind Deinstallation, Rollen und die verwendete Python-Laufzeit öffentlich vollständig dokumentiert. Die Funktionen aus v0.18.0 bleiben unverändert enthalten.

## Windows-Dateimetadaten

Die Windows-EXE enthält jetzt eine native `VERSIONINFO`-Ressource:

- `ProductName`: `DA6IT.de Wavelog Offline Logger`
- `ProductVersion`: `0.18.1`
- `FileVersion`: `0.18.1`
- `FileDescription`: `DA6IT.de Wavelog Offline Logger`
- `OriginalFilename`: `DA6IT.de-Wavelog-Offline-Logger-v0.18.1-windows-x64.exe`
- numerische Dateiversion: `0.18.1.0`

Der Windows-Build liest diese Werte nach dem Einbetten direkt aus der fertigen EXE und bricht bei einer Abweichung ab. Damit entspricht das veröffentlichte, noch unsignierte Artefakt bereits dem Dateiformat, das nach einer SignPath-Annahme signiert werden soll.

## Deinstallation und Daten

README und Benutzerhandbuch erklären die Deinstallation getrennt für Windows, macOS, Debian/Ubuntu, Arch Linux und AppImage. Programmdateien, lokale App-Daten und ADI-Logbücher sind bewusst getrennt:

- Das Entfernen des Programms löscht keine ADI-Logbücher.
- Profile, Einstellungen, Tokens und Sync-Metadaten verbleiben standardmäßig im plattformspezifischen App-Datenordner.
- ADI-Dateien liegen standardmäßig unter `Dokumente/DA6IT.de Wavelog Logger/Profiles/…/Logs` oder an einem selbst gewählten Ort.
- Vor vollständiger Datenlöschung sollte das integrierte ZIP-Backup verwendet werden.

## SignPath-Vorbereitung

- Die Code-Signing-Richtlinie nennt nun ausdrücklich **Authors / Committers**, **Reviewers** und **Approvers**.
- CPython 3.12.10 und die Python Software Foundation License sind in `THIRD_PARTY_NOTICES.md` dokumentiert.
- Datenschutz, Sicherheitsmeldungen, Buildherkunft und der spätere manuelle Freigabeprozess bleiben öffentlich dokumentiert.
- Der SignPath-Workflow selbst wird erst nach Annahme des Projekts und Erhalt der echten Projektkennungen eingerichtet.

## Enthaltene Funktionen aus v0.18.0

- automatischer, per SHA-256 verifizierter In-App-Updater
- vollständiges ZIP-Backup und Restore aller Profile, Einstellungen, ADI-Dateien und Metadaten
- einmalige „Was ist neu?“-Übersicht
- DX-Spot des zuletzt geloggten QSOs auch nach dem automatischen Leeren des Formulars
- WSJT-X-Live-Vorschau, Worked-Historie, Entfernung und Peilung
- Wavelog-/QRZ-Callbook, profilbezogener Sync, Contest und xOTA
- Windows-, macOS- und Linux-Pakete

## Plattformen und Downloads

Der GitHub-Release baut und veröffentlicht automatisch:

- Windows x64: EXE und ZIP
- macOS Apple Silicon: App-ZIP
- macOS Intel: App-ZIP
- Linux x64 und ARM64: DEB, AppImage und Arch-Paket
- SHA-256-Prüfsummen für alle Pakete

## Code signing policy und bekannte Einschränkungen

v0.18.1 wird bewusst noch **ohne Windows-Code-Signatur** veröffentlicht. **[Free code signing provided by SignPath.io, certificate by SignPath Foundation](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.18.1/CODE_SIGNING_POLICY.md)** beschreibt den geplanten Ablauf. Nach diesem Referenzrelease kann die Aufnahme bei SignPath Foundation beantragt werden.

Die macOS-App ist ad-hoc signiert, aber nicht notarisiert. eQSL.cc bleibt **Coming soon**. Entfernung und Peilung aus Maidenhead-Locatoren sind Näherungswerte.

Datennutzung und optionale Netzwerkdienste beschreibt die [Datenschutzerklärung](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.18.1/PRIVACY.md). Das [Benutzerhandbuch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.18.1/docs/USER_GUIDE.md) enthält Installation, Deinstallation und vollständige Bedienung.

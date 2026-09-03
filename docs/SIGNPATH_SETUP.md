# SignPath-Einrichtung

Dieses Dokument ist die Maintainer-Checkliste für die Bewerbung und spätere CI-Integration. v0.19.0 bleibt noch unsigniert, enthält aber bereits die später zu prüfenden Windows-Dateimetadaten. Ein aktiver Workflow wird erst ergänzt, wenn SignPath das Projekt angenommen und die konkreten Organisations-, Projekt- und Richtlinienkennungen bereitgestellt hat; Platzhalter-Geheimnisse sollen keinen Release-Workflow absichtlich fehlschlagen lassen.

## Vor der Bewerbung

- v0.19.0 mit Windows-Artefakt, `VERSIONINFO` und vollständiger zweisprachiger Dokumentation veröffentlichen.
- In GitHub für das Maintainer-Konto Mehrfaktor-Authentifizierung aktivieren.
- Unter **Settings → Security** nach Möglichkeit Private Vulnerability Reporting aktivieren.
- Prüfen, dass README und Release-Seite auf **Code signing policy** und **Privacy policy** verweisen.
- Prüfen, dass Lizenz, Quellcode, Buildskripte und Drittanbieterhinweise öffentlich sind.
- Die Rollen aus `CODE_SIGNING_POLICY.md` bestätigen.
- Am veröffentlichten Windows-Artefakt `ProductName`, `ProductVersion`, `FileVersion`, `FileDescription` und `OriginalFilename` prüfen.

Antragsdaten:

- Project: `DA6IT.de Wavelog Offline Logger`
- Repository: `https://github.com/DA6IT/Wavelog-Offline-Logger`
- Download: `https://github.com/DA6IT/Wavelog-Offline-Logger/releases/latest`
- License: `MIT`
- Privacy policy: `https://github.com/DA6IT/Wavelog-Offline-Logger/blob/main/PRIVACY.md`
- Code signing policy: `https://github.com/DA6IT/Wavelog-Offline-Logger/blob/main/CODE_SIGNING_POLICY.md`
- Contact: `opensource@da6it.de`

Antrag: https://signpath.org/apply.html

## Nach der Annahme

1. SignPath-Organisation, Projekt, Artifact Configuration und Signing Policy mit den von SignPath vergebenen Werten anlegen beziehungsweise prüfen.
2. Das öffentliche GitHub-Repository als vertrauenswürdige Quelle verbinden.
3. Den Windows-Build aus `.github/workflows/release.yml` als vertrauenswürdigen Build konfigurieren.
4. Produktname `DA6IT.de Wavelog Offline Logger` und die zum Tag passende Produktversion als Metadatenrestriktionen erzwingen.
5. Einen getrennten Signing-Schritt mit manueller Freigabe einrichten; Geheimnisse ausschließlich als GitHub Actions Secrets speichern.
6. Erst die von SignPath zurückgegebene Datei veröffentlichen, danach deren SHA-256 erzeugen und `Get-AuthenticodeSignature` auf `Valid` prüfen.
7. Einen Test-Tag verwenden und anschließend README, Release Notes sowie diese Anleitung auf den tatsächlich aktiven Ablauf aktualisieren.

Die jeweils aktuellen Bedingungen stehen unter https://signpath.org/terms.html. Keine Projektkennung, Secret-Namen oder Workflow-Action dürfen vor der Freigabe geraten werden.

# DA6IT.de Wavelog Offline Logger v0.18.0

v0.18.0 macht Aktualisierung und Datensicherung deutlich komfortabler. Der Logger kann ein bestätigtes Update selbst laden und prüfen, vollständige lokale Daten als ZIP sichern und wiederherstellen und zeigt die wichtigsten Änderungen nach dem ersten Start einmalig an.

## Backup und Restore

- Unter **Einstellungen → Daten & Verbindungen** lässt sich eine vollständige ZIP-Sicherung erstellen.
- Enthalten sind alle Logger-Profile, Einstellungen, ADI-Logbücher, Metadatenbanken, Callbook-Caches sowie Contest- und xOTA-Zuordnungen.
- SQLite-Dateien werden als konsistente Snapshots gesichert.
- Vor einem Restore prüft die App Format, Pfade, Dateianzahl und entpackte Gesamtgröße des Archivs.
- Direkt vor jeder Wiederherstellung wird automatisch ein zusätzliches Sicherheitsbackup des aktuellen Stands erzeugt.
- Ein fehlgeschlagener Austausch kann zurückgerollt werden. Nach erfolgreichem Restore wird die App kontrolliert neu gestartet beziehungsweise beendet und kann mit den wiederhergestellten Daten geöffnet werden.

Backups können Zugangsdaten und API-Tokens enthalten. Sie sollten deshalb wie das Originalprofil geschützt und nicht öffentlich weitergegeben werden.

## Automatische, geprüfte Updates

- Der bekannte Update-Hinweis bietet nun an, die passende Plattformdatei direkt herunterzuladen.
- Downloads erfolgen ausschließlich über HTTPS und werden zwingend gegen die im GitHub-Release veröffentlichte SHA-256-Prüfsumme geprüft.
- Unter Windows beendet ein separater Helfer die laufende Anwendung, ersetzt die bisherige EXE und startet die neue Version.
- macOS und Linux laden das passende Paket verifiziert herunter und öffnen anschließend den Speicherort für die plattformübliche Installation.
- Ohne passende Prüfsumme oder bei einer Abweichung wird das Paket nicht installiert.

## Was ist neu?

Nach dem ersten Start von v0.18.0 erscheint einmalig eine kurze Übersicht der wichtigsten Änderungen in der gewählten Sprache. Sie kann später über **Hilfe → Was ist neu?** erneut geöffnet werden. Die App speichert lediglich lokal, welche Versionsübersicht bereits bestätigt wurde; daraus entsteht keine Telemetrie.

## DX-Spot nach dem Loggen

Nach einem erfolgreichen manuellen oder externen QSO wird das Formular weiterhin automatisch geleert. Rufzeichen, Frequenz, Band, Mode und Kommentar des zuletzt geloggten QSOs bleiben jedoch intern als Spot-Kandidat erhalten. **DX-Spot senden** verwendet nach einer klaren Bestätigung diese letzten Daten, solange noch kein neues QSO vorbereitet wurde.

## Bestehende Funktionen

Die Funktionen aus v0.17.2 bleiben vollständig enthalten:

- WSJT-X-Live-Vorschau und profilbezogener UDP-Empfang
- Worked-Historie im QSO-Formular
- Entfernung und Peilung aus Maidenhead-Locatoren
- Callbook-Anreicherung über Wavelog oder QRZ.com
- Contest-, xOTA-, ADIF-Import/-Export-, CAT-, DX-Cluster- und Wavelog-Sync-Funktionen
- getrennte Stationsprofile, Deutsch/Englisch und Light/Dark

## Plattformen und Downloads

Der GitHub-Release baut und veröffentlicht automatisch:

- Windows x64: EXE und ZIP
- macOS Apple Silicon: App-ZIP
- macOS Intel: App-ZIP
- Linux x64 und ARM64: DEB, AppImage und Arch-Paket
- SHA-256-Prüfsummen für alle Pakete

## Upgrade und Datensicherheit

v0.18.0 kann direkt über v0.17.2 oder eine ältere Version installiert werden. Vorhandene Profile, Einstellungen, ADI-Dateien, Sync-Metadaten und Callbook-Caches bleiben erhalten. Jedes neue QSO wird weiterhin zuerst lokal in der profilbezogenen ADI-Datei gespeichert.

Vor dem Upgrade empfiehlt sich erstmals die neue ZIP-Sicherung. Bei einem Upgrade von einer älteren Version kann alternativ weiterhin der vollständige Anwendungs- und externe ADI-Ordner manuell kopiert werden.

## Code signing policy und bekannte Einschränkungen

- v0.18.0 wird bewusst noch **ohne Windows-Code-Signatur** veröffentlicht. Erst danach wird die kostenlose Aufnahme bei SignPath Foundation beantragt. **[Free code signing provided by SignPath.io, certificate by SignPath Foundation](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.18.0/CODE_SIGNING_POLICY.md)** beschreibt den geplanten kontrollierten Ablauf.
- Die macOS-App ist technisch ad-hoc signiert, aber mangels Apple-Developer-Zertifikat nicht notarisiert.
- eQSL.cc bleibt **Coming soon**.
- Entfernung und Peilung aus Locatoren sind wegen der Zellgröße Näherungswerte.

Datennutzung und optionale Netzwerkdienste beschreibt die [Datenschutzerklärung](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.18.0/PRIVACY.md). Eine vollständige Bedienungsanleitung steht im [Benutzerhandbuch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.18.0/docs/USER_GUIDE.md); typische Probleme behandelt die [Fehlerhilfe](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.18.0/docs/TROUBLESHOOTING.md).

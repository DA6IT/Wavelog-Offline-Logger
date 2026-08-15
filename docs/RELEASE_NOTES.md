# DA6IT.de Wavelog Offline Logger v0.16.0

v0.16.0 ist das bisher größte Bedienungs- und Plattformupdate des Offline Loggers. Das Grundprinzip bleibt unverändert: Jedes QSO wird zuerst sicher in einer lokalen ADI-Datei gespeichert. Wavelog ist eine optionale Ergänzung und niemals Voraussetzung für das Loggen.

## Die wichtigsten Neuerungen

- modernisierte Oberfläche mit schmaler Navigation und DA6IT.de-Branding
- Deutsch oder Englisch sowie helles oder dunkles Theme
- Callbook-Abfrage über Wavelog oder direkt über QRZ.com
- automatische Übernahme von Name, Locator und QTH; optional wird das Stationsfoto angezeigt
- sicherer Wavelog-Online-Modus für den direkten Push neuer QSOs
- unabhängig aktivierbarer Voll-Sync beim Start und/oder Beenden
- sichtbares Sync-Statusfenster, das erst nach dem Ergebnis mit **OK** freigegeben wird
- TUNE/ATU über die bestehende Hamlib-CAT-Verbindung
- optionaler UDP-Autostart für WSJT-X und kompatible Programme
- Linux-Pakete für x64 und ARM64 zusätzlich zu Windows und macOS

## Sicherer Online-Modus

Die neue Statusanzeige unterscheidet **LOCAL ONLY** und **WAVELOG ONLINE**. Die App prüft dafür ausschließlich die konfigurierte Wavelog-API. Ein fehlendes Netzwerk erzeugt keine störende Fehlermeldung.

Die drei Optionen sind pro Profil unabhängig wählbar:

1. Neue QSOs im Online-Modus automatisch pushen
2. Vollständigen Sync beim App-Start ausführen
3. Vollständigen Sync beim Beenden ausführen

Der Laufzeit-Push erstellt nur neue, noch nie mit Wavelog verknüpfte QSOs. Änderungen, Löschungen, Downloads und Konfliktbehandlung bleiben bewusst dem vollständigen Sync vorbehalten. Damit wird der normale Online-Betrieb schnell, ohne die konservativen Sicherheitsregeln des bidirektionalen Abgleichs zu umgehen.

## Callbook und Offline-DXCC

Als Callbook-Quelle kann Wavelog oder QRZ.com gewählt werden. Sind für den direkten QRZ-Zugriff keine Zugangsdaten hinterlegt, verwendet die App Wavelog. Erfolgreiche Antworten werden profilspezifisch zwischengespeichert. Ohne Internet arbeitet die vorhandene CTY.DAT-Erkennung weiterhin vollständig offline.

Die vorbereiteten eQSL.cc-Felder sind weiterhin mit **Coming soon** gekennzeichnet. In v0.16.0 findet darüber weder ein Upload noch ein Download statt.

## Plattformen und Downloads

Der GitHub-Release-Workflow erzeugt:

- Windows x64: EXE und ZIP
- macOS Apple Silicon: App-ZIP
- macOS Intel: App-ZIP
- Linux x64: DEB, AppImage und Arch-Paket
- Linux ARM64: DEB, AppImage und Arch-Paket
- SHA-256-Prüfsummen für die jeweiligen Pakete

Windows-Pakete sind derzeit nicht digital signiert. Die macOS-App ist technisch ad-hoc signiert, aber nicht notarisiert. Bitte ausschließlich aus dem offiziellen GitHub-Release laden und die Prüfsumme vergleichen.

## Upgrade

Bestehende Profile, ADI-Logbücher und Sync-Zuordnungen werden weiterverwendet. ADI bleibt das primäre Logbuchformat; die SQLite-Dateien enthalten weiterhin nur Einstellungen, Cache- und Sync-Metadaten.

Vor dem ersten produktiven Start wird wie bei jedem größeren Update eine Sicherung der ADI- und Profilordner empfohlen.

## Bekannte Einschränkungen

- keine Windows-Code-Signatur
- keine Apple-Notarisierung
- eQSL.cc-Anbindung noch ohne Funktion
- Backup/Wiederherstellung erfolgt in dieser Version weiterhin manuell über die dokumentierten Datenordner

Eine vollständige Bedienungsanleitung steht im [Benutzerhandbuch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.16.0/docs/USER_GUIDE.md); typische Probleme behandelt die [Fehlerhilfe](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.16.0/docs/TROUBLESHOOTING.md).

Die GitHub-Dokumentation enthält zusätzlich einen reproduzierbar mit isolierten Demo-Daten erzeugten Screenshot-Satz aller Hauptseiten, aller Einstellungsreiter, beider Sync-Dialogzustände sowie der englischen Oberfläche im Dark-Theme.

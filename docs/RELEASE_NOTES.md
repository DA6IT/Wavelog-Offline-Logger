# DA6IT.de Wavelog Offline Logger v0.16.2

v0.16.2 verbessert die Profiltrennung beim Wavelog-Sync und die Zuverlässigkeit der Online-Dienste. Das lokale ADI-Logbuch bleibt die primäre Datenquelle; bestehende Profile, QSOs und Sync-Zuordnungen werden unverändert weiterverwendet.

## Wavelog-Sync nach Stationsprofil

- Der Logger lädt weiterhin über die Wavelog API v2, filtert die Remote-QSOs nun aber strikt nach der im aktiven Logger-Profil gespeicherten Stationsprofil-ID.
- Beim Wechsel zwischen Logger-Profilen wird jeweils nur das zugehörige Wavelog-Stationslogbuch angezeigt und synchronisiert.
- Das aktive Logbuch muss dafür in der Wavelog-Weboberfläche nicht umgestellt werden.
- Profilfremde Remote-QSOs werden nicht in das lokale ADI-Logbuch übernommen.
- Eine vorhandene Verknüpfung zu einem QSO aus einem anderen Stationsprofil wird nicht automatisch verändert. Sie erscheint als `SYNC-FEHLER` mit einer erklärenden Ursache und kann bewusst geprüft werden.

## QRZ.com und sichere Online-Verbindungen

- Direkte QRZ.com-Abfragen funktionieren unabhängig von einer Wavelog-Konfiguration.
- Ist **QRZ.com direkt** gewählt und sind gültige QRZ-Zugangsdaten hinterlegt, werden Name, Locator, QTH, Zonen und ein verfügbares Stationsfoto direkt geladen.
- Ist Wavelog als Callbook-Quelle gewählt, bleibt der vorhandene Wavelog-Lookup erhalten.
- Die eingebetteten Laufzeiten verwenden den nativen Zertifikatsspeicher von Windows, macOS beziehungsweise Linux.
- Ein geprüftes CA-Bundle dient als Fallback. Dadurch werden typische `CERTIFICATE_VERIFY_FAILED`-Fehler durch fehlende Zwischenzertifikate vermieden, ohne die Zertifikatsprüfung abzuschalten.

## Bedienung

- In **Einstellungen → Allgemein** lässt sich eine Desktop-Benachrichtigung nach jedem erfolgreich lokal gespeicherten QSO aktivieren oder deaktivieren.
- Die Benachrichtigung nutzt unter Windows den Infobereich, unter macOS die Mitteilungszentrale und unter Linux `notify-send`, sofern verfügbar.
- Im unteren Bereich der App stehen dezente Links zu **Buy Me a Coffee** und **PayPal** zur freiwilligen Unterstützung des Projekts bereit.

## Plattformen und Downloads

Der GitHub-Release enthält:

- Windows x64: EXE und ZIP
- macOS Apple Silicon: App-ZIP
- macOS Intel: App-ZIP
- Linux x64 und ARM64: DEB, AppImage und Arch-Paket
- SHA-256-Prüfsummen für die jeweiligen Pakete

Windows-Pakete sind derzeit nicht digital signiert. Die macOS-App ist technisch ad-hoc signiert, aber nicht notarisiert. Bitte ausschließlich aus dem offiziellen GitHub-Release laden.

## Upgrade

v0.16.2 kann direkt über v0.16.0 oder v0.16.1 verwendet werden. Es ist keine Datenmigration erforderlich. Bestehende Profile, ADI-Dateien, Einstellungen, Callbook-Cache und Sync-Metadaten bleiben erhalten.

Vor dem ersten vollständigen Sync eines Profils sollte kontrolliert werden, dass in dessen Einstellungen das richtige Wavelog-Stationsprofil gewählt ist. Der Logger nimmt keine automatische Reparatur alter profilfremder Verknüpfungen vor.

## Bekannte Einschränkungen

- keine Windows-Code-Signatur
- keine Apple-Notarisierung
- eQSL.cc-Anbindung weiterhin **Coming soon**
- Backup und Wiederherstellung weiterhin manuell über die dokumentierten Datenordner
- Linux-Desktop-Benachrichtigungen setzen eine vorhandene `notify-send`-Installation voraus

Eine vollständige Bedienungsanleitung steht im [Benutzerhandbuch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.16.2/docs/USER_GUIDE.md); typische Probleme behandelt die [Fehlerhilfe](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.16.2/docs/TROUBLESHOOTING.md).

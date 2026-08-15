# DA6IT.de Wavelog Offline Logger v0.16.1

v0.16.1 ist ein kompaktes Stabilitätsupdate für die neue Oberfläche aus v0.16.0. Das lokale ADI-Logbuch, bestehende Profile und sämtliche Sync-Zuordnungen bleiben unverändert erhalten.

## Verbesserungen

- Das Hauptfenster passt seine Darstellung jetzt proportional an die verfügbare Größe an.
- Schrift, Eingabefelder, Buttons, Tabellenzeilen, Kartenabstände, Seitenleiste, DA6IT.de-Logo und Callbook-Fotos skalieren gemeinsam.
- Die Oberfläche bleibt ohne zusätzliche Scrollleisten übersichtlich.
- Die unterstützte Mindestgröße beträgt 900 × 580 Pixel.
- Auf großen Fenstern wächst die Bedienoberfläche kontrolliert bis auf 110 Prozent.
- Nach dem Programmstart wird das fertig aufgebaute Fenster zuverlässig sichtbar in den Vordergrund geholt.
- Das Rufzeichenfeld erhält direkt den Eingabefokus.

## Plattformen und Downloads

Der GitHub-Release enthält weiterhin:

- Windows x64: EXE und ZIP
- macOS Apple Silicon: App-ZIP
- macOS Intel: App-ZIP
- Linux x64 und ARM64: DEB, AppImage und Arch-Paket
- SHA-256-Prüfsummen für die jeweiligen Pakete

Windows-Pakete sind derzeit nicht digital signiert. Die macOS-App ist technisch ad-hoc signiert, aber nicht notarisiert. Bitte ausschließlich aus dem offiziellen GitHub-Release laden.

## Upgrade

Die neue Version kann direkt über v0.16.0 installiert beziehungsweise gestartet werden. Bestehende Profile, ADI-Dateien, Einstellungen, Callbook-Cache und Sync-Metadaten werden weiterverwendet. Eine Datenmigration ist nicht erforderlich.

ADI bleibt das primäre Logbuchformat. Ohne erreichbares Wavelog arbeitet die Anwendung weiterhin still im Modus **LOCAL ONLY**.

## Bekannte Einschränkungen

- keine Windows-Code-Signatur
- keine Apple-Notarisierung
- eQSL.cc-Anbindung weiterhin **Coming soon**
- Backup und Wiederherstellung weiterhin manuell über die dokumentierten Datenordner

Eine vollständige Bedienungsanleitung steht im [Benutzerhandbuch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.16.1/docs/USER_GUIDE.md); typische Probleme behandelt die [Fehlerhilfe](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.16.1/docs/TROUBLESHOOTING.md).

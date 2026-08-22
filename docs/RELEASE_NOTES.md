# DA6IT.de Wavelog Offline Logger v0.17.0

v0.17.0 erweitert den Offline Logger um einen integrierten xOTA-Arbeitsbereich und eine sichere ADIF-Verwaltung. Jedes QSO wird weiterhin zuerst lokal gespeichert; bestehende Profile, Einstellungen und Sync-Zuordnungen werden übernommen.

## xOTA für portable Aktivierungen

- POTA, SOTA, WWFF, IOTA, COTA und WCA können in einer gemeinsamen Aktivierung kombiniert werden.
- Mehrere gleichzeitig gültige Referenzen lassen sich mit Strg/Shift gemeinsam auswählen und ohne Dubletten übernehmen.
- GPS ist optional; Koordinaten bleiben editierbar und der Maidenhead-Locator wird offline berechnet.
- Standort- und Referenzdienste ergänzen Daten nur bei bestehender Internetverbindung.
- Der vollständige offizielle POTA-Katalog wird lokal zwischengespeichert.
- Nahe POTA-Marker bis 10 km und deutlich gekennzeichnete Kandidaten bis 25 km berücksichtigen auch große Parks mit entferntem Mittelpunkt.
- Ein ausgewählter POTA-Park kann zur bewussten Grenzprüfung auf pota-map.info geöffnet werden.
- QSOs werden dauerhaft der Aktivierung zugeordnet. Eine passende Wavelog Station Location kann ausgewählt oder nach ausdrücklicher Bestätigung neu angelegt werden.

Referenzvorschläge sind kein automatischer Gültigkeitsnachweis. Der Benutzer prüft und bestätigt jede Referenz selbst.

## Eine ADI-Datei je Profil

- Pro Profil gibt es nun eine fortlaufende ADI-Datei statt täglicher Einzeldateien.
- Bestehende Tagesdateien werden vor der Migration als ZIP gesichert, zusammengeführt und durch erneutes Einlesen verifiziert.
- Erst nach erfolgreicher Prüfung werden die alten Quellen in ein Wiederherstellungsverzeichnis verschoben.
- ADIF-Import prüft Pflichtfelder, schützt vor Dubletten und legt vor dem Schreiben eine Sicherung an.
- ADIF-Export schreibt einen geprüften, portablen Datensatz aus dem lokalen Profil-Logbuch.

## Oberfläche und Windows-Integration

- Das xOTA-Layout passt Schaltflächen und Tabellen an die verfügbare Fensterbreite an.
- Die UTC-Uhr besitzt eine feste Breite und springt beim Sekundenwechsel nicht mehr.
- Das DA6IT.de-Funkmastlogo wird als Fenster-, Taskleisten-, Verknüpfungs- und EXE-Dateisymbol verwendet.
- Die Windows-GPS-Anbindung verwendet die aktuelle WinRT-Geoposition-API und fällt kontrolliert auf manuelle Eingabe zurück.

## Plattformen und Downloads

Der GitHub-Release enthält:

- Windows x64: EXE und ZIP
- macOS Apple Silicon: App-ZIP
- macOS Intel: App-ZIP
- Linux x64 und ARM64: DEB, AppImage und Arch-Paket
- SHA-256-Prüfsummen für alle Pakete

Windows-Pakete sind derzeit nicht digital signiert. Die macOS-App ist technisch ad-hoc signiert, aber nicht notarisiert. Bitte ausschließlich aus dem offiziellen GitHub-Release laden.

## Upgrade und Datensicherheit

v0.17.0 kann direkt über v0.16.x verwendet werden. Beim ersten Zugriff auf ein älteres Profil kann die einmalige ADI-Zusammenführung je nach Loggröße etwas dauern. Die App erzeugt vor jeder Migration eine Sicherung und löscht keine Quelldatei ohne erfolgreiche Verifikation.

Vor einem Upgrade empfiehlt sich trotzdem eine zusätzliche Kopie des vollständigen Anwendungs- und gegebenenfalls externen ADI-Ordners.

## Bekannte Einschränkungen

- keine Windows-Code-Signatur
- keine Apple-Notarisierung
- eQSL.cc-Anbindung weiterhin **Coming soon**
- vollständiges ZIP-Backup und Restore über die Oberfläche weiterhin geplant
- POTA-Katalogkoordinaten sind Marker und keine exakten Parkgrenzen

Eine vollständige Bedienungsanleitung steht im [Benutzerhandbuch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.17.0/docs/USER_GUIDE.md); typische Probleme behandelt die [Fehlerhilfe](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.17.0/docs/TROUBLESHOOTING.md).

# DA6IT.de Wavelog Offline Logger v0.17.1

v0.17.1 ist das Wartungsrelease für die neue Contest-Anbindung und die responsive Oberfläche. Es verbessert den Wavelog-Abgleich und verhindert abgeschnittene Felder oder Schaltflächen bei kleineren Fenstergrößen. xOTA, ADIF-Import/-Export und alle lokalen Daten aus v0.17.0 bleiben vollständig erhalten.

## Zuverlässig skalierende Oberfläche

- Alle Hauptseiten verkleinern jetzt nicht nur die Schrift, sondern auch Karten, Innenabstände, Aktionsleisten und Tabellenzeilen gemeinsam.
- Die Einstellungen wechseln bei begrenzter Höhe automatisch in eine Kompaktansicht: Eingabefelder und Aktionen bleiben sichtbar, optionale Erklärungstexte werden vorübergehend ausgeblendet.
- Contest-, QSO-Bearbeitungs-, Profil- und Sync-Dialoge passen sich der verfügbaren Bildschirmfläche an.
- Der Release-Ablauf prüft alle zehn Hauptseiten und jeden Einstellungs-Tab automatisch bei 900×580, 1100×680, 1355×790 und 1420×820 Pixeln. Abgeschnittene sichtbare Schaltflächen stoppen die Veröffentlichung.

## Contest-Sessions mit Wavelog

- Contest-Sessions werden für das gewählte Stationsprofil aus Wavelog geladen und lokal auswählbar gemacht.
- Lokal angelegte Sessions werden mit ADIF-Contest-Name, UTC-Zeitraum, Exchange-Einstellungen und Kommentar zu Wavelog übertragen.
- Die numerische Session-ID kommt automatisch von Wavelog; der Anwender muss keine freie ID suchen.
- Bereits verknüpfte QSOs werden der exakten Session zugeordnet und bestimmen beim Start die nächste freie Seriennummer.
- Neue Online-QSOs werden nach dem Upload automatisch mit der passenden Contest-Session verknüpft.
- Fehlt die noch junge Contest-API oder ein benötigter Token-Scope, bleiben lokales Contest-Logging und der QSO-Sync einschließlich `CONTEST_ID` verwendbar; vorhandene Contest-QSOs werden als lokale Auswahl nach ADIF-Name und Jahr rekonstruiert.
- Numerische IDs aus der Wavelog-Weboberfläche werden nicht mehr als ADIF-Contest-Name akzeptiert.
- Das Contest-Formular nutzt ein kompaktes mehrspaltiges Layout.

## xOTA für portable Aktivierungen (seit v0.17.0)

- POTA, SOTA, WWFF, IOTA, COTA und WCA können in einer gemeinsamen Aktivierung kombiniert werden.
- Mehrere gleichzeitig gültige Referenzen lassen sich mit Strg/Shift gemeinsam auswählen und ohne Dubletten übernehmen.
- GPS ist optional; Koordinaten bleiben editierbar und der Maidenhead-Locator wird offline berechnet.
- Standort- und Referenzdienste ergänzen Daten nur bei bestehender Internetverbindung.
- Der vollständige offizielle POTA-Katalog wird lokal zwischengespeichert.
- Nahe POTA-Marker bis 10 km und deutlich gekennzeichnete Kandidaten bis 25 km berücksichtigen auch große Parks mit entferntem Mittelpunkt.
- Ein ausgewählter POTA-Park kann zur bewussten Grenzprüfung auf pota-map.info geöffnet werden.
- QSOs werden dauerhaft der Aktivierung zugeordnet. Eine passende Wavelog Station Location kann ausgewählt oder nach ausdrücklicher Bestätigung neu angelegt werden.

Referenzvorschläge sind kein automatischer Gültigkeitsnachweis. Der Benutzer prüft und bestätigt jede Referenz selbst.

## Eine ADI-Datei je Profil (seit v0.17.0)

- Pro Profil gibt es nun eine fortlaufende ADI-Datei statt täglicher Einzeldateien.
- Bestehende Tagesdateien werden vor der Migration als ZIP gesichert, zusammengeführt und durch erneutes Einlesen verifiziert.
- Erst nach erfolgreicher Prüfung werden die alten Quellen in ein Wiederherstellungsverzeichnis verschoben.
- ADIF-Import prüft Pflichtfelder, schützt vor Dubletten und legt vor dem Schreiben eine Sicherung an.
- ADIF-Export schreibt einen geprüften, portablen Datensatz aus dem lokalen Profil-Logbuch.

## Windows-Integration

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

v0.17.1 kann direkt über v0.17.0 oder eine ältere Version installiert werden. Beim ersten Zugriff auf ein Profil aus v0.16.x kann die einmalige ADI-Zusammenführung je nach Loggröße etwas dauern. Die App erzeugt vor jeder Migration eine Sicherung und löscht keine Quelldatei ohne erfolgreiche Verifikation.

Vor einem Upgrade empfiehlt sich trotzdem eine zusätzliche Kopie des vollständigen Anwendungs- und gegebenenfalls externen ADI-Ordners.

## Bekannte Einschränkungen

- keine Windows-Code-Signatur
- keine Apple-Notarisierung
- eQSL.cc-Anbindung weiterhin **Coming soon**
- vollständiges ZIP-Backup und Restore über die Oberfläche weiterhin geplant
- POTA-Katalogkoordinaten sind Marker und keine exakten Parkgrenzen
- Der Wavelog-Contest-Abgleich benötigt eine Wavelog-Version mit `/api/v2/contest` sowie `contest:read` und `contest:write`; ältere Instanzen arbeiten lokal weiter

Eine vollständige Bedienungsanleitung steht im [Benutzerhandbuch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.17.1/docs/USER_GUIDE.md); typische Probleme behandelt die [Fehlerhilfe](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.17.1/docs/TROUBLESHOOTING.md).

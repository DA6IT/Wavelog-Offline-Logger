# DA6IT.de Wavelog Offline Logger v0.17.2

v0.17.2 erweitert das normale QSO-Formular um eine Live-Anbindung an WSJT-X, lokale Worked-Informationen sowie Entfernung und Peilung zur Gegenstation. Extern empfangene QSOs werden weiterhin zuerst sicher lokal gespeichert und können anschließend automatisch mit Callbook-Daten ergänzt und zu Wavelog übertragen werden.

## WSJT-X-Live-Vorschau

- Der Logger verarbeitet die laufenden Statuspakete des nativen WSJT-X-UDP-Protokolls.
- Sobald in WSJT-X eine Gegenstation gewählt ist, erscheinen Rufzeichen, Locator, Frequenz, Band, Mode und Report bereits während des QSOs im normalen QSO-Formular.
- Der vorhandene Callbook-Lookup kann dadurch schon vor dem Loggen Name, QTH, Foto und weitere Angaben anzeigen.
- Ein Live-Status speichert niemals selbstständig ein QSO. Erst das echte `QSO Logged`-Paket erzeugt den lokalen ADI-Eintrag.
- Nach einem erfolgreich manuell oder extern geloggten QSO wird das Formular automatisch geleert.
- Eine vorhandene manuelle Eingabe für ein anderes Rufzeichen wird nicht durch WSJT-X überschrieben.

Für die Live-Vorschau müssen primärer WSJT-X-UDP-Server und Logger dieselbe Adresse und denselben Port verwenden. Der sekundäre, als veraltet markierte ADIF-Broadcast überträgt ausschließlich abgeschlossene QSOs und keine Live-Statuspakete.

## Worked-Anzeige und lokale Historie

- Bereits auf demselben Band und Mode gearbeitete Rufzeichen werden im manuellen QSO-Formular grün markiert.
- Frühere QSOs auf anderen Bändern oder Modes erscheinen als gelber Hinweis.
- Unter dem Formular werden die letzten lokalen Verbindungen mit dem eingegebenen Rufzeichen einschließlich Datum, UTC-Zeit, Band und Mode angezeigt.
- Die Prüfung erfolgt ausschließlich gegen das aktive lokale Profil und benötigt keine Internetverbindung.

## Entfernung und Peilung

- Sobald im aktiven Profil ein eigener Maidenhead-Locator und für die Gegenstation ein Locator vorliegen, zeigt der Callbook-Bereich die ungefähre Entfernung in Kilometern an.
- Zusätzlich werden Anfangspeilung in Grad und Himmelsrichtung ausgegeben.
- Die Berechnung erfolgt offline anhand der Zellmittelpunkte der Maidenhead-Locatoren und funktioniert unabhängig von Wavelog oder QRZ.com.

## Callbook-Ergänzung externer QSOs

- Über WSJT-X oder ADIF/UDP empfangene QSOs werden unmittelbar lokal gespeichert.
- Fehlende Angaben wie Name, Locator, QTH, Land sowie CQ-/ITU-Zone können anschließend im Hintergrund über die konfigurierte Wavelog- oder QRZ.com-Quelle ergänzt werden.
- Bereits vom sendenden Programm gelieferte Werte werden niemals überschrieben.
- Ohne Internet oder bei einem Lookup-Fehler bleibt das sicher gespeicherte lokale QSO unverändert erhalten.
- Ein aktivierter automatischer Wavelog-Push wartet auf die laufende Ergänzung, damit die vollständigen Daten übertragen werden.

## UDP-Logging und Profile

- Beim Profilwechsel beendet der Logger den Listener des alten Profils.
- Für das neu gewählte Profil wird dessen eigene Host-/Port-Konfiguration automatisch gestartet, wenn UDP-Autostart aktiviert ist.
- Die Einstellung heißt deshalb nun ausdrücklich **UDP Logging beim App-Start und Profilwechsel automatisch starten**.

## Bedienung

- Die redundante Schaltfläche **Speichern + Neu** im normalen QSO-Formular wurde entfernt.
- **QSO speichern** speichert lokal, setzt anschließend alle QSO-Felder zurück und fokussiert erneut das Rufzeichenfeld.
- Fast Log, Contest Logging, xOTA, ADIF-Import/-Export und der stationsbezogene Wavelog-Sync aus v0.17.1 bleiben erhalten.

## Plattformen und Downloads

Der GitHub-Release enthält:

- Windows x64: EXE und ZIP
- macOS Apple Silicon: App-ZIP
- macOS Intel: App-ZIP
- Linux x64 und ARM64: DEB, AppImage und Arch-Paket
- SHA-256-Prüfsummen für alle Pakete

Windows-Pakete sind derzeit nicht digital signiert. Die macOS-App ist technisch ad-hoc signiert, aber nicht notarisiert. Bitte ausschließlich aus dem offiziellen GitHub-Release laden.

## Upgrade und Datensicherheit

v0.17.2 kann direkt über v0.17.1 oder eine ältere Version installiert werden. Vorhandene Profile, Einstellungen, ADI-Dateien, Sync-Metadaten und Callbook-Caches bleiben erhalten. Jedes neue QSO wird weiterhin zuerst lokal in der profilbezogenen ADI-Datei gespeichert.

Vor einem Upgrade empfiehlt sich trotzdem eine zusätzliche Kopie des vollständigen Anwendungs- und gegebenenfalls externen ADI-Ordners.

## Bekannte Einschränkungen

- keine Windows-Code-Signatur
- keine Apple-Notarisierung
- eQSL.cc-Anbindung weiterhin **Coming soon**
- vollständiges ZIP-Backup und Restore über die Oberfläche weiterhin geplant
- Entfernung und Peilung sind wegen der Locator-Zellgröße Näherungswerte

Eine vollständige Bedienungsanleitung steht im [Benutzerhandbuch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.17.2/docs/USER_GUIDE.md); typische Probleme behandelt die [Fehlerhilfe](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.17.2/docs/TROUBLESHOOTING.md).

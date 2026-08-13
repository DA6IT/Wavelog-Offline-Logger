# Benutzerhandbuch

## 1. Grundidee

Der Offline Logger schreibt QSOs zuerst in lokale ADI-Dateien. Wavelog wird bei vorhandener Verbindung synchronisiert. Dadurch bleibt das Erfassen auch ohne Internet möglich.

## 2. Erststart unter Windows

Beim ersten Start richtet der kleine Windows-Bootstrapper eine private Python-Laufzeit unter `%LOCALAPPDATA%\AFU-Tools\WavelogOfflineLogger\runtime\python312` ein. Der Download kommt von python.org und wird vor der Installation per SHA-256 geprüft.

Dieser Vorgang benötigt einmalig eine Internetverbindung und kann je nach Verbindung einige Minuten dauern. Spätere Starts benötigen für das lokale Logging kein Internet.

## 3. Logger-Profil einrichten

Ein Profil trennt Station, Zugangsdaten, Logpfad und Sync-Metadaten vollständig von anderen Profilen.

Für ein neues Profil werden mindestens benötigt:

- frei wählbarer Profilname
- Wavelog-Basis-URL
- Wavelog API-v2-Token
- Wavelog-Stationsprofil
- Stationsrufzeichen und Operator
- Ordner für die lokalen ADI-Dateien

Profile können umbenannt oder dupliziert werden. Beim Duplizieren werden Einstellungen übernommen, aber keine QSO- oder Sync-Zuordnungen kopiert.

## 4. QSO erfassen

1. Rufzeichen eingeben.
2. Band, Mode, Datum und UTC-Zeit prüfen.
3. RST und optionale Angaben ergänzen.
4. Bei Aktivierungen POTA-, SOTA- oder WWFF-Referenz eintragen.
5. QSO speichern.

Die Anwendung legt Tagesdateien im Format `CALLSIGN.YYYY-MM-DD.adi` an.

## 5. CAT einrichten

Der Windows-Build enthält Hamlib bereits. Eine zusätzliche Hamlib- oder CAT-Anwendung muss nicht installiert werden.

1. Funkgerät per USB oder serieller Schnittstelle mit Windows verbinden.
2. **CAT Setup** öffnen und das Funkgerätemodell suchen.
3. COM-Port sowie die vom Funkgerät verwendete Baudrate und die seriellen Parameter auswählen.
4. **Einstellungen speichern** auswählen.
5. Optional **Verbindung testen** ausführen.
6. **CAT starten** auswählen.

Die CAT-Konfiguration gehört immer zum aktiven Logger-Profil. Bei erfolgreicher Verbindung werden Frequenz, Band und Mode sowohl im normalen QSO-Formular als auch im Contest-Logging aktualisiert. Digitale Untermodi, die der Nutzer ausdrücklich ausgewählt hat, bleiben bei passenden USB-/LSB-Datenmodi erhalten.

**Einstellungen speichern**, **CAT starten** und **CAT stoppen** sind bewusst getrennte Aktionen. Der Logger startet CAT nach jedem Programmstart ausgeschaltet; die gespeicherten Geräte- und Schnittstellenwerte bleiben erhalten, die Verbindung wird aber erst nach einem ausdrücklichen Klick auf **CAT starten** aufgebaut.

## 6. DX Cluster über Telnet

Der DX Cluster ist eine optionale Online-Funktion. Ohne Internet bleibt der Logger vollständig für Offline-QSOs nutzbar und zeigt beim Start keinen Clusterfehler.

1. **DX Cluster** öffnen.
2. Den Standardserver `dxcluster.afu-tools.de` mit Telnet-Port `7300` verwenden oder eigene Serverdaten eintragen.
3. Das Login-Rufzeichen des aktiven Profils eintragen und **Einstellungen speichern** auswählen.
4. Mit **Verbinden** die Telnet-Sitzung bewusst starten.
5. Eingehende Spots nach Band, Mode, Zeitraum und Spotter-Region filtern. Die Region grenzt die meldende Station ein: Europa, Nordamerika, Südamerika, Asien/Pazifik, Afrika oder Unbekannt. Die Auswahl wird im aktiven Profil gespeichert. Standardmäßig sind nur die letzten 30 Minuten sichtbar. Neue Telnet-Spots werden während der Verbindung automatisch und ohne manuelles Neuladen ergänzt.

Ein Doppelklick stimmt bei laufendem CAT ausschließlich den TRX auf Spot-Frequenz und erkannten Mode ab und lässt die Cluster-Seite geöffnet. **QSO übernehmen** füllt anschließend Rufzeichen, Frequenz, Band und Mode im normalen QSO-Formular; gespeichert wird erst durch die normale QSO-Speicheraktion. `SSB` wird bandabhängig zu `LSB` oder `USB` aufgelöst. Fehlt im Spot jede Mode-Angabe, gilt dieselbe Vorgabe: LSB auf 160, 80 und 40 Metern, USB auf den höheren Bändern. Explizite Angaben wie FM, CW oder FT8 haben immer Vorrang.

Die Offline-Länderdatenbank ergänzt das DX-Land und Spotter-Land. Die Tabelle kann über jede Überschrift sortiert werden, also auch nach beiden Ländern. Ein zweiter Klick kehrt die Sortierrichtung um; beim Öffnen steht der jüngste Spot oben. Neue Spots werden zwei Minuten hellblau hinterlegt. Bereits gearbeitete Länder erhalten nur dann grüne Schrift, wenn sie im selben Mode wie der Spot gearbeitet wurden; bei einem in diesem Mode bereits gearbeiteten Rufzeichen werden sowohl Rufzeichen als auch Land grün dargestellt. Maßgeblich sind ausschließlich die lokalen ADI-Dateien des aktiven Profils.

Um selbst zu spotten, Rufzeichen und Frequenz im QSO-Formular eintragen und **DX-Spot senden** auswählen. Danach kann ein optionaler Kommentar ergänzt werden. Erst die anschließende Bestätigung sendet den Spot öffentlich. Zeilenumbrüche werden entfernt und Kommentare gekürzt; ein Spot wird niemals automatisch beim Speichern eines QSOs gesendet.

Serverdaten und Login-Rufzeichen werden pro Logger-Profil gespeichert. Die Verbindung selbst bleibt nach jedem Programmstart aus und wird bei Profilwechsel oder Programmende geschlossen.

## 7. WSJT-X und andere Programme über UDP

Unter **UDP Logging** können externe Programme ein fertig geloggtes QSO direkt an den Offline Logger senden. Unterstützt werden das native WSJT-X-Protokoll sowie vollständige ADIF-Datensätze mit `<EOR>` über UDP.

1. Im Offline Logger **UDP Logging** öffnen.
2. Für Programme auf demselben PC die Bind-Adresse `127.0.0.1` verwenden.
3. Einen freien UDP-Port eintragen, beispielsweise `2237`, und **Einstellungen speichern** auswählen.
4. In WSJT-X unter **File > Settings > Reporting** beim UDP Server dieselbe Adresse und Portnummer eintragen.
5. Im Offline Logger **UDP starten** auswählen.

Wenn der primäre Port bereits von JTAlert, GridTracker oder einem anderen Programm verwendet wird, kann der zusätzliche „logged contact ADIF broadcast“ von WSJT-X an einen anderen freien Port gesendet werden, beispielsweise `2333`. Der Port ist pro Logger-Profil frei wählbar. Eine Änderung wird nach **UDP stoppen** und erneutem **UDP starten** wirksam; ein Neustart des gesamten Programms ist nicht erforderlich.

Jedes akzeptierte QSO wird in der ADI-Datei des aktiven Profils als `LOCAL ONLY` gespeichert. Identische Mehrfachübertragungen werden ignoriert. Der Empfänger startet nach jedem Programmstart bewusst ausgeschaltet und wird bei einem Profilwechsel oder beim Beenden sicher gestoppt.

## 8. Synchronisieren

Vor dem ersten Sync sollte die Verbindung in den Profileinstellungen getestet werden.

Der Abgleich unterscheidet:

- nur lokal geändert: Upload zu Wavelog
- nur in Wavelog geändert: lokale ADI-Aktualisierung
- auf beiden Seiten geändert: sichtbarer Konflikt
- remote gelöscht und lokal unverändert: lokale Entfernung
- ausdrücklich lokal gelöscht: Remote-Löschanforderung
- außerhalb der App lokal verschwunden: Wiederherstellung aus Wavelog

Clubtokens können abhängig von ihren Berechtigungen nur einen Teil der QSOs sehen. Eine unvollständige Sicht darf nicht als Beweis für Remote-Löschungen behandelt werden.

## 9. Konflikte

Ein Konflikt bedeutet, dass lokale und entfernte Daten seit der letzten gemeinsamen Version verändert wurden. Prüfe beide Fassungen bewusst und entscheide, welche Werte übernommen werden sollen. Die Anwendung wählt absichtlich keine Seite automatisch aus.

## 10. Profil löschen

Das Löschen eines Profils ist immer lokal. Es löscht weder ein Wavelog-Stationsprofil noch Wavelog-QSOs.

Optional können die lokalen ADI-Dateien des Profils entfernt werden. Diese Option greift nur für `.adi`-Dateien und wird verweigert, wenn ein anderes Profil denselben Logordner verwendet.

## 11. Update-Hinweis

Beim Programmstart prüft die Anwendung im Hintergrund die öffentliche GitHub-Release-Liste. Ist eine neuere passende Version verfügbar, erscheint ein Hinweis mit einem Link zur Downloadseite. Ohne Internet oder bei einem Netzwerkfehler erscheint keine Fehlermeldung; das Offline-Logging funktioniert unverändert weiter.

## 12. Datensicherung

Vor Updates und regelmäßig im Betrieb sollten gesichert werden:

- alle verwendeten ADI-Ordner
- `%LOCALAPPDATA%\AFU-Tools\WavelogOfflineLogger\`

API-Tokens oder Sicherungen mit Tokens sollten nicht öffentlich geteilt werden.

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
4. **Verbindung testen** ausführen.
5. CAT aktivieren und die Einstellungen speichern.

Die CAT-Konfiguration gehört immer zum aktiven Logger-Profil. Bei erfolgreicher Verbindung werden Frequenz, Band und Mode sowohl im normalen QSO-Formular als auch im Contest-Logging aktualisiert. Digitale Untermodi, die der Nutzer ausdrücklich ausgewählt hat, bleiben bei passenden USB-/LSB-Datenmodi erhalten.

## 6. Synchronisieren

Vor dem ersten Sync sollte die Verbindung in den Profileinstellungen getestet werden.

Der Abgleich unterscheidet:

- nur lokal geändert: Upload zu Wavelog
- nur in Wavelog geändert: lokale ADI-Aktualisierung
- auf beiden Seiten geändert: sichtbarer Konflikt
- remote gelöscht und lokal unverändert: lokale Entfernung
- ausdrücklich lokal gelöscht: Remote-Löschanforderung
- außerhalb der App lokal verschwunden: Wiederherstellung aus Wavelog

Clubtokens können abhängig von ihren Berechtigungen nur einen Teil der QSOs sehen. Eine unvollständige Sicht darf nicht als Beweis für Remote-Löschungen behandelt werden.

## 7. Konflikte

Ein Konflikt bedeutet, dass lokale und entfernte Daten seit der letzten gemeinsamen Version verändert wurden. Prüfe beide Fassungen bewusst und entscheide, welche Werte übernommen werden sollen. Die Anwendung wählt absichtlich keine Seite automatisch aus.

## 8. Profil löschen

Das Löschen eines Profils ist immer lokal. Es löscht weder ein Wavelog-Stationsprofil noch Wavelog-QSOs.

Optional können die lokalen ADI-Dateien des Profils entfernt werden. Diese Option greift nur für `.adi`-Dateien und wird verweigert, wenn ein anderes Profil denselben Logordner verwendet.

## 9. Update-Hinweis

Beim Programmstart prüft die Anwendung im Hintergrund die öffentliche GitHub-Release-Liste. Ist eine neuere passende Version verfügbar, erscheint ein Hinweis mit einem Link zur Downloadseite. Ohne Internet oder bei einem Netzwerkfehler erscheint keine Fehlermeldung; das Offline-Logging funktioniert unverändert weiter.

## 10. Datensicherung

Vor Updates und regelmäßig im Betrieb sollten gesichert werden:

- alle verwendeten ADI-Ordner
- `%LOCALAPPDATA%\AFU-Tools\WavelogOfflineLogger\`

API-Tokens oder Sicherungen mit Tokens sollten nicht öffentlich geteilt werden.

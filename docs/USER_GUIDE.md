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

## 5. Synchronisieren

Vor dem ersten Sync sollte die Verbindung in den Profileinstellungen getestet werden.

Der Abgleich unterscheidet:

- nur lokal geändert: Upload zu Wavelog
- nur in Wavelog geändert: lokale ADI-Aktualisierung
- auf beiden Seiten geändert: sichtbarer Konflikt
- remote gelöscht und lokal unverändert: lokale Entfernung
- ausdrücklich lokal gelöscht: Remote-Löschanforderung
- außerhalb der App lokal verschwunden: Wiederherstellung aus Wavelog

Clubtokens können abhängig von ihren Berechtigungen nur einen Teil der QSOs sehen. Eine unvollständige Sicht darf nicht als Beweis für Remote-Löschungen behandelt werden.

## 6. Konflikte

Ein Konflikt bedeutet, dass lokale und entfernte Daten seit der letzten gemeinsamen Version verändert wurden. Prüfe beide Fassungen bewusst und entscheide, welche Werte übernommen werden sollen. Die Anwendung wählt absichtlich keine Seite automatisch aus.

## 7. Profil löschen

Das Löschen eines Profils ist immer lokal. Es löscht weder ein Wavelog-Stationsprofil noch Wavelog-QSOs.

Optional können die lokalen ADI-Dateien des Profils entfernt werden. Diese Option greift nur für `.adi`-Dateien und wird verweigert, wenn ein anderes Profil denselben Logordner verwendet.

## 8. Datensicherung

Vor Updates und regelmäßig im Betrieb sollten gesichert werden:

- alle verwendeten ADI-Ordner
- `%LOCALAPPDATA%\AFU-Tools\WavelogOfflineLogger\`

API-Tokens oder Sicherungen mit Tokens sollten nicht öffentlich geteilt werden.

# Benutzerhandbuch

## 1. Grundidee

Der Offline Logger schreibt QSOs zuerst in lokale ADI-Dateien. Wavelog wird ausschließlich über den manuellen Sync angesprochen. Dadurch bleibt das Erfassen auch ohne Internet möglich.

## 2. Erststart unter Windows

Beim ersten Start richtet der Windows-Bootstrapper eine private Python-Laufzeit unter `%LOCALAPPDATA%\AFU-Tools\WavelogOfflineLogger\runtime\python312` ein. Der Download kommt von python.org und wird vor der Installation per SHA-256 geprüft.

Dieser Vorgang benötigt einmalig eine Internetverbindung. Spätere Starts und das lokale Logging funktionieren offline.

## 2a. Erststart unter macOS

Im GitHub-Release das Paket `macos-arm64` für Apple Silicon oder `macos-x64` für einen Intel-Mac laden. ZIP entpacken und `DA6IT.de Wavelog Offline Logger.app` nach **Programme** verschieben. Python, Tk und Hamlib sind bereits im App-Bundle enthalten.

Die kostenlose Community-App ist derzeit nicht von Apple notarisiert. Beim ersten Start deshalb im Finder die App mit Rechtsklick auswählen, **Öffnen** anklicken und die Rückfrage bestätigen. Danach lässt sie sich normal starten. Lokales Logging benötigt keine Internetverbindung.

## 3. Logger-Profil einrichten

Ein Profil trennt Station, Zugangsdaten, Logpfad und Sync-Metadaten vollständig von anderen Profilen. Benötigt werden insbesondere Stationsrufzeichen beziehungsweise Operator und ein Ordner für die lokalen ADI-Dateien. Für den Sync kommen Wavelog-URL, API-v2-Token und Wavelog-Stationsprofil hinzu.

Profile können umbenannt oder dupliziert werden. Beim Duplizieren werden Einstellungen übernommen, aber keine QSO- oder Sync-Zuordnungen kopiert.

## 4. QSO erfassen

1. Rufzeichen eingeben.
2. Band, Mode, Datum und UTC-Zeit prüfen.
3. RST und optionale Angaben ergänzen.
4. QSO speichern.

Die Anwendung legt Tagesdateien im Format `CALLSIGN.YYYY-MM-DD.adi` an.

## 5. Fast Log / DXpedition

Fast Log ist für Pileups und schnelle QSO-Folgen gedacht:

1. **Fast Log / DXpedition** öffnen.
2. Band, Mode, Frequenz, Rapporte und Leistung einmal festlegen.
3. Rufzeichen eingeben und Enter drücken.
4. Für das nächste QSO sofort das nächste Rufzeichen eingeben.

Datum und UTC-Zeit werden automatisch gesetzt. Jedes QSO wird unmittelbar lokal als `LOCAL ONLY` gespeichert. Wavelog wird dabei nicht kontaktiert. Ein Dupe-Hinweis vergleicht Rufzeichen, Band und Mode, verhindert das Speichern aber nicht.

**Werte aus QSO/CAT** übernimmt die aktuellen Frequenz-, Band-, Mode- und Leistungswerte. **Letztes QSO zurücknehmen** löscht nach Bestätigung ausschließlich das letzte noch nicht synchronisierte QSO dieser Sitzung.

## 6. CAT einrichten

Der Windows-Build enthält Hamlib bereits. Eine zusätzliche Hamlib- oder CAT-Anwendung muss nicht installiert werden.

1. Funkgerät verbinden und **CAT Setup** öffnen.
2. Funkgerätemodell, COM-Port und serielle Parameter auswählen.
3. **Einstellungen speichern** und optional **Verbindung testen** auswählen.
4. Mit **CAT starten** die Verbindung aufbauen.

CAT gehört zum aktiven Logger-Profil und startet nach jedem Programmstart bewusst ausgeschaltet. Frequenz, Band und Mode werden in normales QSO-, Fast- und Contest-Logging übernommen. **CAT stoppen** oder das Beenden des Loggers beendet auch den gestarteten `rigctld`-Prozess.

## 7. DX Cluster über Telnet

Der DX Cluster ist eine optionale Online-Funktion. Ohne Internet bleibt der Logger für lokale QSOs vollständig nutzbar.

### Spots empfangen

1. **DX Cluster** öffnen.
2. `dxcluster.afu-tools.de:7300` verwenden oder eigene Empfangsdaten eintragen.
3. **Einstellungen speichern** und anschließend **Verbinden** auswählen.
4. Spots nach Band, Mode, Zeitraum und Spotter-Region filtern.

Das Login-Rufzeichen wird automatisch aus dem aktiven Stationsprofil übernommen. Neue Spots erscheinen live; standardmäßig sind die letzten 30 Minuten sichtbar. Die Tabelle lässt sich über jede Überschrift sortieren.

Ein Doppelklick stimmt bei laufendem CAT den TRX auf Spot-Frequenz und erkannten Mode ab. **QSO übernehmen** füllt danach das normale QSO-Formular, speichert aber noch kein QSO.

Explizite Mode-Hinweise im Kommentar haben Vorrang. Fehlt der Mode, prüft der Logger typische FT8-Frequenzen und eindeutige Bereiche des IARU-Region-1-Bandplans. In mehrdeutigen Bereichen gilt weiterhin LSB auf 160, 80 und 40 Metern, sonst USB.

Neue Spots werden kurz hellblau markiert. Grüne Worked-Markierungen gelten ausschließlich für dasselbe Band und denselben Mode. Die Informationen stammen aus den lokalen ADI-Dateien des aktiven Profils.

### Selbst spotten

Die Spotter-Verbindung ist vom Empfang getrennt. Unter **Einstellungen** sind standardmäßig `dxcluster.afu-tools.de:7301` und das Rufzeichen des aktiven Profils eingetragen.

Im QSO-Formular **DX-Spot senden** auswählen, optional einen Kommentar eingeben und den öffentlichen Versand bestätigen. Die Spotter-Verbindung wird nur dafür aufgebaut. Der gewählte Mode wird als Hinweis in den DXSpider-Kommentar aufgenommen. Es wird niemals automatisch beim Loggen gespottet.

## 8. WSJT-X und andere Programme über UDP

Unter **UDP Logging** können das native WSJT-X-Protokoll und vollständige ADIF-Datensätze mit `<EOR>` empfangen werden.

1. Bind-Adresse `127.0.0.1` und einen freien Port eintragen.
2. In WSJT-X dieselbe Adresse und Portnummer konfigurieren.
3. **UDP starten** auswählen.

Bei einer Portänderung genügen **UDP stoppen** und **UDP starten**. Empfangene QSOs werden lokal als `LOCAL ONLY` gespeichert; identische Mehrfachübertragungen werden ignoriert.

## 9. Synchronisieren

Der Abgleich unterscheidet:

- nur lokal geändert: Upload zu Wavelog
- nur in Wavelog geändert: lokale ADI-Aktualisierung
- auf beiden Seiten geändert: sichtbarer Konflikt
- ausdrücklich lokal gelöscht: Remote-Löschanforderung
- außerhalb der App lokal verschwunden: Wiederherstellung aus Wavelog

Eine unvollständige Sicht eines Clubtokens darf nicht als Beweis für Remote-Löschungen behandelt werden.

## 10. Konflikte

Ein Konflikt bedeutet, dass lokale und entfernte Daten seit der letzten gemeinsamen Version verändert wurden. Die Anwendung wählt absichtlich keine Seite automatisch aus.

## 11. Profil löschen

Das Löschen eines Profils ist immer lokal. Es löscht weder ein Wavelog-Stationsprofil noch Wavelog-QSOs. Das optionale Entfernen lokaler ADI-Dateien wird verweigert, wenn ein anderes Profil denselben Logordner verwendet.

## 12. Update-Hinweis

Beim Programmstart prüft die Anwendung im Hintergrund die öffentliche GitHub-Release-Liste. Ohne Internet oder bei einem Netzwerkfehler erscheint keine Fehlermeldung.

## 13. Datensicherung

Regelmäßig gesichert werden sollten:

- alle verwendeten ADI-Ordner
- `%LOCALAPPDATA%\AFU-Tools\WavelogOfflineLogger\`

API-Tokens oder Sicherungen mit Tokens sollten nicht öffentlich geteilt werden.

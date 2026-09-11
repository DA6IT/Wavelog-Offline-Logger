# DA6IT.de Wavelog Offline Logger v0.20.2

## Deutsch

v0.20.2 ist ein Wartungsupdate mit Schwerpunkt auf ruhigerem Wavelog-Sync, schnellerer Logbuchbedienung und besserem Schutz vor doppelten digitalen QSOs.

### Highlights

- **Auto-Sync mit Verzögerung:** Neue QSOs werden im Online-Modus standardmäßig fünf Minuten gesammelt und anschließend gemeinsam zu Wavelog übertragen. Die Verzögerung kann pro Profil zwischen 1 und 60 Minuten gewählt werden.
- **Mehrere QSOs schnell löschen:** Im Logbuch können mehrere QSOs gemeinsam ausgewählt und in einem Schritt gelöscht werden. Auch bei großen Logbüchern bleibt der Vorgang deutlich schneller.
- **Klare Warnung vor Wavelog-Löschung:** Bereits synchronisierte QSOs werden beim Löschen deutlich gekennzeichnet. Ihre Remote-Löschung erfolgt weiterhin erst beim nächsten vollständigen Sync.
- **Besserer Dublettenschutz:** Wiederholte Abschlussmeldungen aus WSJT-X und externen digitalen Logs führen deutlich seltener zu doppelten oder dreifachen QSOs.
- **Dubletten schon beim Import erkennen:** Auch doppelte Einträge, die bereits in einer WSJT-X-ADIF-Datei vorhanden sind, werden innerhalb desselben Imports erkannt und übersprungen.

### Synchronisierung und Sicherheit

Der verzögerte automatische Upload überträgt ausschließlich neue lokale QSOs. Er führt keine Remote-Löschungen aus.

Wird ein bereits mit Wavelog verknüpftes QSO bewusst lokal gelöscht, bleibt die Löschabsicht gespeichert und wird erst beim nächsten vollständigen Sync zu Wavelog übertragen. Vorher zeigt der Logger jetzt eine deutlichere Warnung mit der Anzahl betroffener QSOs.

Das lokale ADIF-Log bleibt weiterhin die maßgebliche QSO-Datenquelle.

### Danke

Vielen Dank an **DO1DX** für das hilfreiche Feedback und die Praxishinweise, die direkt in diese Verbesserungen eingeflossen sind.

Dokumentation: [Deutsch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.20.2/docs/USER_GUIDE.md) · [English](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.20.2/docs/en/USER_GUIDE.md)

---

## English

v0.20.2 is a maintenance update focused on calmer Wavelog synchronization, faster logbook handling and stronger protection against duplicate digital QSOs.

### Highlights

- **Delayed automatic synchronization:** In online mode, new QSOs are collected for five minutes by default and then uploaded to Wavelog as a batch. The delay can be configured per profile from 1 to 60 minutes.
- **Fast multi-QSO deletion:** Multiple QSOs can be selected and deleted in one step, with much better performance on large logbooks.
- **Clear warning before Wavelog deletion:** Already synchronized QSOs are clearly identified before deletion. Remote deletion still happens only during the next full synchronization.
- **Improved duplicate protection:** Repeated final exchanges from WSJT-X and external digital logging are much less likely to create duplicate or triplicate QSOs.
- **Duplicates detected during import:** Duplicate records that already exist inside a WSJT-X ADIF file are detected and skipped within the same import.

### Synchronization and safety

The delayed automatic upload sends new local QSOs only. It never performs remote deletions.

When a QSO already linked to Wavelog is deliberately deleted locally, the delete intent is retained and sent to Wavelog only during the next full synchronization. The Logger now displays a clearer warning including the number of affected QSOs.

The local ADIF log remains the authoritative QSO data source.

### Thanks

Many thanks to **DO1DX** for the helpful feedback and practical input that directly contributed to these improvements.

Documentation: [Deutsch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.20.2/docs/USER_GUIDE.md) · [English](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.20.2/docs/en/USER_GUIDE.md)

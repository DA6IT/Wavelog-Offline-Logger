# DA6IT.de Wavelog Offline Logger v0.19.0

## Deutsch

v0.19.0 erweitert die vorhandene CAT- und Wavelog-Anbindung, ohne den bewährten Offline-first-Ablauf zu verändern. Jedes QSO wird weiterhin zuerst lokal gespeichert. Der vollständige Sync behält Downloads, Änderungen, Löschungen, Konflikte und Clubstation-Schutz bei.

Neu und verbessert:

- **FLRig über Netzwerk:** Nach Auswahl des Hamlib-Modells FLRig wird eine frei editierbare Adresse im Format `IP/Hostname:Port` angezeigt. `127.0.0.1:12345` bleibt die lokale Vorgabe.
- **Optionale Erkennung:** Ein bewusster Klick durchsucht zuerst den eigenen Rechner und anschließend begrenzte private IPv4-Netze. Nur ein antwortender FLRig-XML-RPC-Dienst gilt als Treffer. Manuelle Eingabe bleibt immer möglich.
- **Wavelog 3.2.0:** Der bestehende QSO- und Contest-Sync wurde gegen den finalen API-v2-Vertrag geprüft. Der vollständige QSO-Vergleich und die älteren Contest-Fallbacks bleiben erhalten.
- **ClubLog:** Logbuch und Statistik zeigen ClubLog neben QRZ, LoTW, eQSL und DCL. Bestehende Profildatenbanken werden automatisch und verlustfrei erweitert.
- **Stationsbezogene Bestätigungen:** Die Confirmation-API erhält die erlaubten Station-Location-IDs des aktiven Profils und lädt keine unnötigen Statusdaten anderer Stationen.
- **Bessere Fehlerursachen:** API-v2-Fehlercode, Nachricht und strukturierte Details bleiben für die Sync-Anzeige erhalten.

Die komplette deutsche und englische Dokumentation ist enthalten. eQSL bleibt weiterhin als **Coming soon** vorbereitet und führt keinen direkten Upload oder Download aus.

v0.19.0 wird weiterhin bewusst **ohne Windows-Code-Signatur** bereitgestellt, solange die geplante SignPath-Aufnahme noch nicht abgeschlossen ist. Die [Code-Signing-Richtlinie](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.19.0/CODE_SIGNING_POLICY.md) beschreibt den vorgesehenen Prozess.

Dokumentation: [Deutsch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.19.0/docs/USER_GUIDE.md) · [English](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.19.0/docs/en/USER_GUIDE.md)

---

## English

v0.19.0 extends the existing CAT and Wavelog integration without changing the proven offline-first workflow. Every QSO is still written locally first. Full synchronization continues to handle downloads, edits, deletions, conflicts and club-station safeguards.

New and improved:

- **FLRig over the network:** Selecting the Hamlib FLRig model exposes a freely editable `IP/hostname:port` endpoint. `127.0.0.1:12345` remains the local default.
- **Optional discovery:** A deliberate click checks the local computer and then bounded private IPv4 networks. A candidate is accepted only when its FLRig XML-RPC service answers. Manual entry always remains available.
- **Wavelog 3.2.0:** Existing QSO and contest synchronization was verified against the final API v2 contract. Full QSO comparison and older contest fallbacks remain intact.
- **ClubLog:** The logbook and statistics show ClubLog alongside QRZ, LoTW, eQSL and DCL. Existing profile databases are upgraded automatically without losing status values.
- **Station-scoped confirmations:** Confirmation requests include the station-location IDs permitted for the active profile and avoid unrelated status data.
- **Clearer failure reasons:** API v2 error codes, messages and structured details remain available to the synchronization UI.

Complete German and English documentation is included. eQSL remains a **Coming soon** placeholder and performs no direct upload or download.

v0.19.0 remains intentionally **unsigned on Windows** while the planned SignPath onboarding is pending. The [code-signing policy](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.19.0/CODE_SIGNING_POLICY.md) documents the intended process.

Documentation: [Deutsch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.19.0/docs/USER_GUIDE.md) · [English](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.19.0/docs/en/USER_GUIDE.md)

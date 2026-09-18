# Full-Sync: Bestandsaufnahme und Integrationsplan

Stand: Branch `fullsync_improvement`.

## Datenhaltung und sichere Migration

- Das fachliche Primärlogbuch ist die profilbezogene ADI-Datei: `LogStore` in `logger_core.py:898`; Schreibpfade sind `add`, `update`, `delete_many` und `import_adif` (`logger_core.py:1207`, `1216`, `1234`, `1273`). ADIF-Import erstellt ein Backup und verifiziert den geschriebenen Bestand. SQLite ist ausschließlich für Einstellungen, Sync-Metadaten und Caches (`README.md:101-107`).
- `MetadataDB` in `logger_core.py:1331` öffnet `metadata.sqlite` mit WAL und einer eigenen Sperre. `sync_meta` verknüpft `local_id` mit `wavelog_id` und führt Status, lokale/remote Hash-Baselines, Fehler und Zeitstempel (`logger_core.py:1345-1357`).
- Schemaerweiterungen müssen ausschließlich als additive, idempotente `CREATE TABLE IF NOT EXISTS`/`ALTER TABLE`-Schritte in `MetadataDB.__init__` erfolgen. Keine ADI-Datei und kein vorhandenes QSO darf für eine Migration neu geschrieben oder verändert werden. Das vorhandene `clublog`-Upgrade und die Hash-Baseline-Migration v0.10→v0.11 sind Vorbilder (`logger_core.py:1396-1405`, `2874-2883`).
- Bereits vorhandene Schnittstellen für einen resumierbaren Full-Sync sind `sync_state` (Schlüssel: `station_id`, `profile_key`; Phase, Checkpoint, Basis- und QSL-Wasserstand) und `sync_change_journal` (lokale Änderungsfolge) mit `get/set_sync_state`, `journal_change`, `pending_journal_changes`, `consume_journal_changes` (`logger_core.py:1358-1377`, `1424-1472`). Sie werden derzeit nur durch Resilienztests verwendet, nicht durch Mutations- oder Sync-Pfade. Das nächste Paket muss sie nach erfolgreich verarbeitetem lokalen Batch atomar nutzen; Einträge erst danach als konsumiert markieren.

## Wavelog API v2 und Full-Sync

- `WavelogClient` (`logger_core.py:1778`) bildet `/index.php/api/v2` ab: Token, Stationen, QSOs, ADIF-Export, Confirmations und Contest-Ressourcen (`1885-2025`). Requests validieren URL/Token, begrenzen Antworten, paginieren QSOs mit maximal 500 Elementen und brechen bei leeren/wiederholten Folgeseiten ab (`1817-1883`, `1913-1945`).
- `SyncEngine.sync` ist der alleinige vollständige QSO-Abgleich (`logger_core.py:2747-3003`): vollständigen stationsgefilterten Remote-Bestand laden, verknüpfte QSOs abgleichen, ungebundene Remote-QSOs verknüpfen/importieren, danach verbleibende `LOCAL ONLY`-QSOs hochladen und anschließend QSL-Status auffrischen. `push_new_only` ist bewusst ein schmaler Online-Push ohne Pull/Patch/Delete (`2553-2586`).
- Stationsumfang ist `station_profile_id` plus xOTA-Stationen (`2750-2752`). Fehlt bei erhaltenen QSO-Daten die Stations-ID, wird der sichere Import abgebrochen; fremde Stationen werden gezählt und übersprungen (`2778-2787`). `remote_to_local` erhält die Stationsdaten über `_station_for` (`2613-2624`).
- Clubstationen: Ist Stationsrufzeichen ungleich Operator, darf eine Abwesenheit nur bei `club:read` als Löschung gelten. Ohne den Scope bleiben QSOs anderer Operatoren unangetastet (`2753-2768`, `2894-2912`). ADIF-Nachreicherung erhält bei kompakten API-QSOs `OPERATOR` und `STATION_CALLSIGN` (`2626-2667`).
- Konflikte: unverändertes lokales QSO + Remote-Löschung löscht lokal; bei lokaler Änderung wird `conflict/remote_deleted` gespeichert. Gleichzeitige lokale und Remote-Änderung wird `conflict/both_changed`; der Nutzer entscheidet im UI zwischen Wavelog übernehmen und lokal erzwingen (`2914-2936`; `feature_qso_sync.py:1075-1119`). Ein explizites lokales Löschen setzt erst nach erfolgreicher ADI-Löschung `pending_delete`; nur dann wird remote gelöscht (`feature_qso_sync.py:727-742`, `logger_core.py:1547-1583`, `2822-2829`). Ein außerhalb der App verschwundenes ADI-QSO ist dagegen keine implizite Löschung und wird aus Wavelog wiederhergestellt (`1585-1601`, `2854-2865`).

## ADI, QSL und UI

- ADI-Einstiegspunkte der Oberfläche sind Import/Export in `feature_qso_sync.py:549-586`; die Listenansicht zeigt `sync_meta` und `qsl_meta` (`feature_qso_sync.py:168-529`). Beim Löschen informiert die UI explizit über die spätere Remote-Löschung (`685-706`).
- QSL-Status: `_refresh_qsl_statuses` liest gesendete Statuswerte aus dem Wavelog-ADIF-Export und überlagert empfangene Bestätigungen aus `/confirmation`; fehlende optionale Berechtigungen sind nicht fatal (`logger_core.py:2669-2745`). `qsl_meta` cached QRZ, LoTW, eQSL, ClubLog und DCL (`1378-1385`, `1641-1652`).
- Der Wavelog-Online-Monitor und der verzögerte Neuanlagen-Push liegen in `feature_wavelog_online.py:38-221`. Manueller/Start-/Shutdown-Full-Sync wird in `feature_qso_sync.py:949-1074` in einem Worker ausgeführt; `SyncProgressDialog` zeigt Zustands- und Abschlussmeldungen, aber noch keinen Zähler/prozentualen Fortschritt (`918-945`). Für Fortschrittsarbeit: Fortschrittsereignisse vom `SyncEngine` als Callback pro Seite/Phase bereitstellen und ausschließlich über `after()` im Tk-Thread rendern.

## Shutdown, Abbruch und Risiken

- Der Schließenpfad beginnt in `feature_lifecycle.py:16-66`: Eingabequellen werden zuerst gestoppt, laufende Synchronisationen werden abgewartet, optional folgt ein Full-Sync beim Beenden. `shutdown` entfernt Tk-Timer und schließt die DB nur bei nicht laufendem Sync (`68-93`).
- `WavelogClient._request` und die Paging-API unterstützen bereits `cancel_event` und Deadline; Retry-Wartezeiten prüfen beides im 100-ms-Rhythmus (`1792-1805`, `1817-1883`, `1913-1945`). `SyncEngine.sync`, UI-Worker und Shutdown reichen diese Werte aktuell nicht weiter. Ein künftiger Abbruch muss daher ein gemeinsames Event vom Lifecycle bis zu allen API- und Batch-Schleifen propagieren; die DB darf erst geschlossen werden, nachdem der Worker beendet und der letzte bestätigte Checkpoint persistiert ist.
- Full-Sync lädt aktuell vor der Verarbeitung den gesamten Remote-Bestand in den Speicher (`2770-2779`), obwohl der Client seitenweise liefern kann. Große Logs benötigen eine phasenweise/seitige Engine mit persistentem Checkpoint, idempotenter Remote-ID-Zuordnung und sorgfältiger Snapshot-/Watermark-Semantik. Keine Wasserstände vor einem erfolgreich geschriebenen und verifizierten lokalen Batch fortschreiben.
- Das Änderungsjournal hat noch keine Aufrufer. Bei seiner Aktivierung müssen alle lokalen Mutationen (Erstellen, Bearbeiten, explizites Löschen, Import und WSJT-X-Übernahmen) konsistent eingetragen werden; sonst darf es nicht als alleinige Quelle für Remote-Änderungen verwendet werden.

## Windows-Build und Verifikation

- Windows-Einstieg ist `build_pyinstaller_windows.bat`; er ruft `scripts/build-windows.ps1` auf. Der unterstützte Build verlangt Python 3.12.x und Go 1.23.2, führt standardmäßig `selftest.py` aus, baut `bootstrap_windows.go` als Windows-amd64-GUI-EXE, bettet Icon/Versionsdaten ein und schreibt `SHA256SUMS.txt` (`scripts/build-windows.ps1:18-53`, `82-87`, `107-179`).
- Für Folgepakete mindestens fokussierte `unittest`-Tests zu Paging, Migration, Konflikten und Löschungen ergänzen; für eine Release-Änderung unter Windows zusätzlich den PowerShell-Build ohne `-SkipTests` ausführen. Keine Merge Request oder Merge-Aktion ist Bestandteil dieses Branches.

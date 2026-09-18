# Regression-Validierung: Delta-/Full-Sync

Diese Prüfung gilt für den Branch `fullsync_improvement`.

## Reproduzierbare Befehle und Ergebnis

Aus dem Repository-Stamm ausführen:

```text
python -m unittest test_shutdown_delta_sync.py test_wavelog_online_settings.py -v
```

Ergebnis: `Ran 13 tests in 0.002s` und `OK`.

```text
python selftest.py
```

Ergebnis: Exit-Code 0. Die Ausgabe endet ohne Fehler und enthält unter anderem
`SELFTEST OK`, `ONLINE MODE SELFTEST OK`, `MIGRATION SELFTEST OK` und
`QSL METADATA MIGRATION SELFTEST OK`.

```text
git diff --check && python -m compileall -q feature_lifecycle.py feature_qso_sync.py feature_wavelog_online.py feature_settings.py logger_core.py test_shutdown_delta_sync.py selftest.py
```

Ergebnis: Exit-Code 0, keine Ausgabe und keine Whitespace- oder Syntaxfehler.

## Abgedeckte Invarianten

`test_shutdown_delta_sync.py` deckt folgende Regressionen automatisiert ab:

- Beim Abschluss wird ausschließlich `_start_shutdown_delta_sync()` ausgelöst; der Test-Probe schlägt bei einem vorzeitigen finalen Close fehl und protokolliert jeden Full-Sync-Start (`test_shutdown_uses_delta_and_never_starts_full_sync`).
- `SyncEngine.push_new_only()` erhält einen `reconcile_index`-Guard, der bei einem indirekten Integritätscheck fehlschlägt (`test_delta_upload_skips_full_integrity_reconciliation`). Der Delta-Pfad arbeitet nur mit der vorhandenen Kandidatenliste.
- Historische Start- und Abschlusswerte (`full_sync_on_start`, `full_sync_on_exit`) werden in stabiler Reihenfolge in die fehlenden Delta-Schlüssel kopiert. Legacy-Werte bleiben unverändert; bereits explizit gespeicherte Delta-Werte haben Vorrang; ein zweiter Lauf erzeugt keine weiteren Writes (`test_legacy_shutdown_setting_migrates_to_delta_without_overwriting_legacy`, `test_historical_start_and_shutdown_settings_migrate_to_delta_once`, `test_explicit_*_delta_setting_wins_over_legacy_*`).
- Der manuelle Bedienweg ruft weiterhin `_start_sync(automatic=False, reason="manual")` auf. Alle automatischen, Start- oder Abschluss-Entry-Points werden am Full-Sync-Guard abgewiesen (`test_manual_sync_still_starts_full_reconciliation`, `test_full_sync_rejects_automatic_or_shutdown_entrypoints`).
- Ein Cancel während des letzten Delta-Uploads löst `WavelogError` aus. Der Shutdown-Fehlerpfad räumt den Sync-Status auf und ruft `_finalize_close()` auf (`test_cancel_during_final_delta_upload_reaches_shutdown_cancel_path`, `test_cancelled_shutdown_delta_finalizes_close`).

## Gezielte Pfadinspektion

- `feature_lifecycle.py:40-44` startet beim Beenden nur den Shutdown-Delta-Pfad; `feature_lifecycle.py:60` finalisiert erst, wenn kein Abschluss-Sync erforderlich ist.
- `feature_qso_sync.py:919-961` implementiert diesen Delta-Pfad mit `SyncEngine.push_new_only`; `feature_qso_sync.py:1039-1050` weist Full-Sync für alle Gründe außer `manual` ab.
- `logger_core.py:2693-2743` enthält den Delta-Upload. Er ruft weder `_local_map()` noch `reconcile_index()` auf; die Integritätsabstimmung liegt ausschließlich in `logger_core.py:2745-2748`, dem Full-Sync-Helfer.
- Die gefundenen `_start_sync`-Aufrufe liegen ausschließlich in `feature_qso_sync.py:795` und `feature_qso_sync.py:917`; beide übergeben den manuellen Grund. Automatischer Start und Shutdown verwenden `_start_delta_sync` beziehungsweise `_start_shutdown_delta_sync`.

## Verbleibende Einschränkung

Die Tests verwenden Headless-Probes und Fake-Wavelog-Clients. Sie validieren die Windows-Shutdown-Semantik und die Cancellation-Weiterleitung ohne ein echtes Windows-Tk-Fenster oder Netzwerklatenz. Vor einem Windows-Release sollte zusätzlich der dokumentierte Windows-Build inklusive seiner Standardtests ausgeführt werden.

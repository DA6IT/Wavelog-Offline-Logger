# DA6IT.de Wavelog Offline Logger v0.21.1

## Deutsch

v0.21.1 beschleunigt den automatischen Wavelog-Abgleich beim Start und Beenden. Diese Abläufe übertragen nur neue lokale QSOs; der vollständige Abgleich mit Integritätsprüfung bleibt eine bewusste manuelle Aktion.

### Highlights

- **Schneller beim Start und Beenden:** Die optionalen automatischen Abgleiche verwenden einen Delta-Upload neuer lokaler QSOs statt eines vollständigen Abgleichs.
- **Vollständiger Abgleich bleibt verfügbar:** Download, Änderungen, Löschungen, Integritätsprüfung und Konfliktbehandlung bleiben im manuellen vollständigen Sync verfügbar.
- **Sichere Umstellung:** Vorhandene automatische Start-/Beenden-Einstellungen werden in die entsprechenden Delta-Sync-Optionen überführt, ohne eine bereits ausdrücklich gewählte neue Option zu überschreiben.
- **Nachvollziehbarer Ablauf:** Der Delta-Sync zeigt Fortschritt und Ergebnis. Ein abgebrochener vollständiger Sync behält seinen gespeicherten Checkpoint und sein Journal für eine spätere Fortsetzung.
- **Geschützte Zustände:** Sync-Snapshots schützen lokale Änderungen und Konflikte; die QSL-Statusverarbeitung bleibt vom QSO-Sync entkoppelt.

Dokumentation: [Deutsch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.21.1/docs/USER_GUIDE.md) · [English](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.21.1/docs/en/USER_GUIDE.md)

---

## English

v0.21.1 makes automatic Wavelog synchronization at startup and shutdown faster. These operations upload only new local QSOs; complete synchronization with integrity checking remains an intentional manual action.

### Highlights

- **Faster startup and shutdown:** Optional automatic synchronization uses a delta upload of new local QSOs instead of a full reconciliation.
- **Complete synchronization remains available:** Downloads, edits, deletions, integrity checking and conflict handling remain available through manual full synchronization.
- **Safe transition:** Existing automatic startup/shutdown settings are migrated to their matching delta-sync options without overwriting an explicitly selected new option.
- **Visible control:** Delta synchronization shows progress and a result. A cancelled full synchronization retains its persisted checkpoint and journal for later resume.
- **Protected state:** Synchronization snapshots protect local changes and conflicts, while QSL status processing remains separate from QSO synchronization.

Documentation: [Deutsch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.21.1/docs/USER_GUIDE.md) · [English](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.21.1/docs/en/USER_GUIDE.md)

# DA6IT.de Wavelog Offline Logger v0.20.1

## Deutsch

v0.20.1 ist ein Wartungs- und Zuverlässigkeitsupdate rund um QSL-Karten, Synchronisierung und Datensicherung. Die Oberfläche bleibt dabei bewusst kompakt; der Schwerpunkt liegt auf zuverlässigerem Verhalten im Hintergrund.

### Highlights

- **QSL-Vorschau verbessert:** Die Vorschau entspricht jetzt noch zuverlässiger der Karte, die später tatsächlich versendet wird.
- **Änderungen an QSOs werden erkannt:** Bereits bekannte QSOs werden erneut mit dem QSL Card Manager abgeglichen, wenn sich relevante Angaben geändert haben.
- **Besser für große Logbücher:** QSL-Status werden gezielter und in begrenzten Mengen aktualisiert. Dadurch entstehen bei großen Logbüchern deutlich weniger unnötige Abfragen.
- **Aktuellere QSL-Motive:** Geänderte Hintergrundbilder werden auch dann zuverlässig neu geladen, wenn ihre URL gleich geblieben ist.
- **Sichereres Backup/Restore:** Backups werden vor der Wiederherstellung strenger geprüft, damit ungültige oder problematische Dateipfade nicht übernommen werden.
- **Mehr automatische Sicherheitsprüfungen:** Die GitHub-CI prüft Änderungen zusätzlich mit Bandit, `pip-audit` und `detect-secrets`.

### QSL-Synchronisierung

Neue QSOs werden weiterhin automatisch zum QSL Card Manager übertragen. Bereits bekannte QSOs werden nur dann erneut abgeglichen, wenn sich die für den Card Manager relevanten Daten geändert haben.

Nach dem Update werden bestehende Zuordnungen aus älteren Versionen einmalig nachgezogen. Dadurch stehen auch die erweiterten QSO-Angaben aus v0.20.1 im Card Manager zur Verfügung, ohne anschließend bei jedem Hintergrundlauf erneut übertragen zu werden.

Der regelmäßige Statusabgleich wurde außerdem begrenzt: fehlende und noch aktive QSL-Zustände haben Vorrang, während stabile Zustände deutlich seltener erneut geprüft werden.

### Backup und Wiederherstellung

Vor einer Wiederherstellung prüft der Logger das Backup nun strenger. Dazu gehören unter anderem Profilinformationen, die im Backup referenzierten Logdateien und problematische Dateipfade.

Diese Änderungen betreffen ausschließlich die Prüfung und Wiederherstellung. Das normale lokale ADIF-Logging bleibt unverändert.

### Sicherheit

Für die Release-Prüfung wurden die bestehenden Python-, Architektur-, Rotor-, LogStore-, WSJT-X-, QSL- und Backup-Tests ausgeführt. Bandit meldet keine Medium- oder High-Findings; `pip-audit` meldet keine bekannten Vulnerabilities.

Die GitHub-CI führt diese Sicherheitsprüfungen künftig ebenfalls automatisch aus. `detect-secrets` blockiert dort neue verdächtige Secret-Funde gegenüber dem jeweiligen Ausgangsstand.

### Hinweis zum QSL-Versand

Der automatische Hintergrundabgleich versendet weiterhin **niemals selbstständig QSL-Mails**. Der Versand bleibt immer eine ausdrückliche Benutzeraktion.

Dokumentation: [Deutsch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.20.1/docs/USER_GUIDE.md) · [English](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.20.1/docs/en/USER_GUIDE.md)

---

## English

v0.20.1 is a maintenance and reliability update focused on QSL cards, synchronization and backup restore. The application remains intentionally compact while background behavior becomes more reliable.

### Highlights

- **Improved QSL preview:** the preview now more reliably matches the card that is actually sent.
- **QSO changes are detected:** existing QSOs are synchronized with the QSL Card Manager again when relevant details change.
- **Better for large logbooks:** QSL status updates are targeted and bounded, greatly reducing unnecessary requests for large logs.
- **Fresher QSL motifs:** changed background images are reloaded reliably even when their URL stays the same.
- **Safer backup and restore:** backups are validated more strictly before restore so invalid or problematic paths are rejected.
- **More automated security checks:** GitHub CI now additionally runs Bandit, `pip-audit` and `detect-secrets`.

### QSL synchronization

New QSOs continue to be synchronized automatically with the QSL Card Manager. Existing QSOs are synchronized again only when data relevant to the Card Manager has changed.

After updating, mappings created by older versions are backfilled once. This makes the additional QSO information introduced in v0.20.1 available to the Card Manager without resending unchanged QSOs on every background run.

Periodic status refresh is also bounded: missing and active QSL states are prioritized while stable states are checked much less frequently.

### Backup and restore

Before restoring, the Logger now validates the backup more strictly, including profile information, referenced log files and problematic file paths.

These changes affect validation and restore only. Normal local ADIF logging remains unchanged.

### Security

Release validation included the existing Python, architecture, rotor, LogStore, WSJT-X, QSL and backup tests. Bandit reports no Medium or High findings and `pip-audit` reports no known vulnerabilities.

GitHub CI now runs these security checks automatically as well. `detect-secrets` blocks new suspicious secret findings relative to the relevant base revision.

### QSL delivery note

Automatic background synchronization still **never sends QSL email on its own**. Sending always remains an explicit user action.

Documentation: [Deutsch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.20.1/docs/USER_GUIDE.md) · [English](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.20.1/docs/en/USER_GUIDE.md)

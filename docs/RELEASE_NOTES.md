# DA6IT.de Wavelog Offline Logger v0.19.2

## Deutsch

v0.19.2 behebt den automatischen Windows-Updater. Der Logger ersetzt und startet nach einem Update jetzt zuverlässig genau die EXE, die ursprünglich gestartet wurde – unabhängig von Dateiname und Speicherort.

Behoben und verbessert:

- **Zuverlässige Update-Übergabe:** Die Desktop-App lädt und prüft das Update, beendet sich anschließend sauber und übergibt die Installation an den Windows-Launcher.
- **Kein Abbruch durch den internen Job Object:** Der PowerShell-Updateprozess wird erst nach dem Ende der Desktop-App gestartet und kann dadurch nicht mehr zusammen mit dem Python-Prozess beendet werden.
- **Beliebiger EXE-Name und Speicherort:** Aktualisiert wird weiterhin exakt die vom Benutzer gestartete Programmdatei. Es gibt keinen fest codierten Dateinamen und keinen fest vorgegebenen Installationsordner.
- **Windows PowerShell 5.1:** Der Update-Helper verwendet ausschließlich mit Windows PowerShell 5.1 kompatible Pfad- und Prozessoperationen.
- **Integritätsprüfung:** Das bereits verifizierte Downloadpaket wird beim Staging und nach dem Austausch erneut per SHA-256 geprüft.
- **Rollback:** Schlägt Austausch oder Neustart fehl, wird die vorherige EXE wiederhergestellt.
- **Update-Log:** Der Ablauf wird unter `%LOCALAPPDATA%\AFU-Tools\WavelogOfflineLogger\updates\update.log` protokolliert.

### Wichtig für Benutzer von v0.19.1

Da genau der automatische Updater in v0.19.1 fehlerhaft ist, kann der Sprung von **v0.19.1 auf v0.19.2 einmalig eine manuelle Installation erfordern**. Lade v0.19.2 in diesem Fall direkt aus dem GitHub-Release herunter und starte bzw. ersetze deine bisherige EXE damit. Ab v0.19.2 ist der reparierte Update-Ablauf enthalten.

Profile, Einstellungen, ADI-Logbücher und Wavelog-Synchronisationsdaten werden durch dieses Update nicht verändert.

v0.19.2 wird weiterhin bewusst **ohne Windows-Code-Signatur** bereitgestellt, solange die geplante SignPath-Aufnahme noch nicht abgeschlossen ist. Die [Code-Signing-Richtlinie](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.19.2/CODE_SIGNING_POLICY.md) beschreibt den vorgesehenen Prozess.

Dokumentation: [Deutsch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.19.2/docs/USER_GUIDE.md) · [English](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.19.2/docs/en/USER_GUIDE.md)

---

## English

v0.19.2 fixes the automatic Windows updater. After an update, the logger now reliably replaces and restarts the exact EXE that was originally launched, regardless of its filename or location.

Fixed and improved:

- **Reliable update hand-off:** The desktop app downloads and verifies the update, exits cleanly, and hands installation over to the Windows launcher.
- **No termination by the internal Job Object:** The PowerShell updater is started only after the desktop app has exited, so it is no longer terminated together with the Python process.
- **Arbitrary EXE filename and location:** The updater still replaces exactly the program file launched by the user. No product filename or installation directory is hard-coded.
- **Windows PowerShell 5.1:** The helper uses path and process operations compatible with Windows PowerShell 5.1.
- **Integrity verification:** The already verified download package is checked again with SHA-256 after staging and after replacement.
- **Rollback:** If replacement or restart fails, the previous EXE is restored.
- **Update log:** The process is logged under `%LOCALAPPDATA%\AFU-Tools\WavelogOfflineLogger\updates\update.log`.

### Important for users of v0.19.1

Because the automatic updater itself is broken in v0.19.1, moving from **v0.19.1 to v0.19.2 may require one manual installation**. In that case, download v0.19.2 directly from the GitHub release and start or replace your existing EXE with it. From v0.19.2 onward, the repaired update flow is included.

Profiles, settings, ADI logbooks and Wavelog synchronization data are not changed by this update.

v0.19.2 remains intentionally **unsigned on Windows** while the planned SignPath onboarding is pending. The [code-signing policy](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.19.2/CODE_SIGNING_POLICY.md) documents the intended process.

Documentation: [Deutsch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.19.2/docs/USER_GUIDE.md) · [English](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.19.2/docs/en/USER_GUIDE.md)

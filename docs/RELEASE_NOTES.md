# DA6IT.de Wavelog Offline Logger v0.19.1

## Deutsch

v0.19.1 verbessert CAT/TUNE, den Dark Mode und die Pflege der mitgelieferten Hamlib-Laufzeit. Der bewährte Offline-first-Ablauf und die vorhandene Wavelog-Synchronisierung bleiben unverändert: QSOs werden weiterhin zuerst lokal gespeichert.

Neu und verbessert:

- **Dark Mode:** Eingabefelder, Comboboxen samt Auswahllisten, Tabellen, Register, Listen und deaktivierte Bedienelemente besitzen nun in allen Hauptfenstern einen konsistenten Kontrast.
- **TUNE / FTX-1:** Der TUNE-Knopf kann eine gespeicherte CAT-Verbindung bei Bedarf selbst starten. Beim FTX-1 wird die am Funkgerät ausgewählte Tunerart abgefragt und mit dem passenden Yaesu-CAT-Befehl gestartet.
- **Saubere CAT-Kommandos:** Abfragen, Frequenz-/Mode-Änderungen und TUNE werden innerhalb einer Verbindung geordnet ausgeführt, damit paralleles Polling den Tunerbefehl nicht stört.
- **Hamlib selbst aktualisieren:** Unter Windows kann der Benutzer im CAT Setup bewusst nach einer stabilen Hamlib-Version suchen und das offizielle x64-ZIP installieren.
- **Geprüfte Installation:** Downloadquelle und GitHub-SHA-256 werden geprüft. Anschließend muss die neue `rigctld.exe` einen lokalen Funktionstest bestehen, bevor sie aktiv wird.
- **Rückfall möglich:** Die zuvor verwendete Hamlib-Version bleibt gesichert und kann im CAT Setup wiederhergestellt werden. Profile, CAT-Einstellungen und QSOs werden nicht verändert.
- **Linux und macOS:** Hamlib bleibt Bestandteil der plattformspezifisch gebauten Anwendungspakete und wird dort mit einem normalen App-Update erneuert.

Die vollständige deutsche und englische Dokumentation ist enthalten. eQSL bleibt weiterhin als **Coming soon** vorbereitet und führt keinen direkten Upload oder Download aus.

v0.19.1 wird weiterhin bewusst **ohne Windows-Code-Signatur** bereitgestellt, solange die geplante SignPath-Aufnahme noch nicht abgeschlossen ist. Die [Code-Signing-Richtlinie](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.19.1/CODE_SIGNING_POLICY.md) beschreibt den vorgesehenen Prozess.

Dokumentation: [Deutsch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.19.1/docs/USER_GUIDE.md) · [English](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.19.1/docs/en/USER_GUIDE.md)

---

## English

v0.19.1 improves CAT/TUNE, dark-mode presentation and maintenance of the bundled Hamlib runtime. The established offline-first workflow and existing Wavelog synchronization remain unchanged: QSOs are still stored locally first.

New and improved:

- **Dark mode:** Entries, combo boxes and their drop-down lists, tables, tabs, lists and disabled controls now have consistent contrast throughout the main windows.
- **TUNE / FTX-1:** The TUNE button can start the saved CAT connection when required. On the FTX-1, the app reads the tuner type selected on the radio and sends the matching Yaesu CAT command.
- **Ordered CAT commands:** Polling, frequency/mode changes and TUNE are serialized so that background polling cannot interfere with the tuner command.
- **User-triggered Hamlib updates:** On Windows, users can deliberately check for a stable Hamlib release in CAT Setup and install the official x64 ZIP package.
- **Verified installation:** The download source and GitHub SHA-256 digest are checked. The new `rigctld.exe` must then pass a local runtime test before activation.
- **Rollback:** The previously used Hamlib runtime is retained and can be restored from CAT Setup. Profiles, CAT settings and QSOs are not changed.
- **Linux and macOS:** Hamlib remains part of the platform-specific application packages and is updated with the regular app package.

Complete German and English documentation is included. eQSL remains a **Coming soon** placeholder and performs no direct upload or download.

v0.19.1 remains intentionally **unsigned on Windows** while the planned SignPath onboarding is pending. The [code-signing policy](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.19.1/CODE_SIGNING_POLICY.md) documents the intended process.

Documentation: [Deutsch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.19.1/docs/USER_GUIDE.md) · [English](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.19.1/docs/en/USER_GUIDE.md)

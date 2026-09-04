# DA6IT.de Wavelog Offline Logger v0.19.1

Version 0.19.1 improves CAT/TUNE, dark-mode presentation and maintenance of the bundled Hamlib runtime while preserving the offline-first workflow and existing Wavelog synchronization.

Highlights:

- Entries, combo boxes and their drop-down lists, tables, tabs, lists and disabled controls now have consistent dark-mode contrast.
- TUNE can start the saved CAT connection when required.
- On the FTX-1, the selected tuner type is read from the radio and started with the matching Yaesu CAT command.
- CAT polling and user commands are serialized so that they cannot interfere with each other.
- Windows users can manually check for and install stable Hamlib updates from CAT Setup.
- Official Windows x64 archives are accepted only after source and SHA-256 verification and a successful local `rigctld.exe` runtime test.
- The previously used Hamlib runtime remains available for rollback.
- Linux and macOS continue to receive Hamlib through their platform-specific application packages.

Profiles, CAT settings and QSOs are never changed by a Hamlib update or rollback. Complete German and English documentation is included. The Windows package remains intentionally unsigned while SignPath onboarding is pending, and the application collects no telemetry or usage counts.

# Mitwirken

**Deutsch** · [English](CONTRIBUTING.en.md)

Danke für dein Interesse am DA6IT.de Wavelog Offline Logger.

## Grundregeln

- Niemals echte Wavelog-Tokens, Stationsdaten oder persönliche Logdateien committen.
- ADI-Dateien bleiben das primäre lokale Logbuch. SQLite darf keine zweite Wahrheit für QSO-Daten werden.
- Remote-Löschungen dürfen nur aus einer ausdrücklichen Benutzeraktion entstehen.
- Konflikte dürfen nicht automatisch zugunsten einer Seite aufgelöst werden.
- Bestehende Profil-, Metadata- und Token-Migrationen müssen kompatibel bleiben.
- Änderungen sollten klein, nachvollziehbar und mit einem Regressionstest versehen sein.

## Entwicklungsablauf

1. Einen eigenen Branch erstellen.
2. Änderung implementieren und relevante Dokumentation aktualisieren.
3. Selftests ausführen:

   ```powershell
   python selftest.py
   ```

4. Für Bootstrapper- oder Releaseänderungen zusätzlich bauen:

   ```powershell
   .\scripts\build-windows.ps1
   ```

5. Einen Pull Request mit Problem, Lösung, Tests und möglichen Datenmigrationsfolgen eröffnen.

## Pull-Request-Checkliste

- [ ] Keine Zugangsdaten oder echten Logdaten enthalten
- [ ] `python selftest.py` erfolgreich
- [ ] Datenverlust- und Löschfolgen geprüft
- [ ] README/CHANGELOG bei sichtbaren Änderungen aktualisiert
- [ ] Versionsnummer nur für einen geplanten Release geändert

Mit dem Einreichen eines Beitrags erklärst du dich damit einverstanden, ihn unter der MIT-Lizenz dieses Projekts bereitzustellen.

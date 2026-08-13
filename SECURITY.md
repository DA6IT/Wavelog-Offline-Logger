# Sicherheitsrichtlinie

## Unterstützte Versionen

Sicherheitskorrekturen werden für die jeweils neueste veröffentlichte Version beziehungsweise den aktuellen Release Candidate vorbereitet.

## Sicherheitsproblem melden

Bitte Schwachstellen, mögliche Token-Offenlegungen oder Wege zu unbeabsichtigten Remote-Löschungen nicht als öffentliches Issue melden.

Nach Veröffentlichung des Repositorys bitte unter **Security → Advisories → Report a vulnerability** einen privaten Security Advisory öffnen. Falls diese Funktion noch nicht aktiviert ist, den Projektbetreiber über den auf dem GitHub-Profil angegebenen privaten Kontaktweg erreichen.

Bitte nach Möglichkeit angeben:

- betroffene Version und Windows-Version
- reproduzierbare Schritte ohne echte Zugangsdaten
- erwartetes und beobachtetes Verhalten
- mögliche Auswirkungen auf lokale ADI-Dateien oder Wavelog

## Umgang mit Zugangsdaten

- Wavelog-API-Tokens gehören niemals in Issues, Screenshots, Logs oder Commits.
- Unter Windows werden neu gespeicherte Tokens mit DPAPI an das Benutzerkonto gebunden.
- Historische `plain:`-Einträge bleiben nur für eine kontrollierte Migration lesbar.
- Release-Artefakte werden mit SHA-256-Prüfsummen veröffentlicht.

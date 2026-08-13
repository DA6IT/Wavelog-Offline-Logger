# GitHub-Einstellungen für Maintainer

Das öffentliche Repository liegt unter [DA6IT/Wavelog-Offline-Logger](https://github.com/DA6IT/Wavelog-Offline-Logger). Der Standardbranch ist `main`.

## Empfohlene Repository-Einstellungen

- Issues aktivieren
- Private Vulnerability Reporting unter **Settings → Security** aktivieren
- GitHub Actions zulassen
- Standardbranch `main` beibehalten
- Branchschutz für `main` einrichten

## Schutz für `main`

Empfohlene Regeln:

- Pull Request vor Merge verlangen
- erfolgreichen CI-Workflow verlangen
- Force-Push und Branchlöschung sperren
- für den Anfang eine Freigabe ausreichend

## Änderungen veröffentlichen

Neue Änderungen sollen auf einem eigenen Branch vorbereitet und über einen Pull Request nach `main` übernommen werden.

```powershell
git switch -c feature/kurze-beschreibung
git add <Dateien>
git commit -m "Kurze Beschreibung"
git push -u origin feature/kurze-beschreibung
```

Vor jedem Push mit `git status` kontrollieren, dass weder `dist\`, EXE-Dateien, ADI-Logs, `AGENTS.md` noch lokale Datenbanken enthalten sind.

## Release Candidate veröffentlichen

Erst nach einem lokalen Test des erzeugten RC-Builds:

```powershell
git tag -a v0.11.2-rc1 -m "DA6IT.de Wavelog Offline Logger v0.11.2-rc1"
git push origin v0.11.2-rc1
```

Der Release-Workflow baut und testet erneut. Der Bindestrich in der Version kennzeichnet das GitHub-Release automatisch als Vorabversion.

## Stabile Version

Nach erfolgreichem Praxistest die in `RELEASING.md` genannten Versionsstellen auf `0.11.2` ändern, erneut testen, committen und den Tag `v0.11.2` pushen.

## Noch nicht automatisiert

- Windows-Code-Signierung
- macOS Intel und Apple Silicon
- Apple-Signierung und Notarisierung

Diese Punkte dürfen den kostenlosen, unsignierten Windows-Release zunächst nicht blockieren, müssen aber in den Release Notes transparent genannt werden.

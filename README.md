# DA6IT.de Wavelog Offline Logger

Ein Offline-first Desktop-Logger für Funkamateure: unterwegs loggen, auch wenn Wavelog oder das Internet nicht erreichbar ist. Jedes QSO wird zuerst sicher lokal als ADI gespeichert und später manuell oder automatisch mit Wavelog synchronisiert.

**Download:** [Aktuelles Release für Windows, macOS und Linux](https://github.com/DA6IT/Wavelog-Offline-Logger/releases/latest)

![QSO-Logging mit Callbook-Seitenleiste](docs/screenshots/qso-logging.png)

## Highlights

- normales QSO-Logging, Fast Log/DXpedition und Contest-Logging
- tägliche ADI-Dateien als primäres lokales Logbuch
- mehrere getrennte Stationsprofile
- bidirektionaler Wavelog-API-v2-Sync mit sichtbaren Konflikten
- optionaler Online-Modus: nur neue QSOs sofort pushen
- optionaler Voll-Sync beim App-Start und/oder Beenden
- Callbook-Daten über Wavelog oder QRZ.com, einschließlich Stationsfoto
- CAT über mitgeliefertes Hamlib, inklusive TUNE/ATU
- Telnet-DX-Cluster, Filter, Worked-Markierung und Spotversand
- WSJT-X- und ADIF-Empfang über UDP
- deutsche und englische Oberfläche, Light- und Dark-Theme
- Builds für Windows x64, macOS Apple Silicon/Intel und Linux x64/ARM64

## Installation

| System | Release-Datei | Hinweis |
|---|---|---|
| Windows x64 | `*-windows-x64.exe` | private Python-Laufzeit; Hamlib enthalten |
| macOS Apple Silicon | `*-macos-arm64.zip` | `.app` nach Programme verschieben |
| macOS Intel | `*-macos-x64.zip` | beim ersten Start Rechtsklick → Öffnen |
| Debian/Ubuntu | `*.deb` | `sudo apt install ./DATEI.deb` |
| Linux allgemein | `*.AppImage` | ausführbar machen und starten |
| Arch Linux | `*.pkg.tar.zst` | `sudo pacman -U DATEI.pkg.tar.zst` |

Beim ersten Windows-Start lädt der Bootstrapper einmalig eine verifizierte private Python-Laufzeit. Python muss nicht systemweit installiert sein. Für CAT kann zusätzlich der Windows-Treiber des Funkgeräts erforderlich sein.

## Schnelleinstieg

1. Unter **Einstellungen → Station & Wavelog** Rufzeichen, Operator und optional Wavelog eintragen.
2. Im **Logbuch** ein Rufzeichen und die QSO-Daten erfassen.
3. QSO speichern – es ist sofort lokal in der ADI-Datei vorhanden.
4. Später **Synchronisieren** anklicken oder den profilbezogenen Online-Modus aktivieren.

Der Logger ersetzt Wavelog nicht. Er ergänzt es für portable Einsätze, DXpeditionen, Pileups, Conteste und Fielddays.

## Daten und Sicherheit

- ADI ist das primäre QSO-Logbuch; SQLite enthält Einstellungen und Sync-Metadaten.
- Ohne Internet bleibt die App still im Modus `LOCAL ONLY`.
- Ein Laufzeit-Push überträgt ausschließlich neue, unverknüpfte QSOs.
- Änderungen, Downloads, Löschungen und Konflikte behandelt nur der vollständige Sync.
- Profil-Löschung wirkt ausschließlich lokal und löscht keine Wavelog-Daten.
- eQSL-Felder sind vorbereitet, aber weiterhin **Coming soon** und noch ohne Verbindung.

## Dokumentation

- [Ausführliches Benutzerhandbuch](docs/USER_GUIDE.md)
- [Vollständige Screenshot-Galerie](docs/SCREENSHOTS.md)
- [Fehlerhilfe](docs/TROUBLESHOOTING.md)
- [Release-Hinweise](docs/RELEASE_NOTES.md)
- [Architektur](docs/ARCHITECTURE.md)
- [Mitwirken](CONTRIBUTING.md)

## Entwicklung und Builds

```powershell
python selftest.py
.\scripts\package-release.ps1
```

Linux wird mit `bash ./scripts/build-linux.sh dist`, macOS mit `./scripts/build-macos.sh dist` gebaut. Die offiziellen Binärpakete entstehen reproduzierbar in GitHub Actions.

## Lizenz

[MIT](LICENSE) · unabhängiges Community-Projekt, kein Bestandteil des Wavelog-Projekts.

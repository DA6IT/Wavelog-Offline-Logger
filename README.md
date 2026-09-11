# DA6IT.de Wavelog Offline Logger

**Deutsch** · [English](README.en.md)

Ein Offline-first Desktop-Logger für Funkamateure: unterwegs loggen, auch wenn Wavelog oder das Internet nicht erreichbar ist. Jedes QSO wird zuerst sicher lokal als ADI gespeichert und später manuell oder automatisch mit Wavelog synchronisiert.

**Download:** [Aktuelles Release für Windows, macOS und Linux](https://github.com/DA6IT/Wavelog-Offline-Logger/releases/latest)

![QSO-Logging mit Callbook-Seitenleiste](docs/screenshots/qso-logging.png)

## Highlights

- normales QSO-Logging, Fast Log/DXpedition und Contest-Logging mit Wavelog-Session-Abgleich
- FLRig-CAT über frei editierbare Netzwerkadresse mit optionaler lokaler Erkennung
- stationsbezogener Wavelog-3.2.0-Abgleich mit ClubLog-Status
- eine fortlaufende ADI-Datei je Profil als primäres lokales Logbuch
- geprüfter ADIF-Import und -Export mit Backup und Dublettenschutz
- integrierter xOTA-Modus für kombinierte POTA-, SOTA-, WWFF-, IOTA- und COTA/WCA-Aktivierungen
- mehrere getrennte Stationsprofile
- profilspezifischer Wavelog-API-v2-Sync mit sichtbaren Konflikten und Fehlerursachen
- optionaler Online-Modus: nur neue QSOs nach konfigurierbarer Verzögerung pushen; Standard sind fünf Minuten
- optionaler Voll-Sync beim App-Start und/oder Beenden
- bidirektionaler Abgleich von Wavelog-Contest-Sessions und deren QSO-Zuordnungen; Session-IDs werden automatisch übernommen
- Callbook-Daten über Wavelog oder direkt über QRZ.com, einschließlich Stationsfoto
- QRZ.com-Seiten direkt aus dem QSO-Formular und aus ausgewählten DX-Cluster-Spots öffnen
- integrierter DA6IT.de QSL Card Manager mit lokalem eQSL-Abgleich für E-Mail-QSL-Empfehlungen
- optionale Desktop-Benachrichtigung nach einem lokal gespeicherten QSO
- CAT über mitgeliefertes Hamlib, inklusive TUNE/ATU und manuellem Windows-Hamlib-Updater mit Rückfallversion
- Rotorsteuerung über Hamlib `rotctld` mit Live-Position, Kompass, Peilungsübernahme, STOP und Dummy-Test ohne Hardware
- Telnet-DX-Cluster, Filter, Worked-Markierung und Spotversand
- bidirektionaler WSJT-X-Dateisync über `wsjtx_log.adi` mit Backup, Dublettenschutz und optionalem Abgleich bei Start/Beenden
- WSJT-X-Live-Status und geloggte QSOs weiterhin zusätzlich über UDP
- deutsche und englische Oberfläche, Light- und Dark-Theme
- verifizierter In-App-Updater; unter Windows wird die bestätigte neue Version automatisch installiert
- vollständiges ZIP-Backup und Restore von Profilen, Einstellungen, ADI-Logbüchern und Metadaten
- einmalige „Was ist neu?“-Übersicht nach dem ersten Start einer neuen Version
- responsive Oberfläche mit gezieltem Scrollen bei langen Geräteeinstellungen; Felder, Aktionen und Abstände passen sich gemeinsam an und werden vor jedem Release in mehreren Fenstergrößen geprüft
- Builds für Windows x64, macOS Apple Silicon/Intel und Linux x64/ARM64

## WSJT-X Sync

Neben dem bestehenden UDP-Live-Logging kann der Logger jetzt die von WSJT-X verwendete `wsjtx_log.adi` direkt abgleichen. Der Offline Logger ist dabei der lokale Merge-Hub:

```text
Wavelog  → Offline Logger ← WSJT-X
Wavelog  ← Offline Logger → WSJT-X
```

Der Abgleich ergänzt fehlende QSOs, führt aber keine automatischen Löschungen durch. Vor Änderungen an der WSJT-X-Datei wird eine Sicherung angelegt. Standardinstallationen und mit `--rig-name` getrennte WSJT-X-Profile werden erkannt; alternativ kann der Pfad manuell gewählt werden. Start-, Beenden- und manueller Sync sind pro Logger-Profil getrennt konfigurierbar.
## xOTA und ADIF

![xOTA-Aktivierung mit Mehrfachreferenzen](docs/screenshots/xota.png)

Der integrierte **xOTA-Modus** kombiniert mehrere Aktivierungsprogramme in einer portablen Session. GPS und die Maidenhead-Berechnung funktionieren offline; Online-Dienste ergänzen lediglich Standort- und mögliche Referenzdaten. Für POTA wird der vollständige offizielle Parkkatalog lokal gespeichert. Die Suche zeigt nahe Katalogmarker bis 10 km und zusätzlich deutlich markierte Kandidaten bis 25 km, damit große oder grenzüberschreitende Parks nicht durch einen weit entfernten Mittelpunkt übersehen werden. Da die Katalogkoordinate keine exakte Parkgrenze ist, lässt sich ein ausgewählter Treffer direkt auf **pota-map.info** kontrollieren. Einen vorgeschlagenen Treffer muss der Benutzer stets selbst prüfen und übernehmen.

QSOs werden weiterhin zuerst lokal gespeichert. Eine Aktivierung kann später einer vorhandenen Wavelog Station Location zugeordnet oder – erst nach ausdrücklicher Bestätigung – als neue Location angelegt werden. ADIF-Import und -Export befinden sich unter **Logbuch & Sync**.

Beim ersten Start werden vorhandene Tages-ADI-Dateien vor der Zusammenführung als ZIP gesichert. Die neue Profil-Datei wird gelesen und verifiziert; erst danach werden die alten Dateien in ein Wiederherstellungsverzeichnis verschoben.

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

## Deinstallation

Programm und Benutzerdaten werden bewusst getrennt entfernt:

- **Windows:** App schließen und die heruntergeladene EXE beziehungsweise den entpackten Programmordner und eigene Verknüpfungen löschen. Optional anschließend `%LOCALAPPDATA%\AFU-Tools\WavelogOfflineLogger\` entfernen. Dieser Ordner enthält die private Python-Laufzeit, Profile, Einstellungen, Tokens, Caches und Sync-Metadaten.
- **macOS:** App schließen und **DA6IT.de Wavelog Offline Logger.app** aus **Programme** in den Papierkorb verschieben. Optional `~/Library/Application Support/AFU-Tools/WavelogOfflineLogger/` löschen.
- **Debian/Ubuntu:** `sudo apt remove wavelog-offline-logger`; optional danach `~/.local/share/AFU-Tools/WavelogOfflineLogger/` löschen.
- **Arch Linux:** `sudo pacman -R wavelog-offline-logger`; optional danach denselben lokalen Datenordner löschen.
- **AppImage:** App schließen und die AppImage-Datei löschen; optional den genannten Linux-Datenordner entfernen.

**Wichtig:** Die ADI-Logbücher liegen standardmäßig getrennt unter `Dokumente/DA6IT.de Wavelog Logger/Profiles/…/Logs` oder an einem selbst gewählten Speicherort. Sie werden durch die obigen Schritte nicht automatisch gelöscht. Vor dem Entfernen von Benutzerdaten empfiehlt sich **Einstellungen → Daten & Verbindungen → Backup erstellen**.

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
- Direkter eQSL-Upload/-Sync mit persönlichen eQSL-Zugangsdaten bleibt **Coming soon**. Für QSL-Empfehlungen wird unabhängig davon die eQSL-Mitgliederliste lokal gecacht und ausgewertet.
- Eine datensparsame pseudonyme Nutzungsstatistik kann nach dem Erststart-Hinweis höchstens einmal täglich eine zufällige Installations-ID, Version und Betriebssystemfamilie melden. Sie kann abgeschaltet und die zugehörigen Statistikdaten können in der App gelöscht werden; Rufzeichen und QSO-Daten werden nicht übertragen.
- [Datenschutzerklärung](PRIVACY.md) und [Sicherheitsmeldungen](SECURITY.md) beschreiben lokale Daten und optionale Netzwerkdienste im Detail.

## Code signing policy

**[Free code signing provided by SignPath.io, certificate by SignPath Foundation](CODE_SIGNING_POLICY.md)**

Die Aufnahme bei SignPath ist vorbereitet, aber noch nicht abgeschlossen. v0.19.1 bleibt deshalb transparent als unsigniert gekennzeichnet. Nach der Freigabe werden künftige Windows-Pakete im kontrollierten CI-Prozess signiert.

## Dokumentation

- [Ausführliches Benutzerhandbuch](docs/USER_GUIDE.md)
- [Vollständige Screenshot-Galerie](docs/SCREENSHOTS.md)
- [Fehlerhilfe](docs/TROUBLESHOOTING.md)
- [Release-Hinweise](docs/RELEASE_NOTES.md)
- [Architektur](docs/ARCHITECTURE.md)
- [Mitwirken](CONTRIBUTING.md)
- [Datenschutzerklärung](PRIVACY.md)
- [Code-Signing-Richtlinie](CODE_SIGNING_POLICY.md)
- [Sicherheitsrichtlinie](SECURITY.md)

## Projekt unterstützen

Wenn dir der Logger hilft, kannst du die Weiterentwicklung freiwillig unterstützen:
[☕ Buy Me a Coffee](https://buymeacoffee.com/da6it?new=1) · [PayPal](https://paypal.me/DA6IT)

## Entwicklung und Builds

```powershell
python selftest.py
.\scripts\package-release.ps1
```

Linux wird mit `bash ./scripts/build-linux.sh dist`, macOS mit `./scripts/build-macos.sh dist` gebaut. Die offiziellen Binärpakete entstehen reproduzierbar in GitHub Actions.

## Lizenz

[MIT](LICENSE) · unabhängiges Community-Projekt, kein Bestandteil des Wavelog-Projekts.

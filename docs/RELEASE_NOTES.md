# DA6IT.de Wavelog Offline Logger v0.19.4

## Deutsch

v0.19.4 ergänzt eine lokal gesteuerte Rotoranbindung über Hamlib und stärkt zugleich die Sicherheitsgrenzen bei Netzwerk- und XML-Verarbeitung.

### Highlights

- **Rotorsteuerung über Hamlib:** `rotctld` wird gemeinsam mit `rigctld` ausgeliefert. Modell, Schnittstelle, Baudrate und lokaler Port werden im CAT Setup konfiguriert.
- **Peilung direkt nutzen:** Sobald eigener und fremder Locator bekannt sind, steht die berechnete Peilung als Rotorziel bereit. Erst **Rotor drehen** setzt die Bewegung in Gang; ein Lookup allein bewegt niemals Hardware.
- **Live-Kompass und STOP:** Das QSO-Log zeigt die aktuelle Rotorposition und das Ziel kompakt an. **STOP** ist während der Verbindung direkt erreichbar.
- **Ohne Hardware testbar:** Hamlib Dummy [ID 1] simuliert Bewegung und Position und ermöglicht einen vollständigen Funktionstest ohne angeschlossenen Rotor.
- **Platzsparendere Oberfläche:** CAT Setup kann auf kleinen Fenstern vertikal per Scrollbar, Mausrad oder Trackpad bedient werden. Das Callbook-Foto belegt weniger vertikalen Platz.
- **Gehärtete Verarbeitung:** QRZ-/FLRig-XML-Antworten werden begrenzt und vor dem Parsen geprüft; HTTPS-Redirects dürfen nicht auf unverschlüsseltes HTTP herabstufen und sensible Header werden nicht an fremde Origins weitergereicht.

### Sicherheit und Verhalten

`rotctld` lauscht ausschließlich lokal auf `127.0.0.1`. Die Rotorbewegung erfordert immer eine ausdrückliche Benutzeraktion. Bei Az/El-Rotoren bleibt die zuletzt gelesene Elevation beim Anfahren einer neuen Peilung erhalten.

ADI bleibt die maßgebliche lokale QSO-Quelle. Das Update ändert weder die bestehenden Regeln für Wavelog-/WSJT-X-Synchronisierung noch führt es automatische Remote-Löschungen ein.

Dokumentation: [Deutsch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.19.4/docs/USER_GUIDE.md) · [English](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.19.4/docs/en/USER_GUIDE.md)

---

## English

v0.19.4 adds local Hamlib rotor control while strengthening network and XML handling boundaries.

### Highlights

- **Hamlib rotor control:** `rotctld` ships alongside `rigctld`. Model, interface, baud rate and local port are configured from CAT Setup.
- **Use the calculated bearing:** when both station grids are known, the bearing becomes the rotor target. Hardware moves only after **Turn rotor** is selected; lookup alone never moves the antenna.
- **Live compass and STOP:** the QSO form displays current rotor position and target in a compact control with immediate **STOP** access.
- **Hardware-free testing:** Hamlib Dummy [ID 1] simulates movement and position for a complete software test without a physical rotor.
- **More compact UI:** CAT Setup can be scrolled vertically by scrollbar, mouse wheel or trackpad on small windows, and the callbook photo uses less vertical space.
- **Hardened handling:** QRZ/FLRig XML responses are bounded and validated before parsing; HTTPS redirects cannot downgrade to plain HTTP and sensitive headers are not forwarded to another origin.

### Safety and behavior

`rotctld` listens on `127.0.0.1` only. Rotor movement always requires an explicit user action. On Az/El rotors the last known elevation is preserved when a new bearing is sent.

ADI remains the authoritative local QSO source. This update does not change the established Wavelog/WSJT-X synchronization rules and introduces no automatic remote deletions.

Documentation: [Deutsch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.19.4/docs/USER_GUIDE.md) · [English](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.19.4/docs/en/USER_GUIDE.md)

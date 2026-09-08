# DA6IT.de Wavelog Offline Logger v0.20.0

## Deutsch

v0.20.0 bringt den DA6IT.de QSL Card Manager direkt in den Offline Logger. Die Integration bleibt dem Offline-First-Prinzip treu: QSOs werden weiterhin lokal in ADIF geführt, während QSL-Motive, Empfängerprüfung, Kartenversand und Status bei vorhandener Internetverbindung im Hintergrund mit DA6IT.de zusammenarbeiten.

### Highlights

- **QSL direkt aus dem Logbuch:** Ein oder mehrere QSOs können ausgewählt und als QSL-Mail versendet werden. Einzelversand läuft direkt, Mehrfachauswahl wird über die serverseitige Queue verarbeitet.
- **Kein manueller QSL-Sync mehr nötig:** Neue QSOs erhalten automatisch ihre `qsoUid`. Programmstart, Profilwechsel und neue QSOs lösen einen leichten Hintergrundabgleich aus.
- **Offline bleibt offline-tauglich:** Ist DA6IT.de vorübergehend nicht erreichbar, läuft das lokale Logging normal weiter. Der QSL-Abgleich wird später automatisch erneut versucht.
- **Motive und persönliche Layouts:** Community-Motive sowie die persönlichen Feldpositionen des jeweiligen Stationsprofils werden geladen und lokal gecacht. Eine kompakte Vorschau öffnet sich separat und hält die Haupt-App klein.
- **QRZ.com bleibt Empfängerquelle:** Die Gegenstationsadresse wird zentral auf DA6IT.de über QRZ.com ermittelt. Der Logger benötigt keine QRZ-Zugangsdaten und sendet keine ADIF-E-Mail-Adresse als autoritativen Empfänger.
- **Private Kontrollkopie:** Optional kann eine Kopie jeder tatsächlich versendeten QSL an eine bestätigte eigene Adresse gehen. Diese Adresse bleibt für die Gegenstation unsichtbar.
- **Status im Logbuch:** Erfolgreich an den Mailtransport übergebene QSLs werden im Logbuch angezeigt. Queue- und Versandstatus werden im Hintergrund nachgezogen.
- **Sicherer Versandpfad:** Der Offline Logger versendet niemals selbst per SMTP. Der endgültige Versand erfolgt ausschließlich über DA6IT.de/Postfix.

### Automatischer Hintergrundabgleich

Nach der einmaligen Einrichtung des Verbindungsschlüssels verwendet die App vorhandene lokale QSL-Daten sofort. Im Hintergrund werden neue noch nicht zugeordnete QSOs synchronisiert, offene Empfängerprüfungen verarbeitet, Status aktualisiert und Motive/Layout-Informationen nachgezogen.

Nach temporären Netzwerk- oder Serverfehlern wird später erneut versucht. Zusätzlich erfolgt ein leichter regelmäßiger Refresh. Dieser Hintergrundprozess **versendet niemals eigenständig QSL-Mails**.

### Kontrollkopie

Unter **Einstellungen → QSL** kann eine private Kontrollkopie aktiviert und eine eigene E-Mail-Adresse hinterlegt werden. Falls eine zusätzliche Bestätigung erforderlich ist, muss diese serverseitig abgeschlossen sein, bevor Kontrollkopien versendet werden.

Die Gegenstation sieht die Kontrolladresse nicht.

### Sicherheit und Datenschutz

Der Logger speichert den QSL-Verbindungsschlüssel als Secret und gibt ihn nicht in Logs aus. Die normale Empfängeradresse bleibt serverseitig autoritativ. Ein Verbindungsschlüssel kann daher nicht dazu verwendet werden, den QSL-Versand als frei adressierbares Mail-Relay zu missbrauchen.

Für die Release-Prüfung wurden die Python-Tests sowie die bestehenden Architektur-, Rotor-, Logstore-, WSJT-X- und Selftests ausgeführt. Bandit meldet keine Medium- oder High-Findings; `pip-audit` meldet keine bekannten Vulnerabilities.

### Wichtige Semantik

Ein QSL-Status **„versendet“** bedeutet, dass die Nachricht erfolgreich an den konfigurierten Mailtransport übergeben wurde. Er bedeutet nicht, dass die Nachricht beim Empfänger zugestellt, gelesen oder nicht durch einen Spamfilter zurückgehalten wurde.

Dokumentation: [Deutsch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.20.0/docs/USER_GUIDE.md) · [English](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.20.0/docs/en/USER_GUIDE.md)

---

## English

v0.20.0 brings the DA6IT.de QSL Card Manager directly into the Offline Logger while preserving the offline-first model: QSOs remain locally authoritative in ADIF, while motifs, recipient resolution, card delivery and status synchronize with DA6IT.de whenever an Internet connection is available.

### Highlights

- **QSL directly from the logbook:** one or multiple QSOs can be selected for QSL email. Single sends run directly while multi-selection uses the server-side queue.
- **No manual QSL sync required:** new QSOs automatically receive their `qsoUid`. Application startup, profile changes and newly logged QSOs trigger a lightweight background synchronization.
- **Offline remains fully usable:** if DA6IT.de is temporarily unavailable, local logging continues normally and QSL synchronization is retried later.
- **Motifs and personal layouts:** community motifs and station-profile-specific field positions are downloaded and cached locally. A compact preview opens separately to keep the main application small.
- **QRZ.com remains the recipient source:** the remote recipient is resolved centrally by DA6IT.de through QRZ.com. The Logger needs no QRZ credentials and never treats an ADIF email field as authoritative.
- **Private control copy:** an optional copy of each actually sent QSL can be delivered to a verified personal email address without exposing that address to the remote station.
- **Status in the logbook:** QSLs successfully handed to the mail transport are shown in the logbook, while queue and send status are refreshed in the background.
- **Safe delivery path:** the Offline Logger never sends email directly through SMTP. Final mail delivery always runs through DA6IT.de/Postfix.

### Automatic background synchronization

After the connection key has been configured once, existing local QSL data is available immediately. In the background the app synchronizes unmapped new QSOs, processes pending recipient checks, refreshes status and updates motif/layout information.

Temporary network or server failures are retried later, with an additional lightweight periodic refresh. This background process **never sends QSL email on its own**.

### Control copy

Under **Settings → QSL**, a private control copy can be enabled and a personal email address can be configured. If the server requires an additional verification step, that verification must be completed before control copies are sent.

The remote station never sees the control-copy address.

### Security and privacy

The Logger stores the QSL connection key as a secret and never writes it to logs. The normal recipient remains server-authoritative, preventing the connection key from turning the QSL API into an arbitrary-address mail relay.

Release validation included the Python tests together with the existing architecture, rotor, LogStore, WSJT-X and selftests. Bandit reports no Medium or High findings and `pip-audit` reports no known vulnerabilities.

### Important status semantics

QSL state **“sent”** means that the message was successfully handed to the configured mail transport. It does not mean that the message was delivered to, read by, or accepted by the recipient's spam filtering.

Documentation: [Deutsch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.20.0/docs/USER_GUIDE.md) · [English](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.20.0/docs/en/USER_GUIDE.md)

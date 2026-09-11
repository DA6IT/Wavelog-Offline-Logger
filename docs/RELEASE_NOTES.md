# DA6IT.de Wavelog Offline Logger v0.21.0

## Deutsch

v0.21.0 erweitert den Offline Logger um direkte QRZ.com-Aufrufe, lokale eQSL-basierte QSL-Empfehlungen und eine datensparsame pseudonyme Nutzungsstatistik. Gleichzeitig wurde der QSL Card Manager deutlich kompakter gestaltet.

### Highlights

- **QRZ.com direkt öffnen:** Im DX-Cluster kann die QRZ.com-Seite des ausgewählten Spots geöffnet werden. Auch im Reiter **QSO loggen** steht QRZ.com direkt für das eingegebene Rufzeichen bereit.
- **QSL-Empfehlungen mit lokalem eQSL-Abgleich:** Der Logger lädt die eQSL-Mitgliederliste lokal und kann eine E-Mail-QSL empfehlen, wenn die Gegenstation dort nicht gefunden wird oder seit mehr als sechs Monaten keinen aktuellen Log-Upload mehr hatte und eine nutzbare E-Mail-Adresse vorhanden ist.
- **Keine automatischen QSL-Mails:** Empfehlungen sind ausschließlich Hinweise. Der Versand startet nur nach einer ausdrücklichen Benutzeraktion und verwendet weiterhin den vorhandenen DA6IT.de-QSL-Card-Manager-Versandweg.
- **Mehr Platz für Empfehlungen:** QSL-Sync, Serverstatus und Motivauswahl sind deutlich kompakter. Dadurch steht der Empfehlungsliste wesentlich mehr Fläche zur Verfügung.
- **Pseudonyme Nutzungsstatistik:** Nach dem Erststart-Hinweis kann der Logger höchstens einmal täglich eine zufällige Installations-ID, Version und Betriebssystemfamilie an DA6IT.de melden. Rufzeichen, QSOs, Locator, Wavelog-Adresse und Zugangsdaten werden nicht übertragen. Die Funktion kann abgeschaltet und die gespeicherten Statistikdaten können direkt aus der App gelöscht werden.

### eQSL und QSL-Empfehlungen

Die eQSL-Mitgliederliste wird im App-Datenverzeichnis gecacht und vollständig lokal mit dem eigenen Logbuch verglichen. Das Empfehlungssystem überträgt die eigenen QSOs oder darin enthaltene Rufzeichen nicht an eQSL.

Ein eQSL-Eintrag gilt für die Empfehlung als aktiv, wenn innerhalb der letzten sechs Monate ein Log-Upload erkennbar ist. Fehlt der Eintrag oder liegt der letzte Upload länger zurück, kann ein QSO als Kandidat für eine E-Mail-QSL erscheinen. Bereits versendete sowie laufende oder queued QSL-Mails werden nicht erneut empfohlen.

Die Empfehlungen verwenden weiterhin die vorhandene serverseitige QRZ-Empfängerprüfung und den bestehenden QSL-Mailversand über DA6IT.de. Es wird keine neue eQSL-Funktion in der DA6IT-QSL-API benötigt.

### Datenschutz und Sicherheit

Die neue Nutzungsstatistik verwendet eine zufällige, nicht aus Rufzeichen, Hardware, Profil oder Wavelog-Daten abgeleitete Installations-ID. Vor Bestätigung des Erststart-Hinweises wird kein Heartbeat gesendet. DA6IT.de speichert in den Statistiktabellen nur den SHA-256-Hash der ID; da die Kennung über mehrere Starts stabil bleibt, wird die Verarbeitung ausdrücklich als pseudonym bezeichnet.

Der eQSL-Download ist größenbegrenzt, auf den vorgesehenen HTTPS-Host beschränkt und ersetzt einen vorhandenen Cache erst nach erfolgreicher Prüfung. Bei einem vorübergehenden Downloadfehler kann ein bereits vorhandener Cache weiterverwendet werden.

Die Datenschutzerklärung sowie README, Benutzerhandbuch und Architekturhinweise wurden für diese Funktionen aktualisiert.

Dokumentation: [Deutsch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.21.0/docs/USER_GUIDE.md) · [English](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.21.0/docs/en/USER_GUIDE.md)

---

## English

v0.21.0 adds direct QRZ.com actions, local eQSL-based QSL recommendations and privacy-conscious pseudonymous usage statistics while making the QSL Card Manager substantially more compact.

### Highlights

- **Open QRZ.com directly:** The selected DX Cluster spot can be opened on QRZ.com, and the **Log QSO** page can open QRZ.com for the currently entered callsign.
- **QSL recommendations with local eQSL matching:** The Logger downloads the eQSL member list locally and can recommend an email QSL when the remote station is not listed or has not uploaded a log for more than six months and a usable email address is available.
- **No automatic QSL email:** Recommendations are advisory only. Sending still requires an explicit user action and continues to use the existing DA6IT.de QSL Card Manager delivery path.
- **More room for recommendations:** QSL synchronization, server status and motif selection are more compact, leaving substantially more space for the recommendation list.
- **Pseudonymous usage statistics:** After the first-start notice, the Logger can report a random installation ID, application version and operating-system family to DA6IT.de at most once per day. Callsigns, QSOs, locators, Wavelog URLs and credentials are not sent. Statistics can be disabled and the stored statistics for the current installation can be deleted directly from the app.

### eQSL and QSL recommendations

The eQSL member list is cached in the application data directory and compared with the local logbook entirely on the user's device. The recommendation feature does not upload the user's QSOs or local callsign list to eQSL.

An eQSL entry is treated as active for recommendation purposes when a log upload is visible within the last six months. Missing entries or older activity can make a QSO eligible for an email-QSL recommendation. Already sent and queued/pending QSL emails are not recommended again.

Recommendations continue to use the existing server-side QRZ recipient check and the established DA6IT.de QSL email path. No new eQSL functionality is required in the DA6IT QSL API.

### Privacy and security

Usage statistics use a random installation identifier that is not derived from callsigns, hardware, profiles or Wavelog data. No heartbeat is sent before the first-start notice has been acknowledged. DA6IT.de stores only the SHA-256 hash of the identifier in the statistics tables; because the identifier remains stable across starts, the processing is explicitly described as pseudonymous.

The eQSL download is size-bounded, restricted to the intended HTTPS host and only replaces an existing cache after successful validation. An existing cache can remain usable during temporary download failures.

The privacy policy, README, user guide and architecture notes have been updated for these features.

Documentation: [Deutsch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.21.0/docs/USER_GUIDE.md) · [English](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.21.0/docs/en/USER_GUIDE.md)

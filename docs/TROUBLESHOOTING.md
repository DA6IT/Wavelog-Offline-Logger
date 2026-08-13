# Fehlerhilfe

## Die EXE startet beim ersten Mal nicht sofort

Der erste Start lädt und installiert eine private Python-Laufzeit. Prüfe die Internetverbindung und warte einige Minuten. Beim nächsten Start wird ein fehlgeschlagener Vorgang erneut versucht.

## Windows meldet einen unbekannten Herausgeber

Die derzeitigen Community-Builds sind nicht digital signiert. Vergleiche vor dem Start die SHA-256-Prüfsumme der Datei mit `SHA256SUMS.txt` aus demselben GitHub-Release. Lade Builds ausschließlich aus dem offiziellen Release-Bereich des Projekts.

## CAT verbindet sich nicht

Prüfe unter **CAT Setup** das gewählte Funkgerätemodell, den COM-Port, die Baudrate und die seriellen Parameter. Der COM-Port darf nicht gleichzeitig von einer anderen CAT-Anwendung belegt sein. Hamlib ist im Windows-Build bereits enthalten und muss nicht separat installiert werden; der zum Funkgerät oder USB-Adapter gehörende Windows-Treiber kann dennoch erforderlich sein.

## Kein Update-Hinweis beim Programmstart

Ohne Internetverbindung oder wenn GitHub nicht erreichbar ist, bleibt die Update-Prüfung absichtlich still. Stabile Versionen weisen außerdem nicht auf Vorabversionen hin. Releases können jederzeit manuell unter https://github.com/DA6IT/Wavelog-Offline-Logger/releases geprüft werden.

## Wavelog-Verbindung schlägt fehl

Prüfe:

- vollständige Basis-URL einschließlich `https://`
- Erreichbarkeit der Wavelog-Instanz im Browser
- API-v2-Token und dessen Berechtigungen
- ausgewähltes Stationsprofil
- lokale Firewall, Proxy oder VPN

Tokens niemals in einem öffentlichen Issue posten.

## QSOs fehlen nach dem Sync

Nicht sofort Dateien oder Metadaten löschen. Sichere zuerst den ADI-Ordner und die Anwendungsdaten. Prüfe danach das aktive Profil, den eingestellten Logpfad, Stationsprofil und Operatorfilter.

Ein außerhalb der App aus einer ADI-Datei verschwundenes, in Wavelog aber noch vorhandenes QSO sollte beim nächsten vollständigen Abgleich lokal wiederhergestellt werden.

## Viele Konflikte nach einem Update

Beende die Anwendung nicht durch Löschen der Metadata-Datenbank. Erstelle eine Sicherung und dokumentiere:

- Ausgangsversion und Zielversion
- Anzahl der Konflikte
- ob Contest-Felder betroffen sind
- ob lokale ADI-Dateien extern bearbeitet wurden

Danach ein Issue mit anonymisierten Beispieldaten eröffnen.

## Logordner lässt sich nicht öffnen

Prüfe, ob der Ordner noch existiert und das Benutzerkonto Schreibrechte besitzt. Netzlaufwerke oder synchronisierte Cloudordner können vorübergehend nicht erreichbar oder gesperrt sein.

## Diagnoseinformationen für ein Issue

- Programmversion
- Windows-Version
- genaue Schritte bis zum Fehler
- vollständiger Wortlaut der Fehlermeldung
- anonymisierte Beispieldaten

Keine Tokens, privaten Rufzeichen-/Adressdaten oder vollständigen privaten Logs veröffentlichen.

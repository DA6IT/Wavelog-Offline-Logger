# Fehlerhilfe

## Die EXE startet beim ersten Mal nicht sofort

Der erste Start lädt und installiert eine private Python-Laufzeit. Prüfe die Internetverbindung und warte einige Minuten. Beim nächsten Start wird ein fehlgeschlagener Vorgang erneut versucht.

## Windows meldet einen unbekannten Herausgeber

Die derzeitigen Community-Builds sind nicht digital signiert. Vergleiche vor dem Start die SHA-256-Prüfsumme der Datei mit `SHA256SUMS.txt` aus demselben GitHub-Release. Lade Builds ausschließlich aus dem offiziellen Release-Bereich des Projekts.

## macOS blockiert den ersten Start

Die macOS-Pakete sind technisch ad-hoc signiert, aber noch nicht mit einem kostenpflichtigen Apple-Developer-Zertifikat signiert und notarisiert. Lade das passende Paket nur aus dem offiziellen GitHub-Release, vergleiche die beiliegende `.sha256`-Datei und wähle die entpackte App im Finder mit Rechtsklick → **Öffnen**. Der Logger verändert Gatekeeper oder andere Sicherheitseinstellungen nicht automatisch.

## CAT verbindet sich nicht

Prüfe unter **CAT Setup** das gewählte Funkgerätemodell, den seriellen Port, die Baudrate und die seriellen Parameter. Der Port darf nicht gleichzeitig von einer anderen CAT-Anwendung belegt sein. Hamlib ist in den Windows- und macOS-Builds bereits enthalten und muss nicht separat installiert werden; der zum Funkgerät oder USB-Adapter gehörende Treiber kann dennoch erforderlich sein.

## DX Cluster verbindet sich nicht

Die DX-Cluster-Funktion benötigt Internet. Prüfe Host, Telnet-Port, Login-Rufzeichen, Firewall, VPN und gegebenenfalls den Status des gewählten Clusters. Als Vorgabe verwendet der Logger `dxcluster.afu-tools.de:7300`; eigene DXSpider-kompatible Telnet-Server können profilbezogen eingetragen werden. Die Verbindung wird nach einem Programmstart nicht automatisch hergestellt.

Bei aktiver Verbindung zeigt der Status die Zahl der in dieser Sitzung empfangenen Spots und die Uhrzeit des letzten Empfangs. Neue Spots werden sofort ergänzt. Bleibt „letzter Spot: noch keiner“ stehen, kann der Cluster gerade ruhig sein oder die Anmeldung noch nicht abgeschlossen sein. Werden Spots gezählt, aber nicht angezeigt, prüfe Band-, Mode- und Zeitraumfilter; standardmäßig sind nur die letzten 30 Minuten sichtbar.

## Ein eigener DX-Spot wird nicht gesendet

Der Button **DX-Spot senden** funktioniert erst nach einer aktiven Telnet-Anmeldung. Rufzeichen und Frequenz müssen im normalen QSO-Formular stehen. Jeder Spot wird öffentlich verbreitet und muss deshalb nach Eingabe des optionalen Kommentars ausdrücklich bestätigt werden. Ob ein Cluster einen Befehl anschließend fachlich akzeptiert, hängt von dessen Regeln und dem verwendeten Login ab.

## UDP Logging meldet „Port bereits belegt“

Ein UDP-Port kann auf derselben Bind-Adresse normalerweise nur von einem Empfänger verwendet werden. Trage unter **UDP Logging** einen anderen freien Port ein und verwende exakt dieselbe Nummer im sendenden Programm. Nach **UDP stoppen** und erneutem **UDP starten** ist die Änderung aktiv; ein kompletter Programmneustart ist nicht nötig.

Wenn JTAlert oder GridTracker bereits den primären WSJT-X-Port belegt, kann WSJT-X den zusätzlichen „logged contact ADIF broadcast“ an einen separaten Port des Offline Loggers senden.

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

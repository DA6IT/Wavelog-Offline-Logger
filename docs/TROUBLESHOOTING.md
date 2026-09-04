# Fehlerhilfe

## Die EXE startet beim ersten Mal nicht sofort

Der erste Start lädt und installiert eine private Python-Laufzeit. Prüfe die Internetverbindung und warte einige Minuten. Beim nächsten Start wird ein fehlgeschlagener Vorgang erneut versucht.

## Windows meldet einen unbekannten Herausgeber

Die derzeitigen Community-Builds sind nicht digital signiert. Vergleiche vor dem Start die SHA-256-Prüfsumme der Datei mit `SHA256SUMS.txt` aus demselben GitHub-Release. Lade Builds ausschließlich aus dem offiziellen Release-Bereich des Projekts.

## macOS blockiert den ersten Start

Die macOS-Pakete sind technisch ad-hoc signiert, aber noch nicht mit einem kostenpflichtigen Apple-Developer-Zertifikat signiert und notarisiert. Lade das passende Paket nur aus dem offiziellen GitHub-Release, vergleiche die beiliegende `.sha256`-Datei und wähle die entpackte App im Finder mit Rechtsklick → **Öffnen**. Der Logger verändert Gatekeeper oder andere Sicherheitseinstellungen nicht automatisch.

## CAT verbindet sich nicht

Prüfe unter **CAT Setup** das gewählte Funkgerätemodell, den seriellen Port, die Baudrate und die seriellen Parameter. Der Port darf nicht gleichzeitig von einer anderen CAT-Anwendung belegt sein. Hamlib ist in den Windows- und macOS-Builds bereits enthalten und muss nicht separat installiert werden; der zum Funkgerät oder USB-Adapter gehörende Treiber kann dennoch erforderlich sein.

Schlägt ein manuelles Hamlib-Update unter Windows fehl, bleibt die bisherige Laufzeit aktiv. Prüfe Internetverbindung und GitHub-Erreichbarkeit und versuche es später erneut. Funktioniert CAT erst seit einem erfolgreichen Hamlib-Update schlechter, verwende im CAT Setup **Vorherige Version wiederherstellen**.

Bei **FLRig** wird statt eines COM-Ports eine Adresse im Format `IP/Hostname:Port` benötigt. Lokal ist dies normalerweise `127.0.0.1:12345`. Falls **FLRig suchen** keinen Treffer liefert, prüfe den in FLRig eingestellten XML-RPC-Port und die Firewall und trage die Adresse manuell ein. Die automatische Suche bleibt bewusst auf den eigenen Rechner und begrenzte private IPv4-Netze beschränkt; andere Subnetze und IPv6-Ziele müssen manuell angegeben werden.

## DX Cluster verbindet sich nicht

Die DX-Cluster-Funktion benötigt Internet. Prüfe Host, Telnet-Port, Login-Rufzeichen, Firewall, VPN und gegebenenfalls den Status des gewählten Clusters. Als Vorgabe verwendet der Logger `dxcluster.afu-tools.de:7300`; eigene DXSpider-kompatible Telnet-Server können profilbezogen eingetragen werden. Die Verbindung wird nach einem Programmstart nicht automatisch hergestellt.

Bei aktiver Verbindung zeigt der Status die Zahl der in dieser Sitzung empfangenen Spots und die Uhrzeit des letzten Empfangs. Neue Spots werden sofort ergänzt. Bleibt „letzter Spot: noch keiner“ stehen, kann der Cluster gerade ruhig sein oder die Anmeldung noch nicht abgeschlossen sein. Werden Spots gezählt, aber nicht angezeigt, prüfe Band-, Mode- und Zeitraumfilter; standardmäßig sind nur die letzten 30 Minuten sichtbar.

## Ein eigener DX-Spot wird nicht gesendet

Der Button **DX-Spot senden** verwendet Rufzeichen und Frequenz aus dem normalen QSO-Formular. Ist das Formular nach einem gespeicherten manuellen oder WSJT-X-QSO bereits geleert, bietet der Button stattdessen ausdrücklich das zuletzt geloggte QSO an. Jeder Spot wird öffentlich verbreitet und muss deshalb nach Eingabe des optionalen Kommentars ausdrücklich bestätigt werden. Die App baut die konfigurierte Telnet-Verbindung bei Bedarf auf; ob der Cluster den Befehl fachlich akzeptiert, hängt von dessen Regeln und dem verwendeten Login ab.

## UDP Logging meldet „Port bereits belegt“

Ein UDP-Port kann auf derselben Bind-Adresse normalerweise nur von einem Empfänger verwendet werden. Trage unter **UDP Logging** einen anderen freien Port ein und verwende exakt dieselbe Nummer im sendenden Programm. Nach **UDP stoppen** und erneutem **UDP starten** ist die Änderung aktiv; ein kompletter Programmneustart ist nicht nötig.

Wenn JTAlert oder GridTracker bereits den primären WSJT-X-Port belegt, kann WSJT-X den zusätzlichen „logged contact ADIF broadcast“ an einen separaten Port des Offline Loggers senden.

## Kein Update-Hinweis beim Programmstart

Ohne Internetverbindung oder wenn GitHub nicht erreichbar ist, bleibt die Update-Prüfung absichtlich still. Stabile Versionen weisen außerdem nicht auf Vorabversionen hin. Releases können jederzeit manuell unter https://github.com/DA6IT/Wavelog-Offline-Logger/releases geprüft werden.

Scheitert der automatische Download oder stimmt die SHA-256-Prüfsumme nicht, bleibt die installierte Programmdatei unverändert. Unter Windows muss die gestartete EXE an ihrem Speicherort überschreibbar sein. Bei einer portable gestarteten Datei in einem geschützten Ordner die EXE zuerst in einen eigenen beschreibbaren Ordner verschieben.

## Wavelog-Verbindung schlägt fehl

Prüfe:

- vollständige Basis-URL einschließlich `https://`
- Erreichbarkeit der Wavelog-Instanz im Browser
- API-v2-Token und dessen Berechtigungen
- ausgewähltes Stationsprofil
- lokale Firewall, Proxy oder VPN

Tokens niemals in einem öffentlichen Issue posten.

Bei `CERTIFICATE_VERIFY_FAILED` verwendet ein aktueller Build zuerst den nativen Zertifikatsspeicher des Betriebssystems und zusätzlich ein gebündeltes CA-Paket als Fallback. Prüfe trotzdem Systemdatum, ausstehende Betriebssystem-Zertifikatsupdates sowie TLS-inspektierende Firmen-Proxys oder Virenscanner. Die Zertifikatsprüfung wird aus Sicherheitsgründen nicht abschaltbar gemacht.

## Contest-Sessions erscheinen nicht oder werden nicht verknüpft

Führe im Contest-Bereich **Mit Wavelog abgleichen** aus und prüfe den dort angezeigten Contest-API-Status. Der API-v2-Token benötigt `contest:read` zum Laden sowie `contest:write` zum Anlegen, Ändern und Verknüpfen. Der gewählte Contest muss in Wavelogs Contest-Katalog aktiv sein. Bei Clubstationen kann ein Mitglied eigene QSOs verknüpfen; zum Erstellen oder Bearbeiten der gemeinsamen Session sind Club-Officer-Rechte erforderlich.

Die Contest-API ist noch nicht in jeder Wavelog-Version enthalten. Ein `404`, `405` oder fehlender Contest-Scope verhindert deshalb bewusst weder das lokale Speichern noch den normalen QSO-Sync. Die Session bleibt lokal und kann nach einem Wavelog-Update erneut abgeglichen werden.

## SYNC-FEHLER in der Logbuchtabelle

Markiere das rote QSO. Unter der Tabelle erscheint die gespeicherte Ursache. Gehört die verknüpfte Wavelog-ID zu einem anderen Stationsprofil, bleiben ADI-Datensatz und Zuordnung unangetastet; eine automatische Reparatur findet bewusst nicht statt. Sichere vor einer manuellen Korrektur den ADI-Ordner und die Profildaten.

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

## Die ADI-Zusammenführung schlägt fehl

Die App lässt die vorhandenen Tagesdateien unangetastet, wenn Sicherung, Schreiben oder anschließende Verifikation nicht vollständig erfolgreich ist. Beende die App, kopiere den gesamten ADI-Ordner und prüfe freien Speicherplatz, Schreibrechte sowie eine mögliche Sperre durch Cloud-Synchronisation oder Virenscanner. Lösche weder das ZIP-Backup noch `.migration-backups`. Mit diesen Dateien kann der ursprüngliche Zustand nachvollzogen und wiederhergestellt werden.

## xOTA findet keinen oder den falschen Park

Prüfe zuerst Breiten- und Längengrad sowie die angezeigte GPS-Genauigkeit. Aktualisiere bei bestehender Internetverbindung die Referenzdaten und suche erneut. Ein POTA-Katalogpunkt ist nur ein Marker und kann bei großen Parks weit vom tatsächlichen Standort entfernt liegen. Kandidaten bis 25 km werden deshalb angezeigt, müssen aber mit **POTA-Grenze prüfen** und der offiziellen Parkinformation bewusst bestätigt werden. Eine fehlende Standortfreigabe verhindert nicht die manuelle Koordinateneingabe.

## Diagnoseinformationen für ein Issue

- Programmversion
- Windows-Version
- genaue Schritte bis zum Fehler
- vollständiger Wortlaut der Fehlermeldung
- anonymisierte Beispieldaten

Keine Tokens, privaten Rufzeichen-/Adressdaten oder vollständigen privaten Logs veröffentlichen.

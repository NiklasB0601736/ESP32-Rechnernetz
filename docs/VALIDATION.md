# Geprüfter Stand

Prüfdatum: **27.10.2026**. Angeforderte Hardware: zwei ESP32-WROOM-32, ESP-IDF 6.0.1, Target `esp32`.

## Ausgeführt

| Prüfung | Ergebnis |
|---|---|
| ESP-IDF-Build Master | Erfolgreich, inklusive Bootloader, Partitionstabelle, ELF und BIN |
| ESP-IDF-Build Slave | Erfolgreich, mit deaktivierter Master-Rolle, lokaler ID 2 und Peer-ID 1 |
| Eigene C-Quellen | Kompiliert mit `-Wall -Wextra -Werror` |
| Python-Tests | 20 Tests erfolgreich: Auswertung, Grenzen, fehlende Messwerte, Origin-/API-/WebSocket-Vertrag, Konfiguration, Rückkehranforderung, Neustarterkennung, beide Simulationsrichtungen und Stopp |
| Tatsächliches C-Messmodul auf dem PC | Erfolgreich mit Host-Clang/LLD: gleiche `firmware/main/metrics.c`, Duplikate, vertauschte Reihenfolge, verspätete/fremde Sequenzen, RSSI-Zähler, wiederholtes ARM, RTT und Timeout, Jitter, Stoppdauer, Drainzeit und Erholung bei Senderausfall |
| Browser, Chrome headless | Erfolgreich: beide Geräte, unabhängige Leistung, gemeinsames Profil, zwei abgeschlossene Richtungsversuche, vier Diagramme, BER bleibt `null` / „nicht messbar“, keine JavaScript-Ausnahmen |
| Mobile Ansicht | 390 px Viewport, keine horizontale Seitenüberbreite |
| Normierung | Bekannte Referenzwerte, Grenzwerte, Clipping und fehlende Werte automatisiert geprüft |
| Geräteerkennung am PC | COM-Ports gelesen; CP210x auf COM6 erkannt. Kein Port geöffnet und keine Gerätefirmware verändert |

Die Binärdateien der ersten Builds verwenden absichtlich eine **nicht konfigurierte Peer-MAC** (`00:00:00:00:00:00`). Vor dem Funkbetrieb sind beide Peer-MACs in den jeweiligen `menuconfig`-Konfigurationen einzutragen und beide Rollen erneut zu bauen. Die hier erzeugten Bilder sind damit Build-Nachweise und können zum Auslesen der lokalen MAC dienen; sie sind noch kein gekoppelter Zwei-Geräte-Aufbau.

Nachweise im lokalen Projekt:

- `data/verification/build-master.log`, `build-slave.log`
- `data/verification/python-tests.log`, `firmware-metrics-tests.log`
- `data/verification/browser-test.json`
- `data/verification/dashboard-desktop.png`, `dashboard-mobile.png`
- `firmware/build-master/espnow_funklabor.bin` und `firmware/build-slave/espnow_funklabor.bin`

Der Browser-Test verarbeitet ausschließlich die ausdrücklich markierte Simulation. Ein Test der portablen C-Messlogik ist ein PC-Lauf dieses Moduls und keine Ausführung auf dem ESP32. Die IDF-Werkzeuge mussten für Builds außerhalb der Ausführungssandbox laufen, weil Windows-Prozesspipes dort gesperrt waren. Die Python-Tests benötigten dies für temporäre Testverzeichnisse. Es wurden keine systemweiten Richtlinien geändert und keine Boards geflasht.

## Mit Hardware noch offen

Für **keine** Funkfunktion liegt bislang ein realer Zwei-Board-Versuch vor. Noch zu bestätigen sind insbesondere:

- Boot und Laufzeit ohne Resets, freigegebene Peer-Kopplung, Slavebetrieb ausschließlich mit Stromversorgung.
- ESP-NOW-Daten und Status in beiden Richtungen, RSSI-Metadaten und tatsächlich erreichte Senderate.
- Vom konkreten Treiber angenommene Leistungsstufen und Profile; Rücklesung auf beiden Boards.
- Gemeinsamer Profilwechsel und neue Heartbeat-Transaktions-ID auf Hin- und Rückweg.
- Lease-Rückkehr nach 15 s bei verlorenem Bestätigungsweg sowie expliziter Rollback bei Teilfehlern.
- MAC-Sendestatus, tatsächliche Ziel-RX und Anwendungsantworten bei gezielt geschwächtem Link.
- Laufzeit- und Queue-Verhalten bei 500 Paketen/s, hohe Verluste, vorzeitiger Stopp und Wiederverbindung nach USB-Ausfall.
- HF-seitige Bestätigung der tatsächlichen PHY-Rate und abgestrahlten Leistung durch separate Messtechnik, falls für die Arbeit benötigt.

Die Schritte zur Abnahme stehen in [README.md](../README.md). Erst ein protokollierter Test mit beiden gekoppelten Boards bestätigt den Hardware-Meilenstein. Insbesondere werden erfolgreiche Simulation und erfolgreiche Kompilierung nicht als Funknachweis ausgegeben.

## Grenzen dieses Meilensteins

Eine direkte Verbindung mit einem Peer pro Gerät, ein gerichteter Versuch zugleich, konstante Kanalbreite 20 MHz und ein in der Firmware konfigurierter gemeinsamer Kanal. Keine Mehrsprungweiterleitung und kein Routing. Konfigurationen gelten bis zum Neustart; der Startwert ist 18 dBm / OFDM 6 Mbit/s. BER ist über den genutzten Empfangspfad nicht belastbar messbar. Radar-Referenzen sind Labor-Vergleichswerte.

Verlorene ACKs beweisen keinen Verlust des Datenhinwegs. Queue-Überläufe beeinflussen die Anwendungszustellung und müssen bei Funkinterpretationen beachtet werden. Laufende Verlustwerte sind wegen versetzt eintreffender Zähler vorläufig. Ein PC-Ausfall genau zwischen einzelnen Commit-Bestätigungen kann eine teilweise bestätigte Konfiguration hinterlassen; das Verfahren und die Wiederherstellung sind in [PROTOCOLS.md](PROTOCOLS.md) beschrieben.

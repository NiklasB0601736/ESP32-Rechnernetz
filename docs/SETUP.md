# Einrichtung und Hardwarebetrieb

Alle Befehle werden im Projektverzeichnis ausgeführt, sofern kein anderer Ordner angegeben ist. Zur Projektübersicht: [README.md](../README.md).

Experimentelle Plattform für das Hochschulfach Rechnernetze. Zwei **ESP32-WROOM-32** tauschen lokal erzeugte Testpakete aus. Der Master verbindet das Funknetz per USB/UART mit einem PC; FastAPI und die komplette Weboberfläche laufen ausschließlich auf dem PC.

**Stand:** Firmware und Software sind implementiert. Simulation, automatisierte Auswertung und Browserbedienung sind prüfbar. Ein Hardware-Abnahmeversuch mit zwei geflashten Boards steht aus. Details und konkrete Prüfergebnisse: [docs/VALIDATION.md](VALIDATION.md).

```text
Browser ← HTTP / WebSocket → Python / FastAPI ← USB / UART → Master
                                                            ⇅ ESP-NOW
                                                           Slave
```

## Sofort ohne Hardware starten

Python 3.11–3.13, im Projektverzeichnis:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m backend.app --demo
```

Dann **http://127.0.0.1:8000** öffnen. Sind die Abhängigkeiten bereits vorhanden, reicht `python -m backend.app --demo`. Der orange Hinweis kennzeichnet synthetische Daten. Chart.js 4.4.8 samt MIT-Lizenz liegt lokal im Projekt; der Browser braucht kein Internet. Beenden mit `Strg+C`.

Die Oberfläche zeigt Netzansicht und Geräte, getrennte Sendeleistungsobergrenzen, gemeinsames PHY-Profil, Versuchseinstellungen, Rohwerte, Radar-Chart, drei Zeitverläufe und ein Ereignisprotokoll. Abgeschlossene Versuche werden unter `data/tests/` als JSON archiviert und sind über den Browser exportierbar.

## Firmware bauen und flashen

Ziel ist ausschließlich `esp32` / WROOM-32. **ESP-IDF v6.0.1** ist fest vorgegeben; andere Chips oder IDF-Versionen werden absichtlich beim Build abgelehnt. Diese Wahl nutzt die vorhandene Installation `C:\esp\v6.0.1\esp-idf` und die zugehörigen Werkzeuge unter `C:\Espressif`. cJSON `1.7.19~2` wird beim ersten Build durch den IDF Component Manager bezogen; danach ist die Komponente lokal verfügbar.

Die zwei Boards brauchen unterschiedliche Knoten-IDs und die **STA-MAC-Adresse des jeweils anderen Boards**. Es gibt keine automatische Kopplung. Die Firmware akzeptiert ausschließlich diese freigegebene MAC-/ID-Kombination.

1. STA-MACs zunächst aus vorhandenen Geräteinformationen oder mit `esptool --port COM6 read-mac` in der ESP-IDF-Shell ermitteln. Alternativ lässt sich die Firmware mit der Standard-Peer-MAC `00:00:00:00:00:00` zum Auslesen der eigenen MAC starten: Sie meldet diese seriell und sendet dabei keine Funkpakete an einen Peer. Die Standard-Builds sind deshalb **noch nicht miteinander gekoppelt**.
2. Master konfigurieren: Rolle Master, lokale ID 1, Peer-ID 2, Peer-MAC des Slaves, Kanal 6. Slave konfigurieren: Master-Option deaktiviert, lokale ID 2, Peer-ID 1, Peer-MAC des Masters, ebenfalls Kanal 6. Einstellungen liegen unter **Funklabor** in `menuconfig`.
3. Beide Rollen bauen und jeweils auf das richtige Board flashen. Der Slave benötigt anschließend nur Strom, keine PC-Datenverbindung.

Für die auf diesem PC gefundene EIM-Installation, aus dem Projektverzeichnis:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\idf.ps1 -Role master -Action menuconfig
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\idf.ps1 -Role master -Action build
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\idf.ps1 -Role master -Action flash -Port COM6

powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\idf.ps1 -Role slave -Action menuconfig
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\idf.ps1 -Role slave -Action build
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\idf.ps1 -Role slave -Action flash -Port COM7
```

`COM6` und `COM7` sind Beispiele: den jeweiligen Board-Port einsetzen. Das Skript flasht ausschließlich mit `-Action flash`; `build` schreibt keine Geräte. `-IdfPath` und `-ToolsPath` erlauben andere Installationspfade. `-Action monitor -Port COM6` öffnet den seriellen Monitor; vor dem Backendstart schließen. Das Skript setzt die Ausführungsrichtlinie nur für seinen Prozess und ändert keine systemweite Richtlinie. Bei EIM-Installationen ohne ältere Constraints-Datei verwendet es die bereits installierte versionsgebundene Python-Umgebung.

Alternativ in einer **aktivierten ESP-IDF-6.0.1-Shell**, im Ordner `firmware`:

```powershell
idf.py -B build-master -D SDKCONFIG=sdkconfig.master -D SDKCONFIG_DEFAULTS=sdkconfig.defaults menuconfig
idf.py -B build-master -D SDKCONFIG=sdkconfig.master build
idf.py -B build-master -D SDKCONFIG=sdkconfig.master -p COM6 flash

idf.py -B build-slave -D SDKCONFIG=sdkconfig.slave -D 'SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.slave.defaults' menuconfig
idf.py -B build-slave -D SDKCONFIG=sdkconfig.slave build
idf.py -B build-slave -D SDKCONFIG=sdkconfig.slave -p COM7 flash
```

Die getrennten Build- und Konfigurationsdateien verhindern, dass beim Rollenwechsel versehentlich derselbe Build verwendet wird. `sdkconfig.*` speichert die lokalen Peer-MACs und wird nicht versioniert.

## Hardwarebetrieb und erster Versuch

```powershell
python -m backend.app --port COM6
```

Oder `python -m backend.app` starten und den Master-Port im Browser auswählen. Baudrate: **115200, 8N1**. Das Backend versucht beim Öffnen, DTR/RTS deaktiviert zu halten; manche USB-Bridges können trotzdem einen Reset auslösen. Keine andere Anwendung darf denselben Port geöffnet halten. Auf diesem PC wurde ein CP210x-Gerät auf COM6 erkannt; dessen Firmware und Boardidentität wurden nicht abgefragt.

1. Beide Boards zunächst bei guter Funkverbindung einschalten. Nach etwa drei Sekunden müssen beide im Browser online erscheinen: unterschiedliche IDs/MACs, Kanal 6 / 2437 MHz, Bandbreite 20 MHz und Profil `ofdm6`. Ohne gültige Peer-MACs erscheint nur der Master.
2. Master → Slave, 128 Byte, 50 Pakete/s, 20 Sekunden starten. Nach Sendeende folgen Drain-/Berichtszeiten; auf „Abgeschlossen“ warten. Prüfen: TX, eindeutige Ziel-RX, MAC-Status, Anwendungsantworten, plausibler Goodput und RSSI.
3. Slave → Master mit identischen Einstellungen wiederholen. RSSI gehört jeweils zum Datenempfang am Ziel; RTT umfasst Hin- und Rückrichtung.
4. Sendeleistung **nur eines** Knotens auf z. B. 11 dBm setzen. Ausstehende Änderung, Rückbestätigung und unabhängigen Wert des anderen Knotens prüfen. Beide Richtungen erneut untersuchen.
5. Gemeinsames Profil wechseln; nur die Schnittmenge der von beiden Geräten bestätigten Profile ist auswählbar. Erst nach Bestätigung testen.
6. Einen längeren Versuch vorzeitig stoppen. Die Auswertung muss die tatsächliche Sendedauer verwenden und die Abschlussberichte abwarten.
7. Für einen kontrollierten Ausfallversuch den Slave vorübergehend stromlos machen: Offline nach 4 s; fehlende Zielberichte ergeben **keinen erfundenen Paketverlust**. Bei einer unbestätigten Konfigurationsänderung stellt die Firmware nach 15 s die vorherige Einstellung wieder her. Details zu Teilbestätigungen stehen in [docs/PROTOCOLS.md](PROTOCOLS.md).
8. Ergebnisse exportieren. Abstand, Umgebung, Antennenausrichtung, USB-Stromversorgung und eventuelle Queue-Verluste zum Versuch notieren. Geringere Sendeleistung reduziert das Linkbudget und erzeugt kein zusätzliches Störsignal.

Für jedes PHY-Profil zuerst eine kurze Funktionsprüfung durchführen. Eine vom Treiber angenommene Rate bestätigt die Konfiguration; die tatsächlich ausgesendete PHY-Rate lässt sich erst mit unabhängiger Funkaufzeichnung verifizieren. Die Soll-Senderate ist keine garantierte Rate: MAC-Wartezeiten, Messantworten und Statusverkehr können die erreichte Rate reduzieren.

## Tests und Aufbau

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
# Optional: tatsächliches Firmware-Messmodul auf dem PC ausführen
python scripts/test_firmware_metrics.py
# Bei laufender Demo und installiertem Chrome:
python scripts/browser_smoke.py
```

Der Browser-Test steuert Leistung, gemeinsames Profil und beide Testrichtungen über die tatsächlichen Formulare. Er prüft die vier Diagramme und eine mobile Ansicht; Nachweise liegen unter `data/verification/`. Der optionale native C-Test verwendet standardmäßig das hier vorhandene Clang/LLD aus MATLAB, startet MATLAB aber nicht. Über `--clang-dir` lässt sich ein anderer Host-Clang angeben. Er führt die unveränderte `metrics.c` als PC-Bibliothek aus; das ersetzt keinen ESP32-Laufzeittest.

| Ordner | Aufgabe |
|---|---|
| `firmware/main/radio.*` | ESP-NOW, MAC-Freigabe, Empfangsmetadaten, Treiberfähigkeiten |
| `firmware/main/metrics.*` | Messfenster, Sequenz-Bitmaps, Duplikate, RTT, Jitter |
| `firmware/main/gateway.*` | JSON-Zeilen über UART, binäre Steuerbefehle |
| `firmware/main/main.c` | Rollen, Konfigurationslease, Steuerung und Aggregation |
| `backend/` | FastAPI, serieller Transport, Transaktionen, Auswertung, Archiv, Simulation |
| `frontend/` | Browseroberfläche und lokal eingebundenes Chart.js |
| `tests/` | Auswertungs-, API-, Steuerungs- und Simulationstests |
| `docs/` | Protokolle, Messmethodik, geprüfter Stand |

Backend und UI verwalten Knoten nach ID und freigegebene Kanten als Daten. Die Firmware hat in diesem Meilenstein genau einen konfigurierten direkten Peer. Für fünf Knoten lässt sich der Radioadapter auf eine Peer-Tabelle erweitern; Weiterleitung, Routing, Pfadwahl und Mesh-Discovery sind bewusst noch nicht implementiert. Pro Gateway läuft jeweils ein gerichteter Versuch.

Die lokale Anwendung bindet standardmäßig ausschließlich an `127.0.0.1`. Messdaten bleiben auf dem PC. Die erste Funkversion verwendet unverschlüsseltes Unicast mit MAC-/ID-Freigabe; kryptografische Authentifizierung und Mehrbenutzerbetrieb sind keine Funktionen dieses Laboraufbaus.

## Technische Referenzen

Chip und PHY-API: [ESP32 Wi-Fi API, ESP-IDF 6.0.1](https://docs.espressif.com/projects/esp-idf/en/v6.0.1/esp32/api-reference/network/esp_wifi.html), [ESP-NOW API, ESP-IDF 6.0.1](https://docs.espressif.com/projects/esp-idf/en/v6.0.1/esp32/api-reference/network/esp_now.html), [zugehöriger ESP-NOW-Header](https://github.com/espressif/esp-idf/blob/v6.0.1/components/esp_wifi/include/esp_now.h). Tabellen und Einschränkungen: [docs/MEASUREMENT.md](MEASUREMENT.md).

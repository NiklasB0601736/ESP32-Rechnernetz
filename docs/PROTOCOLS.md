# Architektur und Schnittstellen

## Schichten und Zuständigkeit

Funkadapter (`radio.*`), Messlogik (`metrics.*`), serielles Gateway (`gateway.*`) und die Zustandsmaschine (`main.c`) sind getrennt. Im Empfangscallback werden Daten und RSSI in eine begrenzte Queue kopiert; keine JSON-Erzeugung, keine Flashzugriffe und kein langer Testbetrieb laufen im Wi-Fi-Callback. Senden erfolgt aus einem Task mit genau einem ausstehenden ESP-NOW-Paket, um Callbacks korrekt zuzuordnen. Ein blockierter MAC-Callback wird nicht einem späteren Paket zugeschrieben.

Die Firmware enthält keine HTTP- oder WebSocket-Server. Auf dem Master übergibt die Messsteuerung aggregierte JSON-Meldungen an eine begrenzte 16-Einträge-Ausgabequeue; ein eigener Task schreibt in den UART-TX-Puffer. Dadurch wartet der Messablauf nicht auf die serielle Übertragung. Bei übervoller Ausgabequeue können wiederholte Status-/Abschlussberichte entfallen; unbestätigte Steuerbefehle werden vom PC wiederholt. Das PC-Backend besitzt genau einen Transport (Hardware oder ausdrücklich gewählte Simulation), eine ID-basierte Geräteverwaltung und eine Versuchsauswertung. FastAPI liefert lokale statische Dateien und Zustands-Snapshots per WebSocket. Ein langsamer Browser besitzt nur einen gepufferten Snapshot; neue Daten ersetzen veraltete, statt unbeschränkt Speicher zu belegen.

Knotenstatus altert nach 4 s. Endberichte werden wiederholt über Funk übertragen; eine einmal verlorene Meldung verursacht deshalb keinen künstlichen endgültigen Verlust. Das Backend archiviert vollständige und unvollständige abgeschlossene Versuche mit Konfiguration, Rohzählern und abgeleiteten Werten. Die letzten 30 Archivdateien werden beim Neustart wieder eingelesen.

## Funkformat, Version 1

Alle Mehrbytezahlen sind little endian. Der Aufbau ist in `firmware/main/protocol.h` definiert und mit Größenasserts gesichert. ESP-NOW-Unicast verwendet höchstens 250 Byte: 32 Byte Laborheader und höchstens 218 Byte Body. Das Format enthält weder Zeiger noch C-Enums variabler Größe.

| Byteoffset | Typ | Inhalt |
|---|---|---|
| 0 | uint16 | Magic `0x4c46` |
| 2 | uint8 | Protokollversion `1` |
| 3 | uint8 | Paketart |
| 4 | uint16 | Quellknoten-ID |
| 6 | uint16 | Zielknoten-ID |
| 8 | uint32 | Test-ID; 0 für Verwaltung |
| 12 | uint32 | Sequenznummer innerhalb eines Tests |
| 16 | uint64 | Senderzeit in µs; Echo übernimmt sie unverändert |
| 24 | uint16 | Bodylänge |
| 26 | uint16 | Flags, Bit 0 fordert Echo an |
| 28 | uint32 | Verstrichene Senderzeit in ms seit Teststart |
| 32 | Bytefolge | Body |

Paketarten: `1 CONTROL`, `2 CONTROL_ACK`, `3 STATUS`, `4 STATS`, `5 DATA`, `6 ECHO`. DATA enthält ausschließlich die lokal erzeugten Nutzdaten; ECHO hat keinen Body. Testdaten, Konfiguration und Status sind damit getrennte Nachrichtenklassen.

`command_t` (32 Byte) enthält in Reihenfolge: `id`, `transaction`, `test_id` (je uint32), `source`, `destination`, `payload_bytes`, `rate_pps` (je uint16), `duration_ms`, `lease_ms` (je uint32), `power_qdbm` (int8), `profile`, `op`, `reserved` (je uint8). Profile sind die Indizes der Tabelle in `radio.c`. Operationen: 1 configure, 2 commit, 3 rollback, 4 arm, 5 run, 6 stop. Nicht benötigte Felder bleiben 0.

`control_ack_t` (8 Byte) enthält uint32-ID, uint8-Operation, uint8-ok und uint16-Fehlercode. Die letzten 32 Befehlsbestätigungen pro Gerät werden zwischengespeichert; Wiederholungen derselben ID/Operation führen nicht erneut zur Anwendung oder zu einem Zählerreset.

`node_status_t` (50 Byte): acht uint32-Felder (`uptime_ms`, `boot_id`, `tx_total`, `rx_total`, `peer_age_ms`, `transaction`, `queue_drops`, `seen_peer_transaction`), zwei uint16-Felder (`peer_id`, `powers_mask`), fünf uint8-Felder (`role`, `profile`, `channel`, `bandwidth_mhz`, `profiles_mask`), int8 `power_qdbm`, uint8 `link_healthy`, uint8 `provisional`, sechs MAC-Bytes. Rolle 1 ist Master. Masken verwenden die Tabellenindizes in `radio.c`. `seen_peer_transaction` nennt die im letzten Peerstatus empfangene Konfigurations-ID und ermöglicht einen kausalen Rückwegnachweis.

`stats_t` (77 Byte): dreizehn uint32-Zähler in der Headerreihenfolge (`test_id`, `tx`, `rx_unique`, `duplicates`, `late`, `mac_ok`, `mac_fail`, `send_errors`, `app_acks`, `rtt_count`, `rssi_count`, `elapsed_ms`, `queue_drops`), uint64 `rtt_sum_us`, uint64 `jitter_sum_us`, int64 `rssi_sum`, uint8 `done`. Empfangsknoten übertragen ihre eigenen Zähler, nicht aus fehlenden Antworten abgeleitete Ziel-RX.

Der Empfangsadapter prüft Magic, Version, Framegröße, Bodylänge, lokale/entfernte Knoten-ID und die konfigurierte Peer-STA-MAC. Es gibt keinen Broadcast und kein Routing. Die MAC-Freigabe allein ist keine kryptografische Authentifizierung.

## Serielles Protokoll

115200 Baud, 8N1, UART0; UTF-8-/ASCII-JSON-Objekte, genau ein Objekt pro LF-terminierter Zeile. Boottexte und nicht passende Zeilen werden ignoriert. Maximal 511 Befehlsbytes vor LF am Master, maximal 4096 empfangene Byte pro Zeile am PC. Überlange Zeilen werden vollständig bis zum nächsten LF verworfen. Jede gültige Nachricht enthält `v: 1`.

PC → Gateway, Beispiele:

```json
{"v":1,"id":101,"node_id":2,"op":"configure","power_qdbm":44,"profile":"ofdm12","lease_ms":15000}
{"v":1,"id":102,"node_id":2,"op":"commit","transaction":101}
{"v":1,"id":103,"node_id":2,"op":"rollback","transaction":101}
{"v":1,"id":104,"node_id":2,"op":"arm","test_id":555,"source":1,"destination":2,"payload_bytes":128,"rate_pps":50,"duration_ms":20000}
{"v":1,"id":105,"node_id":1,"op":"run","test_id":555}
{"v":1,"id":106,"node_id":1,"op":"stop","test_id":555}
```

`id` ist eine nichtnull uint32-Befehls-ID; `test_id` identifiziert einen Versuch. Für einen realen Start muss zuerst das Ziel und anschließend auch der Sender per `arm` vorbereitet werden. Der Master übersetzt JSON in `command_t`, führt lokale Befehle selbst aus und leitet entfernte an genau den freigegebenen Peer weiter. Er bestätigt einen Slavebefehl erst, wenn die **Anwendungsbestätigung des Slaves** eingetroffen ist.

Gateway → PC:

```json
{"v":1,"type":"ack","id":101,"node_id":2,"op":"configure","ok":true}
{"v":1,"type":"stats","node_id":2,"test_id":555,"tx":0,"rx_unique":990,"duplicates":0,"late":0,"mac_ok":0,"mac_fail":0,"send_errors":0,"app_acks":0,"rtt_count":0,"rtt_sum_us":0,"jitter_sum_us":0,"rssi_count":990,"rssi_sum":-59400,"elapsed_ms":20000,"queue_drops":0,"done":true}
```

`status` enthält mindestens `node_id`, `mac`, `role`, `chip`, `idf`, `power_qdbm`, `profile`, `powers_qdbm`, `profiles`, `channel`, `bandwidth_mhz`, `tx_total`, `rx_total`, `peer_id`, `boot_id`, `transaction`, `provisional`, `link_healthy`. Die Gateway-Übersetzung behält die ursprüngliche Knoten-ID bei. Der PC versieht Statusmeldungen mit Empfangszeit in UTC; der Browser stellt sie in lokaler Zeit dar. `warning` enthält zusätzlich `message`.

Die Queue-Drop-Zähler sind seit dem Gerätestart kumulativ. `tx_total` und `rx_total` zählen ausschließlich Testdaten und bleiben über mehrere Versuche erhalten, bis das Gerät neu startet. Versuchszähler werden nur beim neuen `arm` zurückgesetzt.

## Konfigurationsbestätigung und Rückkehr

1. Das Backend prüft Onlinezustand, erlaubte Leistungsstufe und gemeinsame Profilfähigkeiten. Während eines Versuchs sind Konfigurationsänderungen gesperrt. Bei einer globalen Profiländerung müssen alle bekannten Geräte online sein.
2. `configure` speichert auf dem betroffenen Gerät den bisherigen Wert, wendet die neue Einstellung an und liest die Leistung zurück. Eine 15-s-Lease beginnt. Die sofortige ACK bestätigt die Anwendung, noch nicht die Funkqualität.
3. Geräte senden sekündliche Statuspakete. `link_healthy` verlangt aktuelle Peerpakete und einen aktuellen Peerstatus, der seinerseits Empfang vom anderen Gerät bestätigt. Während der Lease muss der Peer außerdem über `seen_peer_transaction` den Empfang der **neuen** Konfigurations-ID zurückgemeldet haben. Vor der Änderung empfangene Heartbeats reichen nicht aus. Das Backend wartet auf neue passende Statuswerte mindestens 1.5 s nach Änderungsbeginn und auf bestätigte Erreichbarkeit. Dafür gelten maximal weitere 6 s.
4. Erst danach folgt `commit` je betroffenem Gerät mit eigener Anwendungs-ACK. Die UI zeigt Erfolg erst nach allen Bestätigungen. Jeder Befehl wird bis zu viermal mit derselben ID gesendet, mit 700 ms Wartezeit pro Versuch.
5. Bei Fehlern fordert der PC `rollback` für alle betroffenen Geräte an. Unbestätigte Gerätekonfigurationen kehren nach 15 s selbstständig zurück, auch ohne PC oder USB. Beim Neustart gilt die sichere Startkonfiguration (18 dBm, OFDM 6 Mbit/s). Konfigurationen werden im ersten Meilenstein nicht dauerhaft in NVS gespeichert.

Ein verteilter Commit kann bei abruptem Ausfall nach einer einzelnen Commit-ACK teilweise abgeschlossen sein. Deshalb behält ein Gerät nach Commit die vorherige Konfiguration für einen expliziten Rollback, bis eine neue Änderung sie ersetzt. Ausbleibende Commit-ACKs ergeben Fehler und Rollback-Anforderung. Bereits bestätigte Geräte haben keine weiterhin laufende Lease. Nach einem PC-Ausfall genau im Commit-Zeitfenster können deshalb vorübergehend unterschiedliche TX-Profile bestehen; diese setzen nur die Senderate und verhindern den Empfang anderer aktivierter b/g/n-Raten nicht grundsätzlich. Bei problematischer Erreichbarkeit beide Geräte neu starten oder per PC zurückkonfigurieren. Dies ist kein konsensbasiertes Mesh-Konfigurationsverfahren.

## HTTP und WebSocket

FastAPI bindet per CLI an `127.0.0.1:8000`; OpenAPI unter `/docs`.

| Methode / Pfad | Zweck |
|---|---|
| `GET /api/state` | Vollständiger Browserzustand |
| `GET /api/ports` | Verfügbare Ports ohne Öffnen eines Geräts |
| `POST /api/connect` | `{"port":"COM6"}` |
| `POST /api/disconnect` | Verbindung schließen; nur außerhalb aktiver Vorgänge |
| `POST /api/configure` | `{"powers":{"1":44},"profile":"ofdm12"}`; beide Felder optional, mindestens eine Änderung |
| `POST /api/tests` | `{"source":1,"destination":2,"payload_bytes":128,"rate_pps":50,"duration_s":20}` |
| `POST /api/tests/{id}/stop` | Senden stoppen, Abschlussberichte abwarten |
| `GET /api/tests/{id}/export` | JSON mit Plan, Mode, Gerätekonfiguration, Rohberichten, Samples, Metriken |
| `WS /ws` | Server sendet `{"type":"state","data":...}` alle 500 ms |

POSTs mit fremdem Browser-Origin werden abgelehnt. Fehler liefern `detail` und HTTP 409 für Zustands-/Fähigkeitskonflikte, 422 für ungültige Eingaben oder 503 für Transport-/Bestätigungsausfälle. Konfigurationsänderungen liefern einen Statusdatensatz (`pending`, `success`, `failed`); endgültiger Konfigurationsfehler kann somit als reguläre Antwort mit `state: failed` erscheinen. Die UI erhält den ausstehenden Zustand parallel über WebSocket.

`state` enthält `mode` (`disconnected`, `hardware`, `simulation`), `nodes[]`, `edges[]`, gemeinsame `profiles[]`, `changes[]`, `runs[]`, `active` und `events[]`. Testzustände: `arming`, `running`, `draining`, `complete`, `incomplete`, `failed`, `invalid`. `metrics.provisional` und `metrics.consistency` kennzeichnen die Aussagekraft. Nicht vorhandene Messwerte sind JSON `null`.

Die Simulation verwendet denselben Befehls-/Telemetrievertrag. Ihr `mode: simulation` wird sowohl im Browser als auch in jedem Versuchsexport gespeichert. Sie prüft keine Funk-, Treiber- oder HF-Eigenschaften.

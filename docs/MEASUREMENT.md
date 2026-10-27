# Messmethodik und Hardwarefähigkeiten

## Festgelegte Plattform

Vom Nutzer bestätigt: **ESP32-WROOM-32**. Verwendeter Build-Target: `esp32`. Festgelegte und lokal verfügbare ESP-IDF-Version: **6.0.1**. Fremde Targets/Versionen scheitern explizit an der Build-Prüfung. Der Treiber setzt Station-Modus, 802.11b/g/n-Empfang, HT20, deaktivierten Wi-Fi-Stromsparmodus und den gemeinsamen Kanal aus `menuconfig` (Standard 6). Es findet keine Verbindung mit einem Access Point statt.

Die Mittenfrequenz wird für die erlaubten Kanäle 1–11 mit `2407 + 5 × Kanal` MHz berechnet. Die angezeigten 20 MHz sind die konfigurierte Kanalbandbreite und keine Spektrummessung.

### Maximale Sendeleistung

`esp_wifi_set_max_tx_power()` verwendet Viertel-dBm. Die dokumentierten kanonischen API-Werte sind `8, 20, 28, 34, 44, 52, 56, 60, 66, 72, 80`, entsprechend `2, 5, 7, 8.5, 11, 13, 14, 15, 16.5, 18, 20 dBm`. Die Firmware versucht beim Start jede Stufe, liest sie mit `esp_wifi_get_max_tx_power()` zurück und veröffentlicht nur exakt angenommene Werte. Anschließend setzt sie wieder 18 dBm. Jede Laufzeitänderung wird ebenfalls zurückgelesen.

Dies ist eine **konfigurierte Leistungsobergrenze**. PHY-Kalibrierung, konkrete Datenrate, Versorgung, Modul und regulatorische Vorgaben können die tatsächliche Funkleistung weiter begrenzen. Eine API-Rücklesung ist keine HF-Leistungsmessung.

Quelle: [ESP-IDF 6.0.1 Wi-Fi API](https://docs.espressif.com/projects/esp-idf/en/v6.0.1/esp32/api-reference/network/esp_wifi.html#_CPPv425esp_wifi_set_max_tx_power6int8_t).

### Angebotene PHY-Profile

| Kennung | Modus | Modulation | Coderate | Nominelle PHY-Rate |
|---|---|---|---|---|
| `ofdm6` | 802.11g OFDM, 20 MHz | BPSK | 1/2 | 6 Mbit/s |
| `ofdm12` | 802.11g OFDM, 20 MHz | QPSK | 1/2 | 12 Mbit/s |
| `ofdm24` | 802.11g OFDM, 20 MHz | 16-QAM | 1/2 | 24 Mbit/s |
| `ofdm54` | 802.11g OFDM, 20 MHz | 64-QAM | 3/4 | 54 Mbit/s |
| `ht_mcs0` | 802.11n HT20, ein Spatial Stream | BPSK | 1/2 | 6.5 Mbit/s |
| `ht_mcs7` | 802.11n HT20, ein Spatial Stream | 64-QAM | 5/6 | 65 Mbit/s |

HT verwendet GI 800 ns. Die Firmware setzt `esp_now_set_peer_rate_config()` nach Wi-Fi-/ESP-NOW-Initialisierung und Peer-Anlage. Sie probiert ausschließlich diese dokumentierten Raten mit passendem PHY-Modus aus und veröffentlicht nur erfolgreiche API-Aufrufe. Die Browserauswahl zeigt die Schnittmenge aller bekannten Knoten; das Anwenden eines gemeinsamen Profils erfordert alle bekannten Knoten online. Es werden keine HE-, Wi-Fi-6-, LoRa- oder frei erfundenen Modulationsoptionen angeboten.

Quellen: [ESP32 Wi-Fi Guide](https://docs.espressif.com/projects/esp-idf/en/v6.0.1/esp32/api-guides/wifi.html), [PHY-Enums und Rate-Tabelle](https://github.com/espressif/esp-idf/blob/v6.0.1/components/esp_wifi/include/esp_wifi_types_generic.h), [Peer-Rate-API](https://docs.espressif.com/projects/esp-idf/en/v6.0.1/esp32/api-reference/network/esp_now.html). Tatsächliche Senderaten und Reichweite sind noch mit Hardware zu prüfen.

## Versuch und Messfenster

- Ein aktiver Versuch, genau eine Datenrichtung, zufällige eindeutige uint32-Test-ID. Empfänger wird vor dem Sender vorbereitet. Start erfolgt erst nach Anwendungsbestätigungen beider `arm`-Befehle.
- 1–218 Nutzdatenbyte, 1–500 Sollpakete/s, 1–120 s; höchstens 60000 Pakete. Der 32-Byte-Laborheader zählt nicht zum Goodput. Die Nutzdaten werden auf dem ESP32 erzeugt, nicht seriell angeliefert.
- TX zählt ausschließlich Datenpakete, die `esp_now_send()` mit `ESP_OK` angenommen hat. Sofortige API-Fehler zählen separat. Sequenznummern beginnen bei 0 und werden nur bei Annahme erhöht. Kein Aufholburst nach Verarbeitungsverzögerungen.
- Der Sender misst seine aktive Sendedauer mit `esp_timer_get_time()`. Das Ende ist bei natürlichem Ablauf die angeforderte Dauer, bei Stopp die verstrichene Dauer, auf Millisekunden aufgerundet. Timer und Zeitstempel sind lokal; es wird keine Uhrensynchronität zwischen Geräten angenommen.
- Jede Nachricht trägt ihre Test-ID, Sequenz, Senderzeit und die verstrichenen Sendemillisekunden. Am Ziel zählt jede Sequenz genau einmal mittels 60000-Bit-Bitmap. Duplikate beeinflussen weder Goodput noch RSSI-Summe. Außerhalb des Messfensters oder nach Abschluss eingehende Pakete zählen als verspätet; fremde Test-IDs werden ignoriert.
- Nach Sendeende wartet der Sender 1.5 s auf Antworten und sendet dann wiederholt finale aggregierte Zähler. Der Empfänger wartet nach dem ersten finalen Senderbericht weitere 1.5 s; späte, zum Sendefenster gehörige Daten dürfen bis dahin eintreffen. Die Drainzeiten zählen nicht zur Goodput-Messdauer.
- Die Geräte berichten etwa einmal pro Sekunde kumulative Summen. Beide Abschlussberichte sind erforderlich. Fehlen sie nach Solltestdauer + 12 s (bzw. Stopp + 12 s), wird der Versuch unvollständig; der Endverlust bleibt unbekannt. Geräte sind nach 4 s ohne Status offline.
- Alle Status-, Steuer- und Antwortpakete belasten denselben Funkkanal. Gemessen wird der Goodput dieses Laborprotokolls einschließlich dieses Einflusses, kein isoliertes PHY-Maximum. RX-Queue-Überläufe werden separat angezeigt; sie sind lokale Verarbeitungsverluste und dürfen nicht als reine Funkverluste interpretiert werden.

### Definitionen

`Goodput [bit/s] = eindeutige Ziel-RX × Nutzdatenbyte × 8 / aktive Sendedauer [s]`.

`Paketzustellrate [%] = eindeutige Ziel-RX / TX × 100` und `Paketverlust [%] = (TX − eindeutige Ziel-RX) / TX × 100`. Bei TX = 0 sind beide undefiniert. 0 eindeutige RX in einem vorhandenen finalen Zielbericht bei TX > 0 ergeben 100 % Verlust. Ein **fehlender** Zielbericht ergibt keinen Verlustwert.

Laufende kumulative Berichte sind zeitlich nicht exakt synchron. Der Browser kennzeichnet deren Verlust als vorläufig. Bei RX > TX werden Goodput und Verlust unterdrückt, bis die Senderdaten nachgezogen haben; ein solcher Widerspruch in finalen Berichten macht den Versuch ungültig. Zeitverläufe zeigen kumulative Werte ab Versuchsbeginn, keine angeblich synchronen Intervallverluste. Beide Gerätedatensätze und die Samples werden exportiert.

Jedes zehnte Datenpaket (`seq % 10 == 0`) fordert eine Echoantwort an. Das Ziel übernimmt Test-ID, Sequenz und Senderzeit unverändert. `RTT = Empfangszeit der Antwort am ursprünglichen Sender − ursprüngliche Senderzeit`, gemessen mit derselben Uhr. Einmalige Echoantworten zählen als Anwendungsantworten. Nur Antworten binnen 1 s ergeben eine RTT-Stichprobe. Reihenfolge für Jitter ist die Empfangsreihenfolge am Sender:

`Jitter [ms] = Σ |RTT[i] − RTT[i−1]| / (n−1)`, für n ≥ 2. Bei weniger als zwei RTTs bleibt Jitter unbekannt. RTT ist der arithmetische Mittelwert der gültigen Stichproben. Es wird keine Einweglatenz behauptet. Softwarequeue und MAC-Wartezeiten sind Bestandteil der RTT; der RX-Zeitpunkt wird bereits im Empfangscallback erfasst.

RSSI ist das arithmetische Mittel der `rx_ctrl->rssi`-Metadaten eindeutiger Datenpakete am Ziel. Es beschreibt ausschließlich die gewählte Datenrichtung. Echo- oder Status-RSSI wird nicht als Daten-RSSI ausgegeben.

### Drei verschiedene Nachweise

1. `mac_ok` / `mac_fail`: Sendecallback des lokalen ESP-NOW-Treibers für Testdaten. Ein ausstehender bzw. zu später Callback kann eine Differenz `TX − mac_ok − mac_fail` hinterlassen; die Differenz darf nicht als Zielverlust gewertet werden.
2. `rx_unique`: eindeutige Testdaten am Ziel, unabhängig von Antworten und MAC-Berichten.
3. `app_acks`: eindeutige Echoantworten am ursprünglichen Sender; nur für jeden zehnten Sequenzwert angefordert. `rtt_count` kann wegen Timeouts kleiner sein.

Ein fehlendes Echo kann am Hinweg, am Rückweg oder durch lokale Verarbeitung scheitern und beweist allein keinen Datenverlust auf dem Hinweg.

## BER und Radar

Die normale ESP-NOW-Empfangsschnittstelle liefert erfolgreich dekodierte Nutzdaten und Metadaten, keinen vollständigen Bitstrom fehlerhafter Übertragungen. Dadurch fehlen die beschädigten bzw. nicht dekodierbaren Pakete als Grundlage einer Funk-BER. Ein Bitvergleich zugestellter Payloads wäre nur eine bedingte Anwendungsprüfung. **Funk-BER ist mit diesem Aufbau nicht belastbar messbar.** Sie bleibt im API/Export `null`, im Browser „nicht messbar“, im Radar ohne Punkt. Es wird keine Bitfehlersimulation beigemischt.

Diese Schlussfolgerung ergibt sich aus den [ESP-NOW-Empfangsdaten und Callbacks](https://docs.espressif.com/projects/esp-idf/en/v6.0.1/esp32/api-reference/network/esp_now.html) sowie der fehlenden Bereitstellung fehlerhafter Empfangsbits. Paketverlust ist eine separate Messgröße.

Für alle verfügbaren Radarachsen gilt `100 × clamp(f(x), 0, 1)`:

| Achse | f(x) | 0 Punkte | 100 Punkte |
|---|---|---|---|
| Goodput | x / 100000 bit/s | 0 bit/s | ab 100 kbit/s |
| Paketverlust | 1 − x / 100 % | 100 % | 0 % |
| RTT | 1 − x / 100 ms | ab 100 ms | 0 ms |
| RTT-Jitter | 1 − x / 20 ms | ab 20 ms | 0 ms |
| RSSI | (x + 100 dBm) / 60 dB | bis −100 dBm | ab −40 dBm |
| BER | keine | keine Bewertung | keine Bewertung |

Referenzwerte sind feste Labor-Vergleichswerte, keine physikalischen Leistungsgrenzen. Höher bedeutet überall besser. Fehlende, nicht endliche oder undefinierte Werte bleiben `null`; die Diagramme verbinden Lücken nicht und füllen keine scheinbar vollständige Fläche. Rohwerte und Einheiten stehen neben den Diagrammen; Clips im Radar verändern die Rohdaten nicht.

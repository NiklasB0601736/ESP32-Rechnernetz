# Konzeptnotiz: zentral gesteuertes ESP32-Netz

**Stand: 17.11.2026 · Ideensammlung, keine Implementierungsspezifikation.**

Das bisherige Projekt soll perspektivisch durch den hier beschriebenen Ansatz ersetzt werden. Diese Datei hält zunächst nur die neue Idee fest. Ein Zurücksetzen, Überschreiben oder Umbauen des bestehenden Codes ist in diesem Schritt nicht vorgesehen. Die bisherigen Anleitungen beschreiben weiterhin den alten Zwei-Geräte-Aufbau.

Die Abschnitte **Vorgaben**, **eigene Interpretationen**, **Vorschläge** und **offene Punkte** sind bewusst getrennt. Interpretationen und Vorschläge sind noch keine beschlossenen Anforderungen.

## 1. Vorgaben aus der beschriebenen Idee

### Drei Komponenten

| Komponente | Aufgabe |
|---|---|
| **Frontend** | Einstellungen und Ereignisse vorgeben; das vom Backend gemeldete Netz grafisch darstellen. |
| **Backend** | Knotentabellen empfangen, zu einer gemeinsamen Struktur zusammenführen und anhand wählbarer Kriterien neue Routen bzw. Netzverbindungen berechnen. |
| **Netz** | Teilweise verbundene ESP32 mit einem Master; Nachbarn vermessen und Ergebnisse auch über mehrere Zwischenknoten zum Master weiterleiten. |

### Netz

- Das Netz besteht aus ESP32, die **nicht alle direkt miteinander verbunden** sind.
- Ein **Master** kommuniziert über die serielle Schnittstelle mit dem Backend.
- Jeder Knoten besitzt eine definierte Sendeleistung. Sie kann in der GUI festgelegt werden oder zufällig innerhalb eines vorgegebenen Bereichs schwanken.
- Jeder Knoten hat **höchstens N direkte Nachbarn**. Die Grenze ist eine Obergrenze; weniger Nachbarn sind zulässig.
- Die Knoten stellen ihre vorgesehenen Nachbarschaftsbeziehungen **auf Aufforderung des Masters** her.
- Bereits bei der Initialisierung kennen sie ihre vorgesehenen Partner und einen Weg zum Master, gegebenenfalls über andere Knoten.
- In einem definierten Zeitraum prüfen alle Knoten die Verbindungsqualität zu ihren Nachbarn, soweit dies technisch möglich ist.
- Jeder Knoten erstellt eine eigene Verbindungstabelle: eine mit seiner ID „signierte“ Liste von Tupeln **(Nachbarknoten, Verbindungsstärke, Latenz)**. Bedeutung von „signiert“, Einheit und Messverfahren sind noch offen.
- Knoten ohne direkte Master-Verbindung leiten ihre Tabellen über den bekannten Weg zum Master weiter.
- Der Master reicht die einzelnen JSON-Strukturen der Ursprungsknoten an das Backend weiter.
- Das Backend übermittelt dem Master seriell eine neue Routingtabelle. Format, Verteilung und Aktivierung werden noch ausgearbeitet.

### Backend

- Empfängt die den Ursprungsknoten zugeordneten Verbindungstabellen.
- Erstellt daraus eine einheitliche Netzstruktur und übermittelt diese an das Frontend.
- Speichert für die erste Testversion **zwei vollständige Topologien**, zwischen denen über das Frontend gewechselt werden kann. Später soll die Topologie anhand der Verbindungstabellen erstellt und anschließend **Dijkstra** für die Pfadberechnung eingesetzt werden.
- Berücksichtigt Kriterien, die im Frontend ausgewählt bzw. verändert werden können.

### Frontend

- Erlaubt die Eingabe von Ereignissen bzw. deren Simulation.
- Ermöglicht Einstellungen einzelner Knoten, insbesondere der Sendeleistung und ihres Zufallsbereichs.
- Ermöglicht die Vorgabe der Partneranzahl N.
- Zeigt das Netz anhand der vom Backend gelieferten Verbindungsstruktur grafisch an.
- Zeigt in der ersten Version **RTT, RSSI und Zustellquote** sowie Platzhalter für **Durchsatz und BER**. Später lassen sich Kriterien für die Topologieauswahl einstellen.
- Ermöglicht die Einstellung des Intervalls einer periodischen **Pilotsequenz zur geplanten BER-Erfassung**, beispielsweise einmal pro Sekunde. Das genaue BER-Messverfahren bleibt technisch zu prüfen.

### Ergaenzte Festlegungen aus der gemeinsamen Konzeptbesprechung

Die folgenden Punkte sind vom Nutzer bestaetigt und gelten als Anforderungen fuer die erste Testversion:

- **Nachbargrenze:** Jeder Knoten darf hoechstens **N direkte Nachbarn** haben. N ist eine Obergrenze, keine geforderte Mindest- oder Exaktzahl. Noch festzulegen ist, ob eine gerichtete Beziehung oder eine beidseitig bestaetigte Verbindung als ein Nachbar zaehlt; fuer die erste Version wird eine beidseitig bestaetigte Verbindung empfohlen.
- **Zwei vollständige Topologien:** Das Backend speichert zwei komplette Topologien mit den vorgesehenen Nachbarschaften. Das Frontend wählt die Zieltopologie; der Master verteilt sie an die Knoten. Gemeint sind zwei Netzstrukturen, zwischen denen gewechselt wird. Periodische Statusmeldungen erfassen die tatsächlich bestätigten Nachbarschaften. Solltopologie und beobachtete Topologie werden getrennt geführt.
- **Wiederverbindung:** Ein Knoten ohne Netzverbindung versucht wiederholt, mindestens einen anderen Knoten zu erreichen. Welche Kontakte dafür freigegeben sind und wann ein Ausfall angenommen wird, wird in Abschnitt J als Vorschlag präzisiert.
- **Sicherer Wechsel:** Eine neue Konfiguration wird erst aktiv, wenn die betroffenen Knoten sie erhalten und bestaetigt haben. Bei einem Fehler sollen alle Knoten auf die urspruengliche Netzkonfiguration zurueckfallen. Rueckfallfrist und Verhalten bei teilweise aktivierter Konfiguration muessen noch festgelegt werden.
- **Messwerte in Version 1:** Das Frontend stellt RTT, RSSI und Zustellquote dar. Durchsatz und BER erscheinen als ausdruecklich nicht verfuegbare Platzhalter, bis belastbare Messverfahren umgesetzt sind.
- **Pilotsequenz für BER:** Für die spätere BER-Erfassung soll periodisch eine bekannte Pilotsequenz gesendet werden. Das Intervall ist im Frontend variabel; **eine Sekunde** ist ein Beispielwert. Eine Pilotsequenz allein löst die Frage nach dem Zugriff auf fehlerhafte Empfangsbits noch nicht; siehe Abschnitt K.
- **Optimierung spaeter:** In einer spaeteren Ausbaustufe soll das Backend aus den Verbindungstabellen eine Topologie erstellen. Dijkstra ist danach fuer die Pfadberechnung vorgesehen; die Topologieauswahl ist ein eigener vorgelagerter Schritt.

**Klaerung zur Initialisierung:** Ja, gemeint ist ein festes Startnetz, das vor Beginn der Messungen bekannt ist. Die Knoten erhalten daraus ihre vorgesehenen Nachbarn und den Weg zum Master. Diese Startkonfiguration dient zugleich als Rueckfallkonfiguration. Eine dynamisch berechnete Topologie ersetzt sie erst nach erfolgreicher Verteilung und Bestaetigung.

## 2. Grafische Übersicht

![Übersicht der drei Komponenten und des Regelkreises](images/netzkonzept.svg)

Die Knotenanzahl und die gezeichneten Kanten sind nur ein Beispiel. Grün zeigt die Meldung einer Tabelle über einen Zwischenknoten zum Master. Die Grafik legt weder konkrete Partner noch eine feste Knotenzahl oder ein Funkprotokoll fest. Die Rückverteilung neuer Routen zeigt den beabsichtigten Ablauf; das zugehörige Protokoll ist noch offen.

## 3. Eigene Interpretationen und Herleitungen — noch nicht vereinbart

### Zentraler Regelkreis

**Interpretation:** Das System arbeitet in wiederkehrenden Runden:

1. **Initialisieren:** Vorgegebene Partner und erste Wege zum Master laden.
2. **Anfordern:** Master verteilt den Auftrag für eine Messrunde.
3. **Messen:** Knoten untersuchen ihre Nachbarschaft innerhalb des festgelegten Zeitraums.
4. **Melden:** Jeder Knoten sendet seine eigene Tabelle zum Master; dieser reicht sie weiter.
5. **Berechnen:** Backend aktualisiert den Graphen und berechnet anhand der GUI-Vorgaben neue Routen und gegebenenfalls Partner.
6. **Verteilen und aktivieren:** Backend sendet das Ergebnis zum Master; die betroffenen Knoten erhalten ihre Einstellungen.
7. **Wiederholen:** Nach Aktivierung folgt die nächste Messrunde.

**Herleitung:** Der bekannte Startweg löst das anfängliche Problem, dass Messberichte schon vor der ersten Optimierung zum Backend gelangen müssen. Nach einer Änderung muss dieser Steuerweg weiterhin nutzbar sein oder wiederhergestellt werden können.

### Drei unterschiedliche Arten von Beziehungen

**Interpretation:** Für ein eindeutiges Modell sind drei Ebenen nötig:

| Ebene | Bedeutung |
|---|---|
| **Hörbare bzw. messbare Nachbarn** | Knoten, von denen ein Gerät Funkpakete empfangen oder mit denen es Messungen durchführen kann. |
| **Erlaubte bzw. aktive Partner** | Die für den regulären Austausch freigegebenen Beziehungen; hier könnte die N-Grenze gelten. |
| **Routing** | Die Auswahl, über welchen aktiven Partner eine Nachricht ihr Ziel erreichen soll. |

**Herleitung:** Alle Nachbarn zu untersuchen und gleichzeitig nur N Partner zuzulassen ist nur dann eindeutig, wenn geklärt wird, ob Messkontakte ebenfalls als Partner zählen. Ein hörbarer Knoten muss nicht automatisch ein erlaubter Weiterleitungspartner sein.

### Herkunft bleibt beim Weiterleiten erhalten

**Interpretation:** Eine Tabelle von Knoten C bleibt eine Tabelle von C, auch wenn A und der Master sie weiterleiten. Ursprungsknoten und letzter Weiterleiter sind unterschiedliche Angaben. Die Zuordnung per ID ist noch keine kryptografische Signatur.

### Messrichtung und Konfiguration gehören zusammen

**Herleitung:** Eine Messung von A nach B beschreibt zunächst diese Richtung. Die Gegenrichtung wird gesondert erfasst. Außerdem muss bekannt sein, welche Sendeleistung während der Messung galt; bei zufälligen Änderungen wären Messwerte sonst schwer vergleichbar.

### Dijkstra braucht einen bereits definierten Graphen

**Technische Einordnung:** Dijkstra bestimmt Pfade mit der kleinsten Summe von Kantengewichten in einem vorhandenen Graphen. Für den vorgesehenen Ansatz müssen daraus nichtnegative Kosten entstehen. Negative RSSI-Werte dürfen nicht unverändert als Dijkstra-Kosten verwendet werden. Die [NetworkX-Dokumentation zu Dijkstra](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.shortest_paths.weighted.single_source_dijkstra.html) beschreibt die Pfadberechnung und ihre Gewichtung.

**Herleitung:** Die zusätzliche Aufgabe, aktive Partner unter einer N-Grenze auszuwählen und dabei die Erreichbarkeit des Masters zu erhalten, ist damit noch nicht definiert. „Bestes Netz“ braucht daher eine eigene Zielfunktion und eine Regel zur Auswahl der Kanten.

## 4. Vorschläge für die noch offenen Konzepte — nicht beschlossen

### A. Zunächst eine klare Grundvariante festlegen

**Vorschlag:** N zunächst als **maximale Zahl aktiver direkter Partner pro Knoten** behandeln. Ob der Master dieselbe Grenze hat, ausdrücklich festlegen. Weniger Partner sind zulässig, wenn die physische Nachbarschaft nichts anderes ermöglicht. Eine neue Konfiguration wird nur übernommen, wenn die geforderten Wege zum Master bestehen.

**Vorschlag:** Für den ersten Entwurf zunächst bekannte, erlaubte Verbindungen vermessen und darauf Routen berechnen. Eine zusätzliche Suche nach alternativen Partnern kann als eigener Schritt folgen. So bleiben Routing und Topologieauswahl unterscheidbar.

### B. Messrunden koordinieren

**Vorschlag:** Der Master vergibt eine Messrunden-ID, Messdauer und aufeinanderfolgende Sendezeiten. Alle Knoten arbeiten innerhalb derselben Runde, senden aber nicht gleichzeitig sämtliche Prüfpakete. Dadurch lassen sich gegenseitige Belastung und fehlende Antworten besser einordnen.

**Vorschlag:** Beim Messen die Sendeleistung kurz konstant halten. Zufällige Leistungsänderungen zwischen den Runden ausführen und zu jeder Runde speichern: Bereich, gewählter Konfigurationswert, Änderungsintervall und Zufalls-Seed. Nur von der Hardware unterstützte Stufen verwenden. Ein Zufallswert ist eine Leistungsänderung; er erzeugt kein zusätzliches Störsignal. Die [Espressif-API zur Sendeleistung](https://docs.espressif.com/projects/esp-idf/en/v6.0.1/esp32/api-reference/network/esp_wifi.html#_CPPv425esp_wifi_set_max_tx_power6int8_t) beschreibt die Konfiguration des bisherigen Hardwareansatzes.

### C. Begriffe und Messwerte präzisieren

| Größe | Vorschlag |
|---|---|
| **Verbindungsstärke** | RSSI empfangener Prüfpakete in **dBm**; dB für Differenzen bzw. Verhältnisse. Mittelwert und Stichprobenzahl je Richtung speichern. |
| **Latenz** | Zunächst RTT einer Anfrage mit Antwort messen. Eine echte Einweglatenz erfordert ein zusätzliches Zeit-/Synchronisationskonzept. RTT/2 nicht als gemessene Einweglatenz ausgeben. |
| **Zustellung** | Sendungen, eindeutige Ziel-Empfänge und Antworten getrennt zählen; fehlende Rückantwort nicht automatisch als Verlust des Hinwegs behandeln. |
| **Durchsatz** | Zunächst gerichteten Goodput messen: eindeutig empfangene Nutzdatenbits pro Messdauer. Messungen einzelner Verbindungen und des gesamten Mehrsprungpfads getrennt betrachten. |
| **BER** | Bis zu einem belastbaren Messkonzept als **nicht verfügbar** führen; nicht aus Paketverlust schätzen. Eine Bitfehlersimulation gegebenenfalls als gesonderte Simulation kennzeichnen. |

Falls ESP-NOW beibehalten wird, bestätigt dessen MAC-Sendestatus keinen sicheren Empfang in der Zielanwendung. Die Empfangsschnittstelle stellt auch keinen vollständigen Strom beschädigter Funkbits zur BER-Auswertung bereit. Daraus folgt für diesen Ansatz: Eine echte Funk-BER ist über diesen Empfangspfad nicht belastbar ableitbar. Grundlage: [ESP-NOW-Sende- und Empfangsschnittstellen](https://docs.espressif.com/projects/esp-idf/en/v6.0.1/esp32/api-reference/network/esp_now.html).

### D. Routingkosten und Topologieauswahl getrennt entwickeln

**Vorschlag für die erste Routingversion:** Latenz als einziges Pfadkriterium verwenden. Eine Mindest-RSSI-Bedingung kann unbrauchbare Kanten ausschließen. Anschließend Dijkstra auf dem zulässigen Graphen ausführen.

**Späterer Vorschlag:** Mehrere Kriterien zunächst auf vergleichbare, nichtnegative Kosten abbilden. Die GUI legt fest, ob ein Kriterium optimiert, nur als Mindestanforderung geprüft oder mit anderen gewichtet wird. Referenzwerte und Gewichte müssen sichtbar sein; fehlende Messwerte dürfen keine besonders guten Kosten erhalten.

**Offene Herleitung:** Der Engpass-Goodput eines Pfads ist keine Summe der Link-Goodputs. Auch „stärkster Pfad“ braucht eine Definition, etwa die Qualität der schwächsten Verbindung. Eine gewichtete Kostensumme wäre ein gewähltes Bewertungsmodell und kein Beweis für das global beste Netz. Dies gilt besonders bei zusätzlicher N-Grenze und gemeinsam genutztem Funkkanal.

**Vorschlag für die Graphenrichtung:** Für Knoten → Master und Master → Knoten getrennte Pfade berücksichtigen. Bei gerichteten Kanten kann die Sammlung von Wegen zum Master über eine Pfadberechnung vom Master im umgedrehten Graphen erfolgen. Der Rückweg folgt daraus nicht automatisch.

### E. Herkunft und Weiterleitung dokumentieren

**Vorschlag für einen späteren Bericht:** Mindestens `source_id`, `report_id`, `measurement_round`, Messzeitraum, Konfigurationsversion und Nachbarliste vorsehen. Je Nachbar Messrichtung, RSSI, RTT bzw. eindeutig benannte Latenzgröße, Stichprobenzahl und Erreichbarkeit angeben. Nicht erhobene Werte bleiben `null`; eine leere Liste ist von einem fehlenden Bericht zu unterscheiden.

**Vorschlag für Weiterleitung:** Ursprung und Inhalt erhalten; Weiterleitungsinformationen getrennt führen. Paket-ID, Duplikaterkennung und eine maximale Hopanzahl vorsehen. Bei Bedarf Nachrichten in kleinere Funkpakete zerlegen. Ob die ursprünglichen JSON-Strukturen bereits über Funk oder erst an der seriellen Schnittstelle erzeugt werden, bleibt eine Designentscheidung.

**Falls Authentizität verlangt wird:** Die ursprüngliche Meldung zusätzlich authentifizieren oder digital signieren. Die genaue Bedeutung von „signiert“ und die Schlüsselverwaltung müssen dann gesondert festgelegt werden.

### F. Neue Routen kontrolliert aktivieren

**Vorschlag:** Jede Topologiekonfiguration erhält eine Version. Der Master verteilt sie zunächst über die bisher funktionierenden Wege. Die Knoten bestätigen den Empfang; danach folgt eine definierte Aktivierung und die Prüfung der neuen Nachbarschaften und Masterpfade. Nach der bestätigten Anforderung ist das Rückfallziel die **ursprüngliche Starttopologie**. Das Rückfallverfahren und seine Fristen werden in Abschnitt J vorgeschlagen.

**Vorschlag:** Verbindungswerte über mehrere Runden glätten und eine Mindestverbesserung vor einem Wechsel verlangen. Dadurch kann verhindert werden, dass kleine Schwankungen ständig neue Routen auslösen. Fehlende bzw. zu alte Berichte erhalten einen eigenen Zustand; sie werden nicht als Messwert null interpretiert.

### G. Hardware- und Simulationsereignisse unterscheiden

**Vorschlag:** Die GUI benennt, ob ein Ereignis eine reale Änderung auslöst oder nur im Modell wirkt. Beispiele: unterstützte Sendeleistungsstufe setzen, Weiterleitung anhalten, eine Verbindung logisch sperren oder Paketverlust simulieren. Künstliche Verluste und künstliche Bitfehler bleiben im Ergebnis erkennbar.

### H. Geeignete Verfahren zur Topologieauswahl

**Einordnung:** Dijkstra loest die spaetere Pfadfrage innerhalb einer feststehenden Topologie. Fuer die Auswahl der Kanten bei einer Obergrenze N pro Knoten eignen sich mehrere Stufen:

1. **Erste Testversion - zwei gespeicherte Konfigurationen:** Die beiden festgelegten Topologien werden als versionierte Konfigurationen im Backend gespeichert und im Frontend auswaehlbar gemacht. Das ist reproduzierbar und erlaubt, Messung, Statusmeldung und sichere Aktivierung zu testen, bevor ein Optimierer hinzukommt.
2. **Einfacher automatischer Start - gewichteter Spannbaum mit Gradgrenze:** Fuer kleine Netze kann ein Minimum-Spanning-Tree-Ansatz eine zusammenhaengende Grundstruktur mit niedrigen Gesamtkosten liefern. Die Gradgrenze N muss dabei als Nebenbedingung eingehalten werden. Ein gewoehnlicher MST garantiert diese Grenze nicht; wenn keine zulaessige Loesung existiert, muss das Backend dies melden. Gradbegrenzte und ausfallsichere Topologieauswahl ist ein eigenes Optimierungsproblem, wie auch Arbeiten zu Funkmesh-Topologien mit Knotengradgrenzen zeigen ([Beispielstudie](https://doi.org/10.1177/1550147716668062)).
3. **Robustere Topologie - Redundanz als Nebenbedingung:** Falls ein einzelner Link- oder Knotenausfall das Netz nicht trennen soll, kann eine k-zusammenhaengende Topologie verlangt werden. Das braucht typischerweise mehr Nachbarschaften und kann bei kleinem N oder schlechter Funkreichweite unmoeglich sein.
4. **Mehrere Kriterien:** Fuer kleine Netze ist eine ganzzahlige Optimierung (z. B. ILP/CP-SAT) mit expliziten Variablen fuer ausgewaehlte Kanten, Gradgrenzen und Master-Erreichbarkeit gut nachvollziehbar. Fuer groessere Netze kann eine Heuristik Kanten schrittweise hinzufuegen oder tauschen und nach jedem Schritt Erreichbarkeit und N pruefen.

**Vorschlag fuer den spaeteren Optimierer:** Zuerst Bedingungen pruefen (Master-Erreichbarkeit, N, Mindest-RSSI, bestaetigte Kanten); danach unter den zulaessigen Topologien ein klares Ziel minimieren. Bei mehreren Zielen sind lexikografische Prioritaeten oft verstaendlicher als undokumentierte Gewichte: etwa zuerst alle Knoten anbinden, dann maximale RTT minimieren, danach Zustellquote verbessern. Gewichtete Summen brauchen Normalisierung und im Frontend sichtbare Gewichte.

Kein Verfahren kann eine Verbindung garantieren, wenn die Kandidatenkanten keine Topologie mit den Anforderungen zulassen. Das Backend sollte dann "keine zulaessige Topologie" samt verletzter Bedingung ausgeben.

### I. Erfassungsverfahren fuer spaetere Messgroessen

| Messgroesse | Verfahren | Darstellung und Grenze |
|---|---|---|
| **RTT** | Anfrage mit Sequenznummer senden; Empfaenger antwortet mit derselben Nummer; Zeit am Initiator messen. Fehlende Antwort nach Timeout als fehlgeschlagenen Versuch zaehlen. Pro Richtung und Messrunde mehrere Proben erfassen. | Median und optional p95 in ms; Probenzahl und Timeout-/Erfolgszahl. RTT enthaelt Funk-, Warteschlangen- und Antwortzeit und ist keine Einweglatenz. |
| **RSSI** | Empfangender Knoten liest den RSSI fuer jedes zuordenbare Pruefpaket und meldet ihn mit Sender-ID, Runde und Richtung. | dBm pro Empfangsrichtung; Median oder Mittelwert plus Stichprobenzahl und Streuung. RSSI ist Empfangspegel, keine direkte Masszahl fuer Paketzuverlaessigkeit. |
| **Zustellquote** | Sender uebermittelt nummerierte Pruefdatagramme. Empfaenger zaehlt eindeutige Sequenznummern; Duplikate separat. | Eindeutig empfangene / erwartete Pakete in Prozent, je Richtung und Messrunde. Genau angeben, ob MAC-Bestaetigungen oder Anwendungsbestaetigungen gezaehlt werden. ESP-NOW-MAC-Sendeerfolg garantiert keinen Empfang in der Zielanwendung. |
| **Durchsatz (Platzhalter)** | Spaeter nummerierte Nutzdatenpakete mit definierter Paketgroesse und Senderate ueber ein festes Zeitfenster senden. Am Empfaenger nur eindeutige, vollstaendige Nutzdaten zaehlen. | Zunaechst Goodput in bit/s: Nutzdatenbits am Ziel / Messdauer. Link-Goodput und Ende-zu-Ende-Goodput getrennt ausweisen; die Messlast beeinflusst das Funknetz. |
| **BER (Platzhalter)** | Periodische bekannte Pilotsequenz; Intervall im Frontend einstellbar, z. B. 1 s. Vergleich von erwarteter und empfangener Bitfolge auf einer ausdrücklich definierten Empfangsebene. | Fehlerhafte Bits / verglichene Bits samt Stichprobenumfang und Empfangsebene. Eine Funk-BER vor Fehlerkorrektur erfordert Zugriff auf die entsprechenden Bits. Der normale ESP-NOW-Anwendungsempfang liefert dafür keinen vollständigen fehlerhaften Bitstrom. Ausgefallene Pilotpakete werden separat als Verluste erfasst; siehe Abschnitt K. |

**Messrunden:** Alle Knoten sollten eine gemeinsame Runden-ID, Paketgroesse, Zahl der Pruefpakete und ein Zeitfenster erhalten. Sendeleistung und Topologiekonfiguration bleiben waehrend einer Runde konstant. Protokolliert werden Konfigurationsversion, Zeitpunkt, Richtung, Stichproben und fehlende oder abgelaufene Berichte.

**Quellenhinweise zu den Messverfahren:** ESP-NOW unterscheidet den MAC-Sendebericht von der Zustellung an die Anwendung und empfiehlt bei Bedarf ACKs und Sequenznummern ([ESP-IDF ESP-NOW-Dokumentation](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/network/esp_now.html)). Goodput zaehlt nuetzliche, am Ziel angekommene Daten und schliesst verlorene oder erneut gesendete Bits aus ([RFC 8238](https://www.rfc-editor.org/rfc/rfc8238.html)). Eine direkte BER-Messung setzt einen bekannten bzw. vergleichbaren Bitstrom voraus; die Anforderungen einer indirekten Schaetzung muessen als Annahmen dokumentiert werden ([ETSI EN 300 674-2-1, Anhang B.4.5](https://portal.etsi.org/Portals/0/TBpages/edithelp/Docs/Compared_versions/300500_300999/3006740201/EN%20300%20674-2-1v311_compared%20with%20previous%20version.pdf)).


### J. Wiederverbindung und Freigaberegel — Vorschlag, noch nicht beschlossen

**Begriff:** Bei einem möglichen ESP-NOW-Einsatz ist eine Verbindung eine von der Anwendung verwaltete und bestätigte Nachbarschaft. ESP-NOW selbst arbeitet verbindungslos. Wiederverbindung bedeutet hier, diese Nachbarschaft durch erneute Kontaktaufnahme und Bestätigung wieder als nutzbar einzustufen.

| Anlass | Vorgeschlagenes Verhalten |
|---|---|
| **Start oder Neustart eines Knotens** | Vorgesehene Nachbarn der gültigen Konfiguration kontaktieren. Beim Kaltstart ohne gültige aktuelle Konfiguration die gespeicherte Starttopologie verwenden. |
| **Bestätigter Nachbar antwortet nicht mehr** | Nach mehreren fehlenden Lebenszeichen bzw. einer Ausfallfrist die Kante als ausgefallen markieren und Kontaktversuche wiederholen. Ein einzelner Paketverlust löst noch keinen Topologierückfall aus. |
| **Keine bestätigte Nachbarschaft mehr** | Mit wiederholten, zeitlich versetzten Versuchen mindestens einen freigegebenen Nachbarn erreichen. Der andere Knoten muss selbst noch Kapazität nach N haben. |
| **Nachbarn erreichbar, aber kein Weg zum Master** | Zustand als „lokal verbunden, Master nicht erreichbar“ melden, soweit möglich. Zusätzlich den Masterpfad prüfen und reparieren; eine lokale Verbindung allein beweist keine Netzanbindung. Nach Ablauf einer festgelegten Frist das Rückfallverfahren auslösen. |
| **Wechsel zwischen den beiden Topologien** | Neue Beziehungen gezielt aufbauen und bestätigen. Das ist ein geplanter Konfigurationswechsel. Scheitern Verteilung, Aufbau oder Prüfung innerhalb der Frist, auf die ursprüngliche Starttopologie zurückfallen. |

**Ausfallerkennung:** Nachbarschaften über periodische Lebenszeichen oder bestätigte Prüfnachrichten überwachen. Beispiel für eine spätere Parametrisierung: Prüfung jede Sekunde, Ausfall nach drei aufeinanderfolgenden unbeantworteten Prüfungen. Diese Werte sind Vorschläge. Lokale Prüfungen und die Bestätigung der Master-Erreichbarkeit brauchen getrennte Fristen. Ein beim Backend fehlender Statusbericht ist zunächst „veraltet/unbekannt“ und beweist allein keinen Nachbarausfall.

**Freigaberegel bedeutet:** In der ersten Version enthält jede vollständige Topologie pro Knoten eine Liste erlaubter Nachbarn. Eine aktive Beziehung A–B darf nur entstehen, wenn beide Knoten sie in derselben Konfigurationsversion freigegeben haben, beide die Kontaktaufnahme bestätigen und die Nachbargrenze N eingehalten wird. Gleichzeitig laufende Kontaktversuche müssen freie Plätze reservieren, damit N nicht versehentlich überschritten wird. Eine Wiederverbindung zu einem bereits freigegebenen Nachbarn benötigt keine neue Einzelentscheidung des Backends: Die gespeicherte Topologie erteilt dafür bereits die Erlaubnis. Ein hörbarer fremder Knoten wird durch den Empfang einer Nachricht nicht automatisch Partner.

**Beispiel:** In Topologie A darf Knoten C nur mit A und D verbunden sein. C verliert beide Kontakte und versucht A und D erneut. Ein hörbarer Knoten B ist dadurch noch kein zulässiger Partner. Die Beziehung C–B darf erst nach einer vom Master verteilten und bestätigten Konfiguration entstehen, die sie für beide Enden erlaubt. So bleibt die im Frontend gewählte Topologie nachvollziehbar. Eine spätere automatische Notfallfreigabe wäre eine zusätzliche Betriebsart mit eigener Regelung.

**Wiederholungsstrategie:** Versuche mit begrenzter wachsender Wartezeit und kleinem Zufallsversatz wiederholen; nach Erreichen der maximalen Wartezeit weiter versuchen. Ein isolierter Knoten darf auf die bereits gespeicherten Freigaben zugreifen, da er für eine neue Genehmigung das Backend gerade nicht erreicht. Kann keiner dieser Nachbarn erreicht werden, bleibt er als isoliert gekennzeichnet. Eine physisch unterbrochene Funkstrecke wird durch wiederholte Kontaktversuche oder das Laden einer Topologie nicht garantiert wiederhergestellt.

**Rückfall aller Knoten:** Die ursprüngliche Starttopologie muss auf jedem Knoten gespeichert und eindeutig als Rückfallziel bezeichnet sein. Der Master kann erreichbare Knoten zum Rückfall auffordern. Damit auch abgetrennte Knoten zurückfallen können, braucht es zusätzlich einen lokalen Mechanismus, etwa eine befristete Freigabe für den Betrieb außerhalb der Starttopologie. Der Master erneuert diese Freigabe nur, solange alle erforderlichen Knoten ihre Teilnahme bestätigen; bei einem anhaltenden Fehler endet die Erneuerung für alle. Beim Ablauf wechseln die Knoten selbstständig zur Starttopologie. Das ermöglicht einen Rückfall trotz unterbrochener Befehlswege; einen exakt gleichzeitigen Wechsel aller Geräte garantiert es nicht. Ausfallfrist, Gültigkeitsdauer und Wiederaufnahme nach dem Rückfall bleiben festzulegen.

**Noch offen:** Während eines Topologiewechsels dürfen alte und neue Nachbarschaften zusammen die Grenze N nicht ungeklärt überschreiten. Es braucht entweder eine ausdrücklich genehmigte Übergangsregel oder einen Ablauf, der alte Kanten gezielt abbaut und neue aufbaut. Der Aufbau einer Prüfnachbarschaft, ihre Bestätigung und die Freigabe zur regulären Weiterleitung sind dabei unterschiedliche Schritte.

### K. Periodische Pilotsequenz für die geplante BER-Erfassung

**Festlegung des Nutzers:** Eine bekannte Pilotsequenz wird periodisch gesendet. Das Sendeintervall lässt sich im Frontend einstellen, beispielsweise auf **1 Sekunde**. In der ersten Version bleibt die BER-Anzeige ein Platzhalter, solange kein belastbares Messverfahren verfügbar ist.

**Vorschlag für den Ablauf:** Jeder teilnehmende Sender überträgt die Sequenz an seine freigegebenen Nachbarn. Zu jeder Übertragung gehören Sender-ID, Sequenznummer, Konfigurationsversion sowie eine Kennung für Muster oder PRBS-Seed und Länge. Der Empfänger erzeugt dieselbe Referenzfolge, richtet sie anhand der Kennung aus und vergleicht die verfügbaren Empfangsbits. Unterschiedliche Bitpositionen werden gezählt; über das Auswertefenster gilt **BER = fehlerhafte verglichene Bits / insgesamt verglichene Bits**. Empfangsrichtung, Sequenzlänge, Anzahl der Piloten und Auswertefenster werden mitgemeldet. Bei null vergleichbaren Bits bleibt der Wert nicht verfügbar.

**Technische Grenze:** Eine bekannte Folge ist Voraussetzung für einen Bitvergleich, schafft aber keinen Zugriff auf Funkbits, die der Empfänger oder Treiber bereits verworfen bzw. korrigiert hat. Der normale ESP-NOW-Empfang stellt Anwendungsdaten bereit; daraus lässt sich keine vollständige Funk-BER vor Fehlerkorrektur ableiten. Ein Vergleich ausschließlich erfolgreich zugestellter Nutzdaten beschreibt nur diese ausgewählte Menge auf Anwendungsebene. Ein fehlendes Pilotpaket ist ein Paketverlust mit unbekannter Zahl fehlerhafter Bits; es darf weder als null Bitfehler noch als vollständig fehlerhafte Bitfolge gezählt werden. Die konkrete Empfangsebene und eine geeignete Schnittstelle bzw. zusätzliche Messtechnik müssen deshalb vor der BER-Implementierung festgelegt werden. Siehe [ESP-NOW-Empfangsschnittstelle](https://docs.espressif.com/projects/esp-idf/en/v6.0.1/esp32/api-reference/network/esp_now.html#receiving-esp-now-data).

**Zeitplanung:** Pilotintervall, Lebenszeichenintervall, Statusmeldeintervall und BER-Auswertefenster sind getrennte Einstellungen. Eine Änderung des Pilotintervalls im Frontend verändert daher nicht automatisch die Ausfallerkennung. Pilotpakete der Knoten sollten zeitlich versetzt werden; Musterlänge und Intervall bestimmen die zusätzliche Messlast. Bei einer Konfigurationsänderung werden alte und neue Messfenster getrennt ausgewertet.

## 5. Lücken und Unschlüssigkeiten, die vor der Umsetzung zu klären sind

| Punkt | Warum er noch offen ist |
|---|---|
| **Nachbargrenze N** | Höchstens N Nachbarn pro Knoten ist festgelegt. Noch offen sind die Zählweise gerichteter Kontakte, ein globaler oder individueller Grenzwert und eine mögliche Sonderregel für den Master. |
| **Erreichbarkeit bei kleinem N** | Manche Grenzen erlauben keine zusammenhängende Topologie. Bei gegenseitigen Verbindungen und maximal einem Partner pro Knoten lässt sich beispielsweise kein zusammenhängendes Netz mit mehr als zwei Knoten aufbauen. |
| **Alle Nachbarn messen, nur N Partner nutzen** | Es fehlt die Regel, ob Messkontakte außerhalb der aktiven Partner erlaubt sind und ob bislang unbekannte Nachbarn überhaupt entdeckt werden sollen. |
| **Starttopologie und Master-Auftrag** | Ein festes Startnetz ist vereinbart. Es braucht noch ein Verfahren, mit dem die Knoten dessen Nachbarschaften ohne bereits funktionierenden Masterpfad aufbauen und bestätigen. |
| **Routenänderung und N-Grenze** | Während eines Wechsels können alte und neue Partner zusammen mehr als N ergeben. Es fehlt die Entscheidung zwischen vorübergehender Ausnahme und einem Wechsel, der die Grenze durchgehend einhält. |
| **Vorgegebene Partner und spätere Optimierung** | Version 1 wechselt zwischen zwei vollständigen Topologien. Später soll das Backend Topologien aus Verbindungstabellen erzeugen. Die Freigabe von Messkontakten zu zusätzlichen Kandidaten bleibt zu entscheiden. |
| **„Bestes Netz“ und Dijkstra** | Offen sind Ziel, Kostenmodell und Nebenbedingungen: kürzeste Pfade, geringe Maximallatenz, hohe Erreichbarkeit, faire Lastverteilung oder etwas anderes. |
| **Rückweg vom Master** | Ein funktionierender Berichtsweg zum Master garantiert keine erfolgreiche Verteilung von Befehlen in Gegenrichtung. Beide Richtungen müssen berücksichtigt werden. |
| **Verbindungsstärke „in dB“** | RSSI, Dämpfung und ein selbst definierter Qualitätswert sind verschiedene Größen. Bezeichnung, Einheit und Messrichtung fehlen. |
| **„Mit ID signiert“** | Eine Herkunftsangabe und eine kryptografische Signatur erfüllen unterschiedliche Aufgaben. Die gewünschte Bedeutung ist noch nicht festgelegt. |
| **RTT-Auswertung** | RTT ist festgelegt. Noch offen sind Paketgröße, Timeout, Stichprobenumfang und die getrennte Anzeige direkter Nachbar-RTT und der RTT zum Master über mehrere Sprünge. |
| **Zufällige Leistung** | Bereich, unterstützte Stufen, Verteilung, zeitlicher Verlauf und Verhalten während einer Messrunde fehlen. Außerdem ist offen, ob der Master ebenfalls schwanken darf. |
| **Durchsatz und BER** | Periodische Pilotsequenz mit im Frontend variablem Intervall ist für BER festgehalten. Empfangsebene, Zugriff auf fehlerhafte Bits, Sequenzlänge und Auswertefenster bleiben offen. Durchsatzmessung und spätere Pfadbewertung sind ebenfalls zu konkretisieren. |
| **Wiederverbindung und Freigabe** | Abschnitt J schlägt die Beschränkung auf Nachbarn der gültigen Topologie vor. Ausfallfristen, Wiederholungszeiten und der Umgang mit Masterverlust bei noch bestehenden lokalen Kontakten müssen beschlossen werden. |
| **Rückfall aller Knoten** | Die ursprüngliche Starttopologie ist das vereinbarte Ziel. Lokale Fristen bzw. befristete Freigaben sind nötig, damit auch abgetrennte Knoten zurückfallen. Exakte Gleichzeitigkeit und physische Wiederherstellung sind dadurch nicht garantiert. |
| **Ausfall und veraltete Tabellen** | Wiederholungen, Fristen, Teilberichte, Neustarts, Netztrennung und Rückkehr zum Ausgangszustand brauchen Regeln. |
| **Routingtabellen verteilen** | Unklar sind Format, Zustellweg, Bestätigungen und das Verhalten bei teilweise empfangenen bzw. aktivierten Versionen. |
| **Funkprotokoll und „Scan“** | Die neue Idee legt das Funkverfahren noch nicht fest. Ein WLAN-AP-Scan und die Suche nach anwendungseigenen ESP32-Nachbarn sind unterschiedliche Vorgänge. |

**Einordnung für einen möglichen ESP-NOW-Ansatz:** ESP-NOW arbeitet verbindungslos; „verbinden“ müsste hier als Verwaltung zugelassener Partner und Nachrichtenwege definiert werden. Eine logische Partnersperre begrenzt nicht die physische Hörbarkeit des Funks. Für Nachbarerkennung kämen eigene Kennungs- und Prüfmeldungen infrage. Der normale Wi-Fi-Scan sucht Access Points. Siehe [ESP-NOW-Grundprinzip und Peerverwaltung](https://docs.espressif.com/projects/esp-idf/en/v6.0.1/esp32/api-reference/network/esp_now.html) sowie [Wi-Fi-Scan-API](https://docs.espressif.com/projects/esp-idf/en/v6.0.1/esp32/api-reference/network/esp_wifi.html#_CPPv418esp_wifi_scan_startPK18wifi_scan_config_tb).

Für die nächste Konzeptentscheidung bleiben die konkreten Kanten der beiden vollständigen Topologien, die eindeutige Wahl der ursprünglichen Rückfalltopologie, die Fristen für Wiederverbindung und Rückfall sowie die Zielhierarchie des späteren Topologieoptimierers offen. Für BER ist zusätzlich die technisch zugängliche Empfangsebene zu klären.

# OpenLigaDB Team Tracker für Home Assistant

![Release](https://img.shields.io/github/v/release/Saarlandpower/ha-openligadb-team?style=for-the-badge&label=RELEASE&color=blue)
![HACS](https://img.shields.io/badge/HACS-CUSTOM-orange?style=for-the-badge)
![Downloads](https://img.shields.io/github/downloads/Saarlandpower/ha-openligadb-team/total?style=for-the-badge&label=DOWNLOADS&color=green)
![Stars](https://img.shields.io/github/stars/Saarlandpower/ha-openligadb-team?style=for-the-badge&label=STARS&color=blue&logo=github&logoColor=white)
![Maintained](https://img.shields.io/badge/MAINTAINED-YES-green?style=for-the-badge)

[![Open HACS repository on my Home Assistant](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Saarlandpower&repository=ha-openligadb-team&category=integration)

Verfolge deinen Verein aus **Bundesliga, 2. Bundesliga, 3. Liga, DFB-Pokal** und allen anderen Ligen, die [OpenLigaDB](https://www.openligadb.de) abdeckt — inklusive Tabelle, nächstem Spiel, letztem Ergebnis und Spielplan. Kein API-Key nötig.

Entstanden, weil ESPN/TeamTracker die 3. Liga nicht unterstützt. ⚽💙🖤

![FCS Live Dashboard](screenshots/fcs-live-dashboard.png)

## Features

- **Config Flow**: Liga-Kürzel eingeben (z.B. `bl3`), Verein per Dropdown wählen
- **6 Sensoren pro Verein**:
  | Sensor | Inhalt |
  |---|---|
  | Tabellenplatz | Platzierung, plus Bilanz (S/U/N, Tore, Differenz) als Attribute |
  | Punkte | Aktuelle Punktzahl |
  | Nächstes Spiel | Paarung, Anstoß (UTC + lokal), Spieltag, Wettbewerb |
  | Letztes Spiel | Paarung mit Endergebnis |
  | Spiele | Alle Spiele der letzten 3 / nächsten 5 Wochen — **inkl. Pokalspiele** |
  | Tabelle | Komplette Ligatabelle als Attribut |
- **Saisonwechsel automatisch** (Juli-Logik), in der Sommerpause wird die Abschlusstabelle der Vorsaison angezeigt
- **Teamlogo inklusive**: Die Sensoren liefern das Vereinslogo als `entity_picture` und als Attribut `team_logo`
- Mehrere Vereine/Ligen parallel möglich (je ein Config Entry)
- **Live-Modus**: Während eines Spiels wird jede Minute aktualisiert, sonst passt sich das Intervall automatisch an (siehe unten)
- **Events für Automationen**: Anpfiff, Tore und Abpfiff lösen eigene Events aus – auch als Entität, direkt in der Automations-Oberfläche auswählbar
- **Spielplan als Kalender**, **Live-Spielstand** und Binärsensoren *Spiel läuft* / *Heute Spieltag*

## Installation

### Home Assistant 2026.11 und neuer (Marketplace)

1. Einstellungen → **Marketplace**
2. Nach **OpenLigaDB Team Tracker** suchen und installieren
3. Einstellungen → Geräte & Dienste → **Integration hinzufügen** → "OpenLigaDB Team Tracker"
4. Liga-Kürzel eingeben (`bl3` für die 3. Liga), Verein wählen – fertig

### Ältere Home-Assistant-Versionen (HACS)

1. HACS öffnen und nach **OpenLigaDB Team Tracker** suchen
2. Herunterladen und Home Assistant neu starten
3. Einrichtung wie oben ab Schritt 3

### Fallback: als eigenes Repository hinzufügen

Falls die Integration in der Suche (noch) nicht auftaucht, kann sie direkt per Link hinzugefügt werden – im Marketplace über *Hinzufügen per Link*, in HACS über ⋮ → **Benutzerdefinierte Repositories**:

`https://github.com/Saarlandpower/ha-openligadb-team` – Kategorie **Integration**

## Entitäten

Pro Verein wird ein Gerät mit diesen Entitäten angelegt:

| Entität | Typ | Inhalt |
|---|---|---|
| Tabellenplatz, Punkte | Sensor | aktueller Stand in der Liga |
| Nächstes Spiel, Letztes Spiel | Sensor | Paarung bzw. Ergebnis, Details als Attribute |
| Spiele, Tabelle | Sensor | kompletter Spielplan bzw. Tabelle als Attribut (für Karten) |
| Live-Spielstand | Sensor | z. B. `1:0` während eines Spiels, sonst *unbekannt*; letztes Tor als Attribut |
| Spiel läuft | Binärsensor | an, solange ein Spiel läuft |
| Heute Spieltag | Binärsensor | an, wenn heute ein Anstoß ansteht |
| Spielplan | Kalender | alle Spiele inkl. Pokal, mit Ergebnis nach Abpfiff |
| Spielereignis | Event | Anpfiff, Tor, Abpfiff – als Trigger in der Automations-Oberfläche |

### Ohne YAML: Automation über die Oberfläche

Einstellungen → Automationen → Neue Automation → Auslöser **Entität → Status**, Entität *Spielereignis* auswählen. In der Bedingung lässt sich mit einer Template-Bedingung z. B. nur auf eigene Tore filtern:

```yaml
condition: template
value_template: >-
  {{ trigger.to_state.attributes.event_type == 'goal'
     and trigger.to_state.attributes.for_team }}
```

Der Kalender eignet sich für Erinnerungen: Auslöser **Kalender** → *Spielplan* → *Beginn des Ereignisses* mit Versatz `-00:30:00` meldet sich 30 Minuten vor Anstoß.

## Live-Modus

Das Abfrageintervall richtet sich nach dem Spielplan deines Vereins:

| Situation | Intervall |
|---|---|
| Spiel läuft | jede Minute (nur das laufende Spiel wird abgefragt, Tabelle alle 15 Min.) |
| Anstoß in weniger als 15 Min. | Update genau zum Anstoß |
| Spiel in den nächsten 12 h oder vor weniger als 6 h | alle 15 Minuten |
| sonst | stündlich |

Während eines Spiels haben die Spiele im Sensor *Nächstes Spiel* bzw. *Spiele* die Attribute `live: true` und `live_score` (z. B. `1:0`).

## Events für Automationen

| Event | Wann | Wichtige Daten |
|---|---|---|
| `openligadb_team_match_started` | Anpfiff | `home`, `away`, `competition`, `team_side` |
| `openligadb_team_goal` | Tor | `score`, `minute`, `scorer`, `scoring_team`, `for_team`, `penalty`, `own_goal` |
| `openligadb_team_match_ended` | Abpfiff | `score`, `result` (`won` / `draw` / `lost`) |

Alle Events enthalten außerdem `team`, `entry_id`, `league_shortcut`, `match_id`, `matchday`, `score_home` und `score_away`. `for_team` ist `true`, wenn das Tor für deinen Verein fiel – auch bei Eigentoren des Gegners.

Nach einem Neustart von Home Assistant werden bereits gefallene Tore nicht erneut gemeldet. Wie schnell ein Tor ankommt, hängt davon ab, wie schnell es bei OpenLigaDB eingetragen wird (Community-gepflegt, meist wenige Minuten).

### Beispiel: Push-Nachricht bei einem Tor des eigenen Vereins

```yaml
automation:
  - alias: "Tor für meinen Verein"
    triggers:
      - trigger: event
        event_type: openligadb_team_goal
        event_data:
          team: "1. FC Saarbrücken"
          for_team: true
    actions:
      - action: notify.mobile_app_mein_handy
        data:
          title: "⚽ TOR! {{ trigger.event.data.score }}"
          message: >-
            {{ trigger.event.data.scorer }} ({{ trigger.event.data.minute }}.)
            – {{ trigger.event.data.home }} gegen {{ trigger.event.data.away }}
```

### Beispiel: Endergebnis melden

```yaml
automation:
  - alias: "Abpfiff"
    triggers:
      - trigger: event
        event_type: openligadb_team_match_ended
    actions:
      - action: notify.mobile_app_mein_handy
        data:
          title: >-
            {{ {'won': 'Sieg! 🎉', 'draw': 'Unentschieden', 'lost': 'Niederlage'}[trigger.event.data.result] | default('Abpfiff') }}
          message: "{{ trigger.event.data.home }} {{ trigger.event.data.score }} {{ trigger.event.data.away }}"
```

## Gängige Liga-Kürzel

`bl1` (Bundesliga), `bl2` (2. Bundesliga), `bl3` (3. Liga), `dfb` (DFB-Pokal). Weitere unter [openligadb.de](https://www.openligadb.de).

## Wie erstelle ich daraus eine Karte in Home Assistant?

Sobald du einen Verein hinzugefügt hast, legt die Integration pro Team **6 Sensoren** an. Danach geht es in Lovelace so weiter:

1. Dashboard öffnen
2. Oben rechts auf **Bearbeiten**
3. **Karte hinzufügen**
4. **Manuell** auswählen
5. Eines der YAML-Beispiele aus [`examples/lovelace_cards.yaml`](examples/lovelace_cards.yaml) einfügen
6. Die Beispiel-Entities wie `sensor.1_fc_saarbrucken_tabelle` auf deine eigenen Entity-IDs anpassen

Die Entity-IDs findest du unter **Entwicklerwerkzeuge → Zustände**, wenn du nach `openligadb`, deinem Vereinsnamen oder `tabelle` suchst.

Zusätzlich stellen die Sensoren das Teamlogo direkt als **`entity_picture`** bereit. Damit kannst du es ohne Zusatz-API direkt in `picture-entity`, Mushroom-Karten oder anderen Lovelace-Karten verwenden.

## Beispiel: Tabellen-Card (Markdown)

```yaml
type: markdown
content: |
  ## 3. Liga {{ state_attr('sensor.1_fc_saarbrucken_tabelle', 'season') }}/{{ (state_attr('sensor.1_fc_saarbrucken_tabelle', 'season') or 0) + 1 }}
  | # | Team | Sp | TD | Pkt |
  |---|------|----|----|----|
  {% for t in state_attr('sensor.1_fc_saarbrucken_tabelle', 'table') or [] -%}
  | {{ t.position }} | {% if 'Saarbrücken' in t.team %}**{{ t.team }}**{% else %}{{ t.team }}{% endif %} | {{ t.matches }} | {{ t.goal_diff }} | **{{ t.points }}** |
  {% endfor %}
```

## Weitere Lovelace-Beispiele

Fertige Beispiele für typische Karten findest du hier:

- [`examples/lovelace_cards.yaml`](examples/lovelace_cards.yaml)

Enthalten sind unter anderem:

- kompakte Team-Übersicht
- Logo-Karte für den Verein
- Karte für das nächste Spiel
- Karte für das letzte Spiel
- Spielplan der kommenden und vergangenen Partien
- Tabellenansicht als Markdown-Karte

## Hinweise

- Datenquelle: [api.openligadb.de](https://api.openligadb.de) — Community-gepflegt, Live-Zwischenstände können je nach Liga verzögert sein
- Update-Intervall: 15 Minuten
- Dieses Projekt steht in keiner Verbindung zu OpenLigaDB, der DFL oder dem DFB

## ☕ Support Development

Wenn dir dieses Projekt gefällt und du die Weiterentwicklung unterstützen möchtest:

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/saarmesh)

Deine Unterstützung hilft bei Entwicklung, Tests, Bugfixes und neuen Features.

## Lizenz

MIT

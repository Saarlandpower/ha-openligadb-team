# OpenLigaDB Team Tracker für Home Assistant

Verfolge deinen Verein aus **Bundesliga, 2. Bundesliga, 3. Liga, DFB-Pokal** und allen anderen Ligen, die [OpenLigaDB](https://www.openligadb.de) abdeckt — inklusive Tabelle, nächstem Spiel, letztem Ergebnis und Spielplan. Kein API-Key nötig.

Entstanden, weil ESPN/TeamTracker die 3. Liga nicht unterstützt. ⚽💙🖤

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
- Mehrere Vereine/Ligen parallel möglich (je ein Config Entry)

## Installation (HACS)

1. HACS → Integrationen → ⋮ → **Custom Repositories**
2. Repository: `https://github.com/Saarlandpower/ha-openligadb-team` — Kategorie: **Integration**
3. **OpenLigaDB Team Tracker** installieren
4. Home Assistant neu starten
5. Einstellungen → Geräte & Dienste → **Integration hinzufügen** → "OpenLigaDB Team Tracker"
6. Liga-Kürzel eingeben (`bl3` für die 3. Liga), Verein wählen — fertig

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
- Karte für das nächste Spiel
- Karte für das letzte Spiel
- Spielplan der kommenden und vergangenen Partien
- Tabellenansicht als Markdown-Karte

## Hinweise

- Datenquelle: [api.openligadb.de](https://api.openligadb.de) — Community-gepflegt, Live-Zwischenstände können je nach Liga verzögert sein
- Update-Intervall: 15 Minuten
- Dieses Projekt steht in keiner Verbindung zu OpenLigaDB, der DFL oder dem DFB

## Lizenz

MIT

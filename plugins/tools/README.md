# AgentLayer Tools

Dieses Verzeichnis enthält alle spezialisierten Tools für AgentLayer.

## Verfügbare Tools

### Grep Tool
- **Datei**: `grep_tool.py`
- **Beschreibung**: Suche in Dateiinhalten mit regulären Ausdrücken
- **Funktionen**: 
  - Reguläre Ausdruckssuche
  - Datei- und Verzeichnissuche
  - Dateifilterung
  - Formatierung der Ergebnisse

## Tool-Entwicklung

Neue Tools sollten folgende Struktur haben:

1. Ein Python-Skript mit dem Tool-Code
2. `TOOLS`-Liste mit Tool-Definitionen
3. `HANDLERS`-Dictionary mit Handler-Funktionen
4. Metadata-Attribute für Integration in das System

Tools werden automatisch durch das Plugin-System geladen, wenn sie sich im `plugins/tools`-Verzeichnis befinden.
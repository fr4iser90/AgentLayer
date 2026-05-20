# Ersteinrichtung (Self-Hosted)

## Voraussetzungen

- Docker und Docker Compose
- Datei `.env` mit mindestens:
  - `AGENT_JWT_SECRET` (einmalig: `openssl rand -hex 32`)
  - `DATABASE_URL` (in Compose meist vorkonfiguriert)

Optional: `AGENT_INITIAL_ADMIN_EMAIL` und `AGENT_INITIAL_ADMIN_PASSWORD` legen den ersten Administrator beim Start an (Automation). Ohne diese Variablen erfolgt die Anlage über die Web-Oberfläche.

**Einrichtungs-Token:** Wenn `AGENT_SETUP_TOKEN` in `.env` gesetzt ist, ist es für Schritt 1 der Ersteinrichtung erforderlich. Ist es nicht gesetzt, erzeugt der Server beim ersten Start ein Token und schreibt es **einmal** ins Log (`docker compose logs agent-layer`). Für öffentlich erreichbare Hosts `AGENT_SETUP_TOKEN` vor dem Start setzen (`openssl rand -hex 32`).

## Start

```bash
docker compose up -d
```

Öffnen Sie im Browser:

`http://localhost:8088/app/setup`

(Port über `AGENT_HTTP_PORT` in `.env` anpassbar.)

## Ablauf in der Oberfläche

1. **Administrator** — E-Mail und Passwort (mindestens 8 Zeichen) für das erste Admin-Konto.
2. **KI-Provider & Modelle** — Alle konfigurierten Provider (erreichbar/nicht erreichbar), Chat- vs. Embedding-Modelle, Standard-Profile (Allgemein, Coding, RAG). Optional manueller Zusatz-Endpunkt.
3. **Abschluss** — Weiter zum Chat; Modell im Composer jederzeit änderbar.

Weitere Endpunkte und Schnittstellen: **Admin → Schnittstellen**.

## API (Referenz)

| Methode | Pfad | Beschreibung |
|---------|------|----------------|
| GET | `/auth/setup-status` | Status der Ersteinrichtung |
| POST | `/auth/setup` | Ersten Administrator anlegen (nur solange kein Admin existiert) |
| GET | `/auth/setup/catalog` | Provider-Status, Chat-/Embedding-Modelle (Admin-Session) |
| POST | `/auth/setup/preferences` | Bevorzugten Provider und Profilmodelle speichern |
| POST | `/auth/setup/test-embedding` | Embedding-Modell testen (Dimensionen) |
| POST | `/auth/setup/llm` | Zusätzlichen LLM-Endpunkt testen oder speichern |

## Fehlerbehebung

| Symptom | Maßnahme |
|---------|----------|
| Container startet nicht | Logs: `docker compose logs agent-layer`; Datenbank-Migrationen und `DATABASE_URL` prüfen |
| Setup-Seite nicht erreichbar | URL mit Präfix `/app/setup`; Reverse-Proxy muss `/app` an den Agent weiterleiten |
| LLM-Verbindung fehlgeschlagen | Basis-URL, Netzwerk (Container → Ollama-Host), API-Schlüssel prüfen |
| Chat ohne Modell | Ersteinrichtung Schritt 2 abschließen oder Endpunkt unter Admin → Schnittstellen anlegen |

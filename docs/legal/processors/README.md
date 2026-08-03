# Auftragsverarbeiter (AVV / DPA)

Diese Dateien sind **nicht** für Endnutzer gedacht. Sie helfen dem **Betreiber** einer Agent-Layer-Instanz, Verträge mit Dienstleistern abzuschließen.

## Checkliste (DE)

| Dienst | Typisch nötig wenn … | Aktion |
|--------|----------------------|--------|
| Hoster (Hetzner, AWS, …) | Server in DE/EU | AVV/DPA beim Provider aktivieren |
| PostgreSQL (managed) | Managed DB | DPA des Cloud-Anbieters |
| Externer LLM-Provider | Chat geht an OpenAI, Anthropic, … | DPA + ggf. EU-Standardvertragsklauseln |
| E-Mail (z. B. Resend) | System-Mails, Einladungen | DPA beim Mail-Provider |
| Backups (S3, etc.) | Automatische Backups | DPA + Löschkonzept dokumentieren |

## Was im Repo liegt

- **Vorlagen** für Rechtstexte: `content/legal/{de,en,_template}/`
- **Öffentliche Seiten**: nur Impressum, Datenschutz, ggf. AGB (Footer)
- **AVVs**: Verträge mit Anbietern — privat beim Betreiber ablegen, nicht im Footer verlinken

## Aktivierung (öffentliche Seiten)

```bash
# Als Site-Admin per API (nach Migration schema_115):
curl -X PATCH https://your-host/v1/admin/operator-settings \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "legal_enabled": true,
    "legal_jurisdiction": "de",
    "legal_entity_name": "Ihr Name / Firma",
    "legal_entity_address": "Straße, PLZ Ort",
    "legal_entity_email": "kontakt@example.de",
    "legal_terms_enabled": false
  }'
```

- `legal_enabled: false` oder `legal_jurisdiction: "none"` → keine Footer-Links (für private/US-Self-Hoster)
- `legal_terms_enabled: true` → zusätzlich AGB-Seite (empfohlen bei echten Accounts)
- Texte anpassen: Dateien unter `content/legal/de/` bearbeiten **oder** Markdown-Felder `legal_impressum_md`, `legal_privacy_md`, `legal_terms_md` per PATCH setzen (überschreiben Dateien)

## Löschkonzept

Technisch: Kontolöschung in der App + Abschnitt in der Datenschutzerklärung (`content/legal/de/datenschutz.md`).

Rechtlich: dokumentieren, welche Daten wie lange in Logs, Backups und bei Sub-Prozessoren verbleiben.

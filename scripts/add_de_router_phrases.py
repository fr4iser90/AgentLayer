#!/usr/bin/env python3
"""Add ``phrases.de`` to every co-located ``*.router.yaml`` (plugins stay plugins)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "plugins" / "tools"

# Phrases that stay identical in DE routing (brands, tool ids, protocols).
KEEP_AS_IS = frozenset(
    {
        "gmail",
        "outlook",
        "gmx",
        "yahoo",
        "proton",
        "github",
        "gitlab",
        "spotify",
        "telegram",
        "discord",
        "imap",
        "rss",
        "grep",
        "rag",
        "api",
        "http",
        "otp",
        "cron",
        "kb",
        "lsp",
        "mdr",
        "ddgs",
        "tavily",
        "openweather",
        "openweathermap",
        "playwright",
        "vimeo",
        "youtube",
        "webhook",
        "plugin",
        "catalog",
        "bash",
        "delegate",
        "create",
        "update",
        "read",
        "replace",
        "rename",
        "list",
        "mail",
        "email",
        "repo",
        "repository",
        "workspace",
        "github.com",
        "read_file",
        "tool_help",
        "secrets_help",
        "register_secret",
        "request_user_secret",
        "save_user_secret",
        "user_secrets_status",
        "scheduler_jobs",
        "inpainting_realvision",
        "@",
        ".com",
        ".de",
        "@gmail.com",
        "@outlook.com",
        "@hotmail.com",
    }
)

GERMAN_HINT = re.compile(r"[äöüß]", re.I)
GERMAN_PREFIXES = (
    "wann ",
    "wer ",
    "was ",
    "zeit ",
    "schicht",
    "kalender",
    "freund",
    "freigabe",
    "geteilt",
    "teile ",
    "merk",
    "notier",
    "speicher",
    "abspeicher",
    "verknüpf",
    "zugriff",
    "urlaub",
    "feiertag",
    "dienst",
    "schreib",
    "angel",
    "jagd",
    "fisch",
    "köder",
    "gewässer",
    "wasser",
    "wetter",
    "wild",
    "notfall",
    "unterstand",
    "übernacht",
    "informations",
    "kontakt",
    "bekannte",
    "telefonnummer",
    "email von",
    "repos importieren",
    "repository aktualisieren",
    "workspace updaten",
    "veröffentliche",
    "nächste schicht",
    "wann muss",
    "wann bin ich",
    "wann arbeite",
    "wann ist ",
    "wann wieder",
    "wieder arbeiten",
    "wer darf",
    "wer hat zugriff",
    "warteschlange",
    "umgebung",
    "einprägen",
    "entziehe",
    "benachrichtige",
    "anschreib",
    "ansitz",
    "trittsiegel",
    "gummifisch",
    "wobbler",
    "spur",
    "track",
    "drift",
    "crosswind",
    "wind",
    "spot",
    "bait",
    "bite",
    "lure",
    "forecast",
    "dehydration",
    "shelter",
    "bivouac",
    "survival",
    "hunting",
    "fishing",
    "outdoor",
    "risiko",
    "risk",
    "notlager",
    "profil",
    "vorschlag",
    "lied",
    "lieder",
    "musik",
    "music",
    "radio",
    "webradio",
    "internetradio",
    "mediathek",
    "stream",
    "playlist",
    "montage",
    "knoten",
    "stelle",
    "dienstplan",
    "schichtplan",
    "termin",
    "termine",
    "frei am",
    "gedächtnis",
    "nachricht",
    "verlauf",
)

# English phrase -> German routing substrings (lowercase).
EXACT_DE: dict[str, list[str]] = {
    "add friend": ["freund hinzufügen", "freund adden"],
    "add secret": ["geheimnis speichern", "secret speichern"],
    "admin": ["admin", "administrator", "verwaltung"],
    "agent callback": ["agent callback", "agent-rückruf"],
    "agent catalog": ["agent katalog", "agenten katalog"],
    "agentlayer verify": ["workspace verifizieren", "projekt prüfen"],
    "agents": ["agenten", "agents"],
    "api connector": ["api connector", "api verbindung"],
    "api key": ["api schlüssel", "api key"],
    "api profile": ["api profil", "api profile"],
    "app password": ["app passwort", "app-passwort"],
    "apply patch": ["patch anwenden", "patch einspielen"],
    "appointment": ["termin", "appointment"],
    "arbeit": ["arbeit"],
    "arbeitszeit": ["arbeitszeit"],
    "artifact": ["artefakt", "anhang"],
    "ask for api key": ["api key anfordern", "schlüssel anfordern"],
    "audio": ["audio", "ton"],
    "backlog": ["backlog", "aufgabenstau"],
    "bind workspace": ["workspace binden", "arbeitsbereich binden"],
    "board": ["board", "pinnwand", "tafel"],
    "brave search": ["brave suche", "websuche brave"],
    "build": ["bauen", "build", "erstellen"],
    "build index": ["index aufbauen", "index erstellen"],
    "calendar": ["kalender", "calendar"],
    "call api": ["api aufrufen", "api call"],
    "call graph": ["aufrufgraph", "call graph"],
    "callees": ["aufgerufene", "callees"],
    "callers": ["aufrufer", "callers"],
    "card grid": ["kartenraster", "card grid"],
    "chart block": ["diagramm block", "chart block"],
    "chat history": ["chatverlauf", "chat historie"],
    "clock": ["uhr", "clock"],
    "clone": ["klonen", "clone"],
    "clone repo": ["repo klonen", "repository klonen"],
    "code index": ["code index", "code-index"],
    "codegen": ["code generieren", "codegen"],
    "coding agent": ["coding agent", "coding-agent"],
    "coding bash": ["shell ausführen", "bash ausführen", "befehl ausführen"],
    "coding edit": ["datei bearbeiten", "code bearbeiten"],
    "coding glob": ["dateien suchen", "glob muster"],
    "coding index": ["code indexieren", "projekt indexieren"],
    "coding list": ["dateien auflisten", "verzeichnis listen"],
    "coding lsp": ["lsp", "definition springen", "referenzen finden"],
    "coding patch": ["patch anwenden", "diff anwenden"],
    "coding read": ["datei lesen", "code lesen"],
    "coding replace": ["datei ersetzen", "code ersetzen"],
    "coding search": ["code suchen", "im code suchen"],
    "coding symbols": ["symbol suchen", "symbole finden"],
    "coding task": ["coding aufgabe", "coding task"],
    "coding todo": ["todo liste", "aufgabenliste coding"],
    "coding write": ["datei schreiben", "code schreiben"],
    "collection": ["sammlung", "collection"],
    "configured secrets": ["konfigurierte secrets", "gespeicherte geheimnisse"],
    "connector": ["connector", "verbindung"],
    "context": ["kontext", "context"],
    "conversation history": ["gesprächsverlauf", "chatverlauf"],
    "create file": ["datei erstellen", "datei anlegen"],
    "create pr": ["pull request erstellen", "pr erstellen"],
    "create release": ["release erstellen", "veröffentlichung erstellen"],
    "create tool": ["tool erstellen", "werkzeug erstellen"],
    "create workspace": ["workspace erstellen", "arbeitsbereich erstellen"],
    "credential": ["zugangsdaten", "credential"],
    "dashboard": ["dashboard", "übersicht"],
    "dashboards": ["dashboards", "übersichten"],
    "days off": ["freie tage", "urlaubstage"],
    "dependencies": ["abhängigkeiten", "dependencies"],
    "dependents": ["abhängige", "dependents"],
    "describe the project": ["projekt beschreiben", "projekt erklären"],
    "domain data": ["domänendaten", "domain daten"],
    "duckduckgo": ["duckduckgo", "websuche"],
    "dynamic tool": ["dynamisches tool", "tool dynamisch"],
    "earlier messages": ["frühere nachrichten", "ältere nachrichten"],
    "edit file": ["datei bearbeiten", "datei editieren"],
    "embeddings": ["embeddings", "einbettungen"],
    "enqueue scan": ["scan einreihen", "scan starten"],
    "entity": ["entität", "entity"],
    "environment": ["umgebung", "environment"],
    "execute": ["ausführen", "execute"],
    "execute project": ["projekt ausführen", "projekt starten"],
    "explain project": ["projekt erklären", "projekt beschreiben"],
    "explain the project": ["das projekt erklären", "projekt erklären"],
    "explain this codebase": ["codebase erklären", "codebasis erklären"],
    "exposure": ["exposition", "belichtung"],
    "extra tool": ["extra tool", "zusätzliches tool"],
    "feed": ["feed", "nachrichtenfeed"],
    "feeds": ["feeds", "feeds abonnieren"],
    "fetch": ["holen", "fetch", "abrufen"],
    "file pattern": ["dateimuster", "file pattern"],
    "filesystem": ["dateisystem", "filesystem"],
    "find code": ["code finden", "code suchen"],
    "find files": ["dateien finden", "dateien suchen"],
    "find in codebase": ["in codebase suchen", "in codebasis suchen"],
    "find in files": ["in dateien suchen", "dateien durchsuchen"],
    "find references": ["referenzen finden", "verweise finden"],
    "find symbol": ["symbol finden", "symbol suchen"],
    "finding-policy": ["finding policy", "befund richtlinie"],
    "forecast": ["vorhersage", "prognose"],
    "freundesanfrage": ["freundesanfrage"],
    "freundschaft": ["freundschaft"],
    "friend request": ["freundschaftsanfrage", "freundesanfrage"],
    "generate tool": ["tool generieren", "werkzeug generieren"],
    "get issue": ["issue abrufen", "ticket abrufen"],
    "get pr": ["pull request abrufen", "pr abrufen"],
    "git checkout": ["git checkout", "branch wechseln"],
    "git clone": ["git clone", "repository klonen"],
    "git diff": ["git diff", "unterschiede anzeigen"],
    "git fetch": ["git fetch", "remote holen"],
    "git log": ["git log", "commit historie"],
    "git pull": ["git pull", "pullen", "repository aktualisieren"],
    "git push": ["git push", "pushen", "branch hochladen"],
    "git status": ["git status", "repository status"],
    "github code search": ["github code suche", "code auf github suchen"],
    "github file": ["github datei", "datei auf github"],
    "github issue": ["github issue", "github ticket"],
    "github issues": ["github issues", "github tickets"],
    "github pr create": ["github pr erstellen", "pull request github"],
    "github prs": ["github pull requests", "github prs"],
    "github release": ["github release", "github veröffentlichung"],
    "github repos": ["github repos", "github repositories"],
    "glob pattern": ["glob muster", "dateimuster"],
    "go to definition": ["zur definition springen", "definition anzeigen"],
    "grant access": ["zugriff gewähren", "zugriff erteilen"],
    "graph memory": ["graph speicher", "wissensgraph"],
    "hover": ["hover", "info anzeigen"],
    "ical": ["ical", "kalenderdatei"],
    "ics": ["ics", "kalender import"],
    "ide agent": ["ide agent", "ide-agent"],
    "impact analysis": ["impact analyse", "auswirkungsanalyse"],
    "imports": ["importe", "imports"],
    "inbox": ["posteingang", "inbox"],
    "index code": ["code indexieren", "index aufbauen"],
    "inheritance": ["vererbung", "inheritance"],
    "integration profile": ["integrationsprofil", "integration profile"],
    "items": ["einträge", "items"],
    "job": ["job", "auftrag"],
    "jump": ["springen", "jump"],
    "kanban": ["kanban", "kanban board"],
    "knowledge base": ["wissensbasis", "knowledge base"],
    "knowledge base documents": ["wissensbasis dokumente", "kb dokumente"],
    "last release": ["letzte veröffentlichung", "last release"],
    "latest release": ["neueste veröffentlichung", "latest release"],
    "layout": ["layout", "anordnung"],
    "lint test workspace": ["workspace linten", "projekt prüfen lint test"],
    "list agents": ["agenten auflisten", "agents listen"],
    "list directory": ["verzeichnis listen", "ordner auflisten"],
    "list files": ["dateien listen", "dateien auflisten"],
    "list prs": ["pull requests listen", "prs auflisten"],
    "list pull requests": ["pull requests auflisten", "prs listen"],
    "list repos": ["repos listen", "repositories auflisten"],
    "list scans": ["scans listen", "scans auflisten"],
    "local file": ["lokale datei", "local file"],
    "media": ["medien", "media"],
    "memory": ["speicher", "memory", "gedächtnis"],
    "memory graph": ["speicher graph", "memory graph"],
    "message": ["nachricht", "message"],
    "mp3": ["mp3", "audio datei"],
    "my notes": ["meine notizen", "my notes"],
    "my targets": ["meine ziele", "meine targets"],
    "new tool": ["neues tool", "tool erstellen"],
    "new version": ["neue version", "version erstellen"],
    "news": ["nachrichten", "news"],
    "next shift": ["nächste schicht", "next shift"],
    "notebook": ["notizbuch", "notebook"],
    "notify": ["benachrichtigen", "notify"],
    "now playing": ["läuft gerade", "now playing"],
    "one-shot": ["einmalig", "one-shot"],
    "open pull request": ["pull request öffnen", "pr eröffnen"],
    "operator": ["operator", "betreiber"],
    "patch code": ["code patchen", "code reparieren"],
    "pets": ["haustiere", "pets"],
    "policy schema": ["policy schema", "richtlinien schema"],
    "preferences": ["einstellungen", "preferences"],
    "project overview": ["projektüberblick", "project overview"],
    "project run": ["projekt ausführen", "project run"],
    "project structure": ["projektstruktur", "project structure"],
    "project workspace": ["projekt workspace", "projekt arbeitsbereich"],
    "proposal": ["vorschlag", "proposal"],
    "publish branch": ["branch veröffentlichen", "branch pushen"],
    "publish release": ["release veröffentlichen", "veröffentlichung"],
    "pull latest": ["neueste holen", "pull latest", "aktuell pullen"],
    "pull request details": ["pull request details", "pr details"],
    "push branch": ["branch pushen", "branch hochladen"],
    "push to github": ["zu github pushen", "github push"],
    "queue": ["warteschlange", "queue"],
    "read chat": ["chat lesen", "verlauf lesen"],
    "read code": ["code lesen", "code anzeigen"],
    "read file": ["datei lesen", "file lesen"],
    "read github file": ["github datei lesen", "datei von github lesen"],
    "readme": ["readme", "readme lesen"],
    "recurring": ["wiederkehrend", "recurring"],
    "redesign": ["neu gestalten", "redesign"],
    "relation": ["beziehung", "relation"],
    "remember": ["merken", "remember"],
    "remember list": ["merkliste", "remember list"],
    "request": ["anfrage", "request"],
    "request secret": ["secret anfordern", "geheimnis anfordern"],
    "rescan": ["neu scannen", "rescan"],
    "resolve-scan": ["scan auflösen", "resolve scan"],
    "rest": ["pause", "rest", "ruhe"],
    "retrieve": ["abrufen", "retrieve", "kontext holen"],
    "revoke access": ["zugriff entziehen", "zugriff widerrufen"],
    "run": ["ausführen", "run", "starten"],
    "run command": ["befehl ausführen", "kommando ausführen"],
    "run now": ["jetzt ausführen", "run now"],
    "run verify": ["verifizierung ausführen", "verify ausführen"],
    "run_plan_subagent": ["plan subagent", "run plan subagent"],
    "save profile": ["profil speichern", "save profile"],
    "save secret": ["secret speichern", "geheimnis speichern"],
    "scan findings": ["scan befunde", "scan ergebnisse"],
    "scan get": ["scan abrufen", "scan get"],
    "scan history": ["scan historie", "scan verlauf"],
    "scan project": ["projekt scannen", "scan project"],
    "scan status": ["scan status", "scan-status"],
    "schedule": ["planen", "schedule", "zeitplan"],
    "scheduler": ["scheduler", "zeitplaner"],
    "scheduler job": ["scheduler job", "geplanter job"],
    "search code": ["code suchen", "code durchsuchen"],
    "search docs and code": ["doku und code suchen", "docs und code suchen"],
    "search issues": ["issues suchen", "tickets suchen"],
    "search pull requests": ["pull requests suchen", "prs suchen"],
    "search repository code": ["repository code suchen", "repo code suchen"],
    "search symbols": ["symbole suchen", "search symbols"],
    "search the web": ["im web suchen", "websuche"],
    "second brain": ["zweites gehirn", "second brain"],
    "secret": ["geheimnis", "secret"],
    "secret form": ["secret formular", "geheimnis formular"],
    "secrets status": ["secrets status", "geheimnis status"],
    "security auditor": ["security auditor", "sicherheits auditor"],
    "security scan": ["sicherheitsscan", "security scan"],
    "semantic lookup": ["semantische suche", "semantic lookup"],
    "semantic search": ["semantische suche", "semantic search"],
    "semgrep findings": ["semgrep befunde", "semgrep findings"],
    "session todo": ["session todo", "sitzung todo"],
    "settings": ["einstellungen", "settings"],
    "share my calendar": ["kalender teilen", "meinen kalender teilen"],
    "shares": ["freigaben", "shares"],
    "sharing": ["teilen", "sharing"],
    "shell": ["shell", "terminal"],
    "shift": ["schicht", "shift"],
    "simplesec": ["simplesec", "ssc"],
    "simplesec get": ["simplesec abrufen", "scan abrufen"],
    "simplesec status": ["simplesec status", "scan status"],
    "smart edit": ["smart edit", "intelligent bearbeiten"],
    "snapshot": ["snapshot", "momentaufnahme"],
    "song": ["song", "lied"],
    "specialist": ["spezialist", "specialist"],
    "specialists": ["spezialisten", "specialists"],
    "spotify": ["spotify"],
    "ssc": ["ssc", "simplesec"],
    "ssc callback": ["ssc callback", "scan callback"],
    "ssc schema": ["ssc schema", "scan schema"],
    "ssc status": ["ssc status", "scan status"],
    "ssc targets": ["ssc targets", "scan ziele"],
    "start scan": ["scan starten", "start scan"],
    "subagent": ["subagent", "unter-agent"],
    "subclass": ["unterklasse", "subclass"],
    "subtask": ["unteraufgabe", "subtask"],
    "summarize feeds": ["feeds zusammenfassen", "feeds summary"],
    "summary": ["zusammenfassung", "summary"],
    "superclass": ["oberklasse", "superclass"],
    "surgical edit": ["chirurgisch bearbeiten", "surgical edit"],
    "switch workspace": ["workspace wechseln", "arbeitsbereich wechseln"],
    "symbol lookup": ["symbol nachschlagen", "symbol lookup"],
    "task": ["aufgabe", "task"],
    "task list": ["aufgabenliste", "task list"],
    "tell me about this project": ["erzähl mir über das projekt", "projekt beschreiben"],
    "temperature": ["temperatur", "temperature"],
    "tenant": ["mandant", "tenant"],
    "time off": ["freizeit", "urlaub", "time off"],
    "timezone": ["zeitzone", "timezone"],
    "todo": ["todo", "aufgabe", "to-do"],
    "tool policy": ["tool richtlinie", "tool policy"],
    "tools": ["tools", "werkzeuge"],
    "tracking": ["tracking", "verfolgung"],
    "type hierarchy": ["typ hierarchie", "type hierarchy"],
    "ui layout": ["ui layout", "oberflächen layout"],
    "unified diff": ["unified diff", "diff anwenden"],
    "update repo": ["repo aktualisieren", "repository aktualisieren"],
    "upload branch": ["branch hochladen", "branch upload"],
    "variant": ["variante", "variant"],
    "vector search": ["vektorsuche", "vector search"],
    "verify workspace": ["workspace verifizieren", "projekt verifizieren"],
    "view file": ["datei anzeigen", "file anzeigen"],
    "vulnerabilities": ["schwachstellen", "vulnerabilities"],
    "water": ["wasser", "water"],
    "weather": ["wetter", "weather"],
    "web search": ["websuche", "web search"],
    "what breaks": ["was bricht", "what breaks"],
    "what does this project do": ["was macht das projekt", "projektzweck"],
    "what is this codebase": ["was ist diese codebase", "codebasis erklären"],
    "what is this project": ["was ist dieses projekt", "projekt erklären"],
    "what time": ["wie spät", "what time", "uhrzeit"],
    "when am i working": ["wann arbeite ich", "when am i working"],
    "when do i work": ["wann arbeite ich", "when do i work"],
    "where to fish": ["wo angeln", "angelplatz"],
    "which agent": ["welcher agent", "which agent"],
    "which api keys": ["welche api keys", "welche schlüssel"],
    "who calls": ["wer ruft auf", "who calls"],
    "widget": ["widget", "baustein"],
    "work schedule": ["arbeitsplan", "schichtplan"],
    "write code": ["code schreiben", "write code"],
    "write file": ["datei schreiben", "write file"],
    "zoneinfo": ["zeitzone", "zoneinfo"],
    "playwright, playwright bundle, local browser, browser automation, export zip, download automation, client-side browser, validate automation plan": [
        "playwright",
        "browser automatisierung",
        "lokaler browser",
        "automatisierung export",
    ],
}


def _is_german(phrase: str) -> bool:
    p = phrase.lower().strip()
    if not p:
        return False
    if GERMAN_HINT.search(p):
        return True
    return any(p.startswith(pref) for pref in GERMAN_PREFIXES)


def _to_de(en: str) -> list[str]:
    key = en.lower().strip()
    if not key:
        return []
    if _is_german(key):
        return [key]
    if key in KEEP_AS_IS:
        return [key]
    if key in EXACT_DE:
        return list(dict.fromkeys(EXACT_DE[key]))
    # Heuristic replacements for common English fragments.
    de = key
    replacements = (
        ("search ", "suche "),
        ("find ", "finde "),
        ("list ", "liste "),
        ("create ", "erstelle "),
        ("read ", "lies "),
        ("write ", "schreibe "),
        ("update ", "aktualisiere "),
        ("delete ", "lösche "),
        ("open ", "öffne "),
        ("run ", "starte "),
        ("project ", "projekt "),
        ("file ", "datei "),
        ("files", "dateien"),
        ("workspace ", "workspace "),
        ("repository ", "repository "),
        ("scan ", "scan "),
        ("tool ", "tool "),
        ("agent ", "agent "),
        ("calendar", "kalender"),
        ("schedule", "zeitplan"),
        ("memory", "speicher"),
        ("secret", "geheimnis"),
    )
    for src, dst in replacements:
        if src in de:
            de = de.replace(src, dst)
    if de != key:
        return list(dict.fromkeys([de, key]))
    return [key]


def _yaml_dump(doc: dict, stem: str) -> str:
    lines = [
        f"# Co-located router phrases for {stem}.py — locale keys are authoring-only.",
        f"domain: {doc['domain']}",
        "phrases:",
    ]
    phrases = doc.get("phrases") or {}
    for lang in ("en", "de"):
        if lang not in phrases:
            continue
        items = phrases[lang]
        if not items:
            continue
        lines.append(f"  {lang}:")
        for item in items:
            s = str(item)
            if any(ch in s for ch in ':@#[]{}|>&*!"\''):
                lines.append(f'    - "{s}"')
            else:
                lines.append(f"    - {s}")
    return "\n".join(lines) + "\n"


def process_yaml(path: Path, *, dry_run: bool = False) -> bool:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return False
    domain = str(raw.get("domain") or "").strip()
    phrases = raw.get("phrases")
    if not isinstance(phrases, dict):
        return False
    en = [str(x).strip().lower() for x in (phrases.get("en") or []) if str(x).strip()]
    if not en:
        return False

    de_seen: set[str] = set()
    de_list: list[str] = []
    for existing in phrases.get("de") or []:
        p = str(existing).strip().lower()
        if p and p not in de_seen:
            de_seen.add(p)
            de_list.append(p)
    for item in en:
        for p in _to_de(item):
            if p not in de_seen:
                de_seen.add(p)
                de_list.append(p)

    if not de_list:
        return False
    if list(phrases.get("de") or []) == de_list:
        return False

    phrases["de"] = de_list
    raw["phrases"] = phrases
    raw["domain"] = domain
    out = _yaml_dump(raw, path.stem)
    if dry_run:
        print(f"update {path.relative_to(ROOT)} (+{len(de_list)} de)")
        return True
    path.write_text(out, encoding="utf-8")
    return True


def main() -> int:
    import sys

    dry = "--dry-run" in sys.argv
    n = 0
    for path in sorted(TOOLS.rglob("*.router.yaml")):
        if process_yaml(path, dry_run=dry):
            n += 1
    print(f"{'would update' if dry else 'updated'} {n} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

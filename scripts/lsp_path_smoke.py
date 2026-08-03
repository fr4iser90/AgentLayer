#!/usr/bin/env python3
"""Check that Python and TypeScript/JS language servers are reachable on PATH.

Does not start LSP or talk to the API — PATH / env smoke only.
See docs/runbooks/lsp.md.
"""

from __future__ import annotations

import os
import shutil
import sys

# Keep in sync with plugins/tools/workspace/lib/lsp_client.py LANGUAGE_SERVERS.
CANDIDATES: dict[str, list[str]] = {
    "python": ["pyright-langserver", "pylsp", "jedi-language-server"],
    "typescript": ["typescript-language-server", "tsserver", "deno"],
}


def _env_override_bin(language: str) -> str | None:
    raw = (os.environ.get(f"AGENT_LSP_{language.upper()}_CMD") or "").strip()
    if not raw:
        return None
    # First token is the executable (same idea as shlex.split in config).
    return raw.split()[0] if raw.split() else None


def _resolve(language: str, bins: list[str]) -> tuple[str | None, str]:
    override = _env_override_bin(language)
    if override:
        path = shutil.which(override)
        if path:
            return path, f"env AGENT_LSP_{language.upper()}_CMD → {path}"
        return None, f"env AGENT_LSP_{language.upper()}_CMD={override!r} not on PATH"
    for name in bins:
        path = shutil.which(name)
        if path:
            return path, f"{name} → {path}"
    return None, f"none of {bins}"


def main() -> int:
    print("LSP PATH smoke (Python + TypeScript/JS minimum)\n")
    ok = True
    for language, bins in CANDIDATES.items():
        path, detail = _resolve(language, bins)
        if path:
            print(f"  OK  {language}: {detail}")
        else:
            ok = False
            print(f"  MISS {language}: {detail}")
    print()
    if ok:
        print("Pass: at least one server per required language is available.")
        return 0
    print("Fail: install servers or set AGENT_LSP_<LANG>_CMD. See docs/runbooks/lsp.md")
    print("  Python:     pip install pyright")
    print("  TypeScript: npm install -g typescript typescript-language-server")
    return 1


if __name__ == "__main__":
    sys.exit(main())

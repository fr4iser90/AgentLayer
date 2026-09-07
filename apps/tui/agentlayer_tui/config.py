"""Where the TUI finds its server URL and credentials."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = "http://127.0.0.1:8088"


def config_path() -> Path:
    root = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(root) / "agentlayer" / "config.toml"


@dataclass
class Settings:
    base_url: str = DEFAULT_BASE_URL
    api_key: str = ""
    model: str = ""
    agent_id: str = ""
    stream: bool = True

    @property
    def ws_url(self) -> str:
        base = self.base_url.rstrip("/")
        if base.startswith("https://"):
            return "wss://" + base[len("https://") :] + "/ws/v1/chat"
        return "ws://" + base.removeprefix("http://") + "/ws/v1/chat"


def load_settings() -> Settings:
    """Config file first, environment second — the environment wins so CI can override."""
    data: dict[str, object] = {}
    path = config_path()
    if path.is_file():
        try:
            data = tomllib.loads(path.read_text("utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            data = {}

    def pick(key: str, env: str, default: str = "") -> str:
        from_env = (os.environ.get(env) or "").strip()
        if from_env:
            return from_env
        value = data.get(key)
        return str(value).strip() if isinstance(value, (str, int, float)) else default

    stream_raw = pick("stream", "AGENTLAYER_STREAM", "true").lower()
    return Settings(
        base_url=pick("base_url", "AGENTLAYER_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        api_key=pick("api_key", "AGENTLAYER_API_KEY"),
        model=pick("model", "AGENTLAYER_MODEL"),
        agent_id=pick("agent_id", "AGENTLAYER_AGENT"),
        stream=stream_raw not in ("0", "false", "no", "off"),
    )


def write_login(key: str, base_url: str, model: str = "") -> Path:
    """Persist the minted key so the next start needs no login."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    managed = ("api_key", "base_url", "model")
    existing = path.read_text("utf-8") if path.is_file() else ""
    kept = [
        line
        for line in existing.splitlines()
        if not line.strip().startswith(managed)
    ]
    header = [f'base_url = "{base_url}"', f'api_key = "{key}"']
    if model:
        header.append(f'model = "{model}"')
    path.write_text("\n".join([*header, *kept]).strip() + "\n", "utf-8")
    path.chmod(0o600)
    return path

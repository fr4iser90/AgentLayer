"""Entry point: ``agentlayer`` (interactive), ``--login`` (mint a key), ``-p`` (one-shot)."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import socket
import sys

from .client import AgentLayerError, RestClient, one_shot
from .config import Settings, load_settings, write_login


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agentlayer",
        description="Terminal client for AgentLayer.",
    )
    p.add_argument("--server", default="", help="base URL, e.g. https://agent.example.com")
    p.add_argument("--model", default="", help="model id (see /models)")
    p.add_argument("--agent", default="", help="chat-surface agent id (default: general)")
    p.add_argument("--login", action="store_true", help="log in, mint an API key, save it")
    p.add_argument("-p", "--prompt", default="", help="run one turn over HTTP and exit")
    p.add_argument("--no-stream", action="store_true", help="disable token streaming")
    return p


async def _login_flow(base_url: str) -> int:
    settings = load_settings()
    if base_url:
        settings.base_url = base_url.rstrip("/")
    rest = RestClient(settings)
    try:
        email = input(f"Email for {settings.base_url}: ").strip()
        password = getpass.getpass("Password: ")
        token = await rest.login(email, password)
        name = f"tui@{socket.gethostname()}"
        key = await rest.mint_api_key(token, name)
        settings.api_key = key
        model = settings.model or await rest.default_model()
    except AgentLayerError as e:
        print(f"Login failed: {e}", file=sys.stderr)
        return 1
    finally:
        await rest.aclose()
    path = write_login(key, settings.base_url, model)
    print(f"Key '{name}' saved to {path} (mode 600).")
    if model:
        print(f"Model set to {model} — change it there or with /model.")
    print("Start with: agentlayer")
    return 0


async def _pick_model(settings: Settings) -> str:
    rest = RestClient(settings)
    try:
        return await rest.default_model()
    finally:
        await rest.aclose()


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.login:
        return asyncio.run(_login_flow(args.server))

    settings = load_settings()
    if args.server:
        settings.base_url = args.server.rstrip("/")
    if args.model:
        settings.model = args.model
    if args.agent:
        settings.agent_id = args.agent
    if args.no_stream:
        settings.stream = False

    if not settings.api_key:
        print(
            "No API key. Run 'agentlayer --login' first "
            "(or set AGENTLAYER_API_KEY).",
            file=sys.stderr,
        )
        return 2

    if not settings.model:
        # The server rejects a chat request with no model and publishes no default of its own.
        try:
            settings.model = asyncio.run(_pick_model(settings))
        except Exception as e:  # noqa: BLE001
            print(f"Could not list models: {e}", file=sys.stderr)
            return 1
        if not settings.model:
            print("No models available — check Admin → Interfaces.", file=sys.stderr)
            return 1

    if args.prompt:
        try:
            asyncio.run(one_shot(settings, args.prompt, print))
        except AgentLayerError as e:
            print(str(e), file=sys.stderr)
            return 1
        return 0

    from .app import AgentLayerTui

    AgentLayerTui(settings).run()
    return 0

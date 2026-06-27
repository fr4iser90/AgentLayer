"""Lifecycle adapter for optional external chat bridges."""
from __future__ import annotations

from apps.backend.infrastructure.integrations import discord_bridge, telegram_bridge


def start_discord_bridge() -> None:
    discord_bridge.start_background()


def stop_discord_bridge() -> None:
    discord_bridge.stop_background()


def start_telegram_bridge() -> None:
    telegram_bridge.start_background()


def stop_telegram_bridge() -> None:
    telegram_bridge.stop_background()

"""
Shipped tool tree: **recursive** scan for ``*.py`` (``TOOLS`` + ``HANDLERS``); see ``app.registry``.

**Layout** (first level under ``plugins/tools/``):

- ``capabilities/`` — ``coding/``, ``filesystem/``, ``knowledge/``, ``browser/``, ``platform/`` (operator,
  scheduler, secrets, tool_factory, friends, …), ``creative/``.
- ``integrations/`` — third-party HTTP APIs (GitHub, Gmail, OpenWeather, web search, image generator, …).
- ``domains/`` — thematic verticals (fishing, hunting, survival, work, …).
- ``productivity/`` — calendar, todos, shopping list, RSS, ideas, pets, clocks, server, ….
- ``agent_created/`` — optional host mount for ``create_tool`` output (see compose / ``AGENT_TOOLS_EXTRA_DIR``).

Admin UI buckets are optional per-module constants ``TOOL_BUCKET`` / ``TOOL_ADMIN_TAGS`` (``tools_meta``).

Extra tools under ``AGENT_TOOLS_EXTRA_DIR`` may use a similar shape (flat or nested ``*.py`` modules).
"""

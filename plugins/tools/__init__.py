"""
Shipped tool tree — recursive scan for ``*.py`` with ``TOOLS`` + ``HANDLERS``.

Layout (by *what the tool is*):

- ``integrations/`` — external APIs (``mail/``, ``github/``, ``weather/``, ``web_search/``, ``friends/``, ``browser/``)
- ``workspace/`` — bound repo (``bind/``, ``files/``, ``shell/``, ``search/``, ``lsp/``, ``planning/``)
- ``platform/`` — AgentLayer infra (``agents/``, ``tasks/``, ``secrets/``, ``scheduler/``, ``tool_help/``, …)
- ``knowledge/`` — ``kb/``, ``memory/``, ``rag/``
- ``personal/`` — dashboard verticals (``shopping/``, ``pets/``, ``tasks/``, …)
- ``creative/`` — ``build/``, ``image_editor/``
- ``outdoor/`` — ``fishing/``, ``hunting/``, ``survival/``
- ``security/`` — ``security_scan/``
- ``agent_created/`` — optional dynamic mount (``AGENT_TOOLS_EXTRA_DIR``)

Each module: ``TOOL_DOMAIN``, optional ``TOOL_PROVIDER``, ``TOOL_CAPABILITIES``.
Helpers: ``apps/backend/domain/`` (not scanned).
"""

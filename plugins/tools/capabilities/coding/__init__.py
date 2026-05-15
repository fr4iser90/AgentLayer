"""Coding tools — workspace-scoped file operations.

All tools are restricted to ``AGENT_CODING_ROOT`` and enforce a path blocklist
to prevent access to system directories or tool modules.

See ``apps/backend/core/config.py`` for configuration:
- ``AGENT_CODING_ENABLED`` — master switch (default true)
- ``AGENT_CODING_ROOT`` — required; the root dir for all coding file ops
- ``AGENT_CODING_MAX_FILE_BYTES`` — size limit (default 2 MB)
- ``AGENT_CODING_PATH_BLOCKLIST`` — never-accessible prefixes
"""

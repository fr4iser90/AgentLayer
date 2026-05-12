"""Bridge module to access backend functions from plugins.

This module can be imported by plugin tools to access workspace context
without dealing with complex import paths.
"""

# Re-export identity functions for plugins
try:
    from apps.backend.domain.identity import get_workspace, get_identity
    HAS_IDENTITY = True
except ImportError:
    get_workspace = None
    get_identity = None
    HAS_IDENTITY = False

__all__ = ["get_workspace", "get_identity", "HAS_IDENTITY"]
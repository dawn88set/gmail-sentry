"""Locate the app's intelligence manifest.

The manifest moved from ``app.yaml`` to ``intelligence.yaml`` (the SDK loads +
validates it at boot); ``app.yaml`` is kept as a legacy fallback for older apps.
Every reader in the backend must accept BOTH names — otherwise an app that ships
only ``intelligence.yaml`` loads nothing (empty engine, empty /api/graph, no
agents/workflows/triggers at runtime). Mirrors clarity-api's MANIFEST_FILENAMES.
"""

import os

# Preference order — intelligence.yaml wins, app.yaml is the legacy fallback.
MANIFEST_FILENAMES = ("intelligence.yaml", "app.yaml")


def _candidate_dirs() -> list:
    backend_dir = os.path.dirname(__file__)
    app_root = os.path.dirname(backend_dir)
    # The manifest is materialized at the app root next to backend/; cover the
    # common working-dir variations too (uvicorn from app root or from backend/).
    return [app_root, os.getcwd(), os.path.join(os.getcwd(), "backend"), backend_dir]


def resolve_manifest_path() -> str | None:
    """Absolute path to the manifest (intelligence.yaml preferred), or None."""
    for name in MANIFEST_FILENAMES:
        for d in _candidate_dirs():
            p = os.path.join(d, name)
            if os.path.isfile(p):
                return p
    return None


def resolve_manifest_name() -> str:
    """Basename of the manifest to load (for loaders that take a filename).
    Falls back to the preferred name when none is present on disk."""
    p = resolve_manifest_path()
    return os.path.basename(p) if p else MANIFEST_FILENAMES[0]

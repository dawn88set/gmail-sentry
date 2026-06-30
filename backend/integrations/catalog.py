"""
Loads the integration catalog (single source of truth) and exposes helpers.

The catalog is `shared/integrations-catalog.json`, forked into every app. It is
also read at plan time by clarity-api, so the instructions shown to the user and
the credentials the code expects always come from the same description.
"""
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

# backend/integrations/catalog.py -> parents[2] == <app_root>
_CATALOG_PATH = (
    Path(__file__).resolve().parents[2] / "shared" / "integrations-catalog.json"
)


@lru_cache(maxsize=1)
def _load() -> Dict[str, Any]:
    path = _CATALOG_PATH
    if not path.exists():
        alt = Path.cwd() / "shared" / "integrations-catalog.json"
        if alt.exists():
            path = alt
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"version": 1, "integrations": []}


def list_integrations() -> List[Dict[str, Any]]:
    return list(_load().get("integrations", []))


def get_integration(integration_id: str) -> Optional[Dict[str, Any]]:
    for entry in list_integrations():
        if entry.get("id") == integration_id:
            return entry
    return None


def app_origin() -> str:
    """Public origin of this deployed app, used to build OAuth redirect URIs."""
    origin = os.getenv("APP_URL") or os.getenv("FRONTEND_URL") or ""
    return origin.rstrip("/")


def redirect_uri(entry: Dict[str, Any]) -> Optional[str]:
    path = entry.get("redirectPath")
    if not path:
        return None
    origin = app_origin()
    return f"{origin}{path}" if origin else None

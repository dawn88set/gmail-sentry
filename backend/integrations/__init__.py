"""
Generic bring-your-own-credentials integration framework.

Storage, encryption, the Settings API, and OAuth machinery here are
integration-agnostic. Per-integration specifics (which credentials, how the user
obtains each one, scopes) live in `shared/integrations-catalog.json`; provider
data clients live in this package (e.g. `gmail_client`).

Generated app code should call these clients and read credentials via this
framework — never read provider keys from environment variables and never
hand-roll OAuth.
"""
from backend.integrations.routes import router

__all__ = ["router"]

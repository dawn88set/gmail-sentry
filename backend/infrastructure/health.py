"""
Health Check Infrastructure

Automatic health check endpoint - users don't need to modify this.
Provides standard health status for monitoring and platform integration.

The endpoint is HONEST about readiness: an app whose manifest (intelligence.yaml)
is PRESENT but failed to load/validate — or loaded but declares no runnable
intelligence (the silent-empty symptom of an SDK↔manifest mismatch) — reports
`unhealthy` + HTTP 503. The platform's post-deploy smoke gate reads this, so a
broken app FAILS to go live instead of serving an empty manifest. A genuinely
manifest-less (legacy) app stays healthy. `backend.main` sets the state after
the v2 boot via `set_readiness()`.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from datetime import datetime
from typing import Any, Dict, Optional

router = APIRouter()


_READINESS: Dict[str, Any] = {
    "ready": True,
    "reason": None,
    "agents": None,
    "workflows": None,
}


def set_readiness(
    ready: bool,
    *,
    reason: Optional[str] = None,
    agents: Optional[int] = None,
    workflows: Optional[int] = None,
) -> None:
    """Record the app's manifest-boot readiness. Called by backend.main once the
    v2 manifest has been loaded (or failed to)."""
    _READINESS.update(ready=ready, reason=reason, agents=agents, workflows=workflows)


def get_readiness() -> Dict[str, Any]:
    return dict(_READINESS)


@router.get("/health")
async def health_check():
    """
    Health check endpoint.

    Required by Clarity platform for app monitoring and orchestration.
    Returns 200 + `healthy` when the app booted its manifest; 503 + `unhealthy`
    + a `reason` when a present manifest failed to load (so the platform blocks
    the deploy instead of shipping an empty app).
    """
    body: Dict[str, Any] = {
        "status": "healthy" if _READINESS["ready"] else "unhealthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "ready": bool(_READINESS["ready"]),
    }
    if _READINESS.get("agents") is not None:
        body["agents"] = _READINESS["agents"]
        body["workflows"] = _READINESS["workflows"]
    if not _READINESS["ready"]:
        body["reason"] = _READINESS["reason"]
        return JSONResponse(status_code=503, content=body)
    return body

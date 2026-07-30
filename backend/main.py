"""
Clarity Agentic App Backend - FastAPI Application

Main FastAPI application with:
- Core API endpoints (health, widget)
- Agent/workflow discovery
- User trigger management
- Execution endpoints
"""

from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import os
import hmac
import logging

from backend.database import get_db, init_db, seed_demo_data, engine
from backend import models
from claritty_sdk import (
    AgentContext,
    WorkflowContext,
    build_graph,
    use_user_context,
)
# v2 manifest-first: agents/workflows/triggers are declared in intelligence.yaml
# and loaded by claritty_sdk.runtime.bootstrap (see _get_boot()). There is no v1
# decorator registry or WorkflowExecutor anymore — one canonical runtime.

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Clarity Agentic App",
    description="AI-powered application with user-configurable triggers",
    version="1.0.0"
)

# --- Widget-data cache (platform speed heuristic) --------------------------
# The dashboard polls GET /api/widget every ~30s and the data tolerates a few
# seconds of staleness. Cache the serialized response per (user, query) in-process
# for a short TTL so warm invocations skip the DB round-trips, and stamp
# Cache-Control so a CDN/browser can reuse it too. App-agnostic (lives here, not in
# the replaceable handler), fail-open, and only touches GET /api/widget. Disable
# with WIDGET_CACHE=off; tune WIDGET_CACHE_TTL (seconds).
import time as _time
from starlette.requests import Request as _Request
from starlette.responses import Response as _Response

_WIDGET_CACHE_ON = os.getenv("WIDGET_CACHE", "on").lower() != "off"
_WIDGET_TTL = float(os.getenv("WIDGET_CACHE_TTL", "10") or 10)
_WIDGET_CC = "public, max-age=10, stale-while-revalidate=20"
_widget_cache: Dict[tuple, tuple] = {}  # (user, query) -> (expiry, body, media_type)


@app.middleware("http")
async def _widget_cache_mw(request: _Request, call_next):
    # Fast path: everything that isn't the widget GET passes straight through.
    if not (
        _WIDGET_CACHE_ON
        and request.method == "GET"
        and request.url.path == "/api/widget"
    ):
        return await call_next(request)

    user = request.headers.get("x-user-id") or ""  # edge-stamped, trusted
    key = (user, request.url.query)
    now = _time.monotonic()

    # Serve from cache without touching the handler / DB.
    if user:
        hit = _widget_cache.get(key)
        if hit and hit[0] > now:
            return _Response(
                content=hit[1],
                media_type=hit[2],
                headers={"Cache-Control": _WIDGET_CC, "X-Claritty-Cache": "hit"},
            )

    resp = await call_next(request)

    # Buffer the body so we can both cache it and re-emit it.
    body = b""
    async for chunk in resp.body_iterator:
        body += chunk

    # Cache only successful, user-scoped responses (never errors / empty user).
    if user and resp.status_code == 200:
        if len(_widget_cache) > 1000:  # cheap unbounded-growth guard
            _widget_cache.clear()
        _widget_cache[key] = (
            now + _WIDGET_TTL,
            body,
            resp.media_type or "application/json",
        )

    headers = dict(resp.headers)
    headers.pop("content-length", None)  # body re-set below
    headers["Cache-Control"] = _WIDGET_CC
    headers["X-Claritty-Cache"] = "miss"
    return _Response(
        content=body,
        status_code=resp.status_code,
        headers=headers,
        media_type=resp.media_type,
    )

# Include infrastructure routers (health checks, etc.)
from backend.infrastructure import health_router
app.include_router(health_router)

# Auto-include app-specific routers from backend/routes/*.py (each exposes a
# module-level `router = APIRouter()`). Registered HERE — before the inline
# example endpoints further down — so a generated backend/routes/app.py can
# OVERRIDE them: FastAPI dispatches to the FIRST route registered for a given
# path+method. Generated apps overwrite backend/routes/app.py with their own
# data endpoints; the inline examples below remain as shadowed fallbacks.
import importlib as _importlib
import pkgutil as _pkgutil
from fastapi import APIRouter as _APIRouter

try:
    from backend import routes as _routes_pkg

    for _m in _pkgutil.iter_modules(_routes_pkg.__path__):
        try:
            _mod = _importlib.import_module(f"backend.routes.{_m.name}")
            _router = getattr(_mod, "router", None)
            if isinstance(_router, _APIRouter):
                app.include_router(_router)
                logger.info(f"Included app router: backend.routes.{_m.name}")
        except Exception as _e:  # noqa: BLE001
            logger.error(
                f"Failed to include app router backend.routes.{_m.name}: {_e}"
            )
except Exception as _e:  # noqa: BLE001
    logger.warning(f"No app routers package to include: {_e}")

# Connecting an integration is PLATFORM-OWNED: the frontend postMessages
# `claritty:connect-integration` to the host, which runs its own OAuth gate, and
# the broker holds the token. The app only reads connection *status*, via
# GET /api/integrations/required (backend/routes/integrations_setup.py). There is
# deliberately no in-app credential-write or oauth/callback endpoint here.

# Triggers are managed by the Claritty platform; the app only exposes the
# /internal dispatch endpoints below (no in-app scheduler).

# Configure CORS
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3200")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3000"],  # Include Clarity platform
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Dependency: Get current user ID — fail-closed in production.
def get_current_user(
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    x_claritty_auth: Optional[str] = Header(None, alias="X-Claritty-Auth"),
    authorization: Optional[str] = Header(None),
) -> str:
    """
    Trusted per-user identity. Mirrors backend.security.require_user (defense-in-depth)
    so app endpoints can't be tricked by a forged X-User-ID.

    Production (ALB_AUTH_SECRET set): identity MUST come from the Claritty edge,
    which validates the user's JWT and injects X-User-Id PLUS the X-Claritty-Auth
    admission secret. We re-verify that secret here; a request that bypasses the
    edge (forging X-User-Id, or presenting a Bearer token) is rejected. Fail closed —
    NEVER trust a bare X-User-Id or a Bearer token as identity in production.

    Local development only (no ALB secret): accept X-User-Id or a Bearer token for
    convenience, and fall back to "dev-user" when explicitly running in dev.
    """
    alb_secret = os.getenv("ALB_AUTH_SECRET", "")

    # Production: require the edge-stamped admission secret.
    if alb_secret:
        if not x_claritty_auth or not hmac.compare_digest(x_claritty_auth, alb_secret):
            raise HTTPException(
                status_code=403,
                detail="Request did not originate from the Claritty edge.",
            )
        if not x_user_id:
            raise HTTPException(status_code=401, detail="Authentication required.")
        return x_user_id

    # Local development only (no ALB secret).
    if x_user_id:
        return x_user_id
    if authorization:
        return authorization.replace("Bearer ", "").strip()
    if os.getenv("NODE_ENV", "").lower() in ("development", "dev", "local"):
        return "dev-user"

    raise HTTPException(
        status_code=401,
        detail="Authentication required.",
    )


# ============================================================================
# CORE ENDPOINTS
# ============================================================================
# Note: the health endpoint is provided by backend/infrastructure/health.py.
# The app's data endpoints — including the REQUIRED `GET /api/widget` — live in
# backend/routes/app.py (auto-included above). Generated apps overwrite that
# file with their own routes; main.py stays generic (discovery + execution).


# ============================================================================
# DISCOVERY ENDPOINTS
# ============================================================================

def _manifest_agents():
    """The loaded v2 manifest's agents (or [] if no manifest booted)."""
    boot = _get_boot()
    return list(boot.manifest.agents) if boot is not None else []


def _agent_to_dict(a, *, detail: bool = False) -> Dict[str, Any]:
    """Map a v2 manifest AgentDecl to the discovery response shape."""
    out = {
        "id": a.id,
        "name": getattr(a, "name", None) or a.id,
        "description": a.description,
        "category": None,
        "inputs": a.input,
        "outputs": a.output,
        "integrations": [
            {"service": svc, "required": True, "auth_type": None}
            for svc in (a.integrations or [])
        ],
    }
    if detail:
        out["timeout"] = a.timeout
        out["tools"] = list(a.tools or [])
        out["model"] = a.model
    return out


@app.get("/api/agents")
async def list_agents():
    """List the app's agents, read from the v2 manifest (intelligence.yaml)."""
    return {"agents": [_agent_to_dict(a) for a in _manifest_agents()]}


@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get one agent's metadata, read from the v2 manifest."""
    agent = next((a for a in _manifest_agents() if a.id == agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _agent_to_dict(agent, detail=True)


@app.get("/api/workflows")
async def list_workflows():
    """List the app's workflows, declared in the v2 manifest (intelligence.yaml)."""
    return {"workflows": _workflows_from_app_yaml()}


def _workflows_from_app_yaml() -> list:
    """Read v2 workflow declarations from the manifest (id/name/steps). Best-effort:
    returns [] if the manifest is absent or unreadable. Accepts intelligence.yaml
    (preferred) or app.yaml (legacy)."""
    try:
        import yaml  # FastAPI app already depends on pyyaml via the SDK
        from backend.manifest_path import resolve_manifest_path

        path = resolve_manifest_path()
        if not path:
            return []
        with open(path, "r", encoding="utf-8") as fh:
            manifest = yaml.safe_load(fh) or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"could not read manifest workflows: {exc}")
        return []
    out = []
    for wf in manifest.get("workflows") or []:
        if not isinstance(wf, dict) or not wf.get("id"):
            continue
        out.append(
            {
                "id": wf["id"],
                "name": wf.get("name") or wf["id"],
                "description": wf.get("description", ""),
                "execution_mode": "sequential",
                "steps": [
                    {"agent_id": s.get("agent"), "output_key": s.get("id")}
                    for s in (wf.get("steps") or [])
                    if isinstance(s, dict)
                ],
            }
        )
    return out


@app.get("/api/trigger-templates")
async def list_trigger_templates():
    """List the app's trigger templates, declared in the v2 manifest
    (intelligence.yaml). Users create instances from these on the platform."""
    boot = _get_boot()
    triggers = list(boot.manifest.triggers) if boot is not None else []

    def _cfg(field) -> Dict[str, Any]:
        ftype = getattr(field, "type", None)
        return {
            "key": getattr(field, "key", None),
            "label": getattr(field, "label", None),
            "type": getattr(ftype, "value", ftype),
            "required": getattr(field, "required", False),
            "default": getattr(field, "default", None),
            "options": getattr(field, "options", None),
            "validation": getattr(field, "validation", None),
        }

    out = []
    for t in triggers:
        ttype = getattr(t, "type", None)
        out.append(
            {
                "id": t.id,
                "name": getattr(t, "name", None) or t.id,
                "description": t.description,
                "template_type": getattr(ttype, "value", ttype),
                "workflow_id": getattr(t, "workflow", None),
                "agent_id": getattr(t, "agent", None),
                "category": None,
                "supported_schedules": [
                    getattr(s, "value", s) for s in (getattr(t, "supported_schedules", None) or [])
                ],
                "config_fields": [_cfg(f) for f in (getattr(t, "config_fields", None) or [])],
                "max_instances_per_user": getattr(t, "max_instances_per_user", None),
            }
        )
    return {"templates": out}


@app.get("/api/graph")
async def get_graph():
    """The app's agent/workflow/trigger graph (v1 contract) for the Claritty
    canvas: nodes (agents + triggers) + edges (agent→agent from input_from,
    trigger→entry-agent). Single source of truth — identical for manual and
    generated apps, served live from the SDK registries."""
    return build_graph()


# ============================================================================
# EXECUTION ENDPOINTS
# ============================================================================

@app.post("/api/agents/{agent_id}/execute")
async def execute_agent(
    agent_id: str,
    input_data: Dict[str, Any],
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Execute a single agent with provided input data.
    """
    # Get user integrations
    integrations = {}
    user_integrations = db.query(models.UserIntegration).filter(
        models.UserIntegration.user_id == user_id,
        models.UserIntegration.is_active == True
    ).all()

    for integration in user_integrations:
        integrations[integration.service] = integration.credentials

    # Per-agent user context (the platform's "how to do your job" instructions)
    # arrives alongside the inputs; pull it out and bind it so the SDK injects
    # it into the agent's LLM system prompt.
    user_context = input_data.pop("user_context", "") if isinstance(input_data, dict) else ""

    # The Run button / trigger sends only the agent's own inputs, not the caller
    # identity. Inject the authenticated user_id so an agent whose manifest input
    # declares `user_id` (the common case) passes run_agent's input validation and
    # scopes its writes to the caller — mirrors _run_workflow's injection.
    if isinstance(input_data, dict):
        input_data.setdefault("user_id", user_id)

    context = AgentContext(
        user_id=user_id,
        input_data=input_data,
        integrations=integrations,
        metadata={},
        user_context=user_context,
    )

    # v2 manifest agent → run via the SDK tool-loop (`run_agent`), the SAME path
    # the hosted WorkflowEngine drives per step. The agent defines a
    # `system_prompt`/`prompt_file` (no `execute()`); run_agent drives the loop.
    boot = _get_boot()
    if boot is None or not any(
        getattr(a, "id", None) == agent_id for a in (boot.manifest.agents or [])
    ):
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        from claritty_sdk.runtime.tool_loop import run_agent
        result = await run_agent(
            manifest=boot.manifest,
            agent_id=agent_id,
            user_input=input_data if isinstance(input_data, dict) else {},
            agent_context=context,
            integration_resolver=lambda svc: integrations.get(svc),
        )
        return {
            "success": True,
            "data": result.output,
            "error": None,
            "metadata": {
                "final_text": result.final_text,
                "iterations": result.iterations,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Agent execution failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Agent execution failed: {str(e)}"
        )


# ============================================================================
# INTERNAL TRIGGER DISPATCH (platform → app)
# ============================================================================
# The Claritty platform owns trigger instances + scheduling and dispatches due
# work here (see clarity-api/src/modules/triggers/SEED_CONTRACT.md). Auth is the
# platform↔app shared secret (X-Claritty-Internal); the ALB also gates these on
# X-Claritty-Auth at the edge. Never reachable by end users directly.


def verify_internal_dispatch(
    x_claritty_internal: Optional[str] = Header(None, alias="X-Claritty-Internal"),
) -> None:
    """Reject unless the platform's shared internal secret matches. When no
    secret is configured (local dev) we allow, since the platform always sets
    it in production."""
    expected = os.getenv("CLARITY_INTERNAL_SECRET")
    if expected and x_claritty_internal != expected:
        raise HTTPException(status_code=401, detail="Invalid internal dispatch secret")


def _load_user_integrations(db: Session, user_id: str) -> Dict[str, Any]:
    integrations: Dict[str, Any] = {}
    rows = db.query(models.UserIntegration).filter(
        models.UserIntegration.user_id == user_id,
        models.UserIntegration.is_active == True,
    ).all()
    for row in rows:
        integrations[row.service] = row.credentials
    return integrations


# --- v2 manifest execution (intelligence.yaml workflows) ----------------------
# Both the platform AND a local "run now" execute through here. Workflows are
# declared in intelligence.yaml (handlers in backend/agents|custom/) and run via
# the SDK WorkflowEngine — the SAME engine the platform uses — so a local trigger
# never diverges from how the app is managed when hosted. The /internal/* contract
# is unchanged.
_BOOT = None
_BOOT_TRIED = False
# Set when a manifest FILE is present but failed to load/validate, or loaded but
# declares no runnable intelligence (0 agents AND 0 workflows). Drives readiness
# (GET /health → 503) so a broken app never silently serves an empty manifest.
_BOOT_ERROR = None


def _maybe_fetch_remote_manifest():
    """Manifest hot-reload: when ``CLARITY_MANIFEST_SOURCE=remote``, fetch the
    app's CURRENT intelligence.yaml (+ prompt side-files) from the platform into
    ``/tmp`` and return that dir, so a pure-manifest edit applies on this cold
    start with NO image rebuild. Best-effort — returns None on any issue and the
    caller falls back to the manifest bundled in the image. Returns None
    immediately (no-op) unless the platform opted the app in."""
    if os.getenv("CLARITY_MANIFEST_SOURCE") != "remote":
        return None
    app_id = os.getenv("CLARITY_APP_ID")
    secret = os.getenv("CLARITY_INTERNAL_SECRET")
    base = (
        os.getenv("CLARITTY_PLATFORM_URL")
        or os.getenv("CLARITY_PLATFORM_URL")
        or ""
    ).rstrip("/")
    if not (app_id and secret and base):
        return None
    try:
        import json
        import urllib.request

        url = f"{base}/internal/apps/{app_id}/manifest-bundle"
        req = urllib.request.Request(
            url, headers={"X-Claritty-Internal": secret}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
        out_dir = "/tmp/claritty-manifest"
        os.makedirs(out_dir, exist_ok=True)
        manifest_name = data.get("filename") or "intelligence.yaml"
        with open(os.path.join(out_dir, manifest_name), "w") as f:
            f.write(data.get("intelligenceYaml") or "")
        # Prompt side-files, relative paths preserved, so the SDK resolves them
        # consistently whether it keys off the manifest dir or the app root.
        for rel, content in (data.get("files") or {}).items():
            dest = os.path.join(out_dir, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w") as f:
                f.write(content or "")
        logger.info(f"manifest hot-reload: fetched remote manifest → {out_dir}")
        return out_dir
    except Exception as e:  # any failure → use the bundled manifest
        logger.warning(f"remote manifest fetch failed ({e}); using bundled.")
        return None


def _get_boot():
    global _BOOT, _BOOT_TRIED, _BOOT_ERROR
    if _BOOT_TRIED:
        return _BOOT
    _BOOT_TRIED = True
    try:
        from claritty_sdk.runtime.bootstrap import load as _bootstrap_load
        from backend.manifest_path import resolve_manifest_name

        # Manifest hot-reload: prefer a freshly-fetched manifest from the platform
        # (so a pure-manifest edit applies on this cold start, no rebuild). Falls
        # back to the image-bundled manifest when not opted in / on any error.
        remote_dir = _maybe_fetch_remote_manifest()
        # Load the app's manifest by its ACTUAL name — intelligence.yaml for new
        # apps, app.yaml legacy. Hardcoding "intelligence.yaml" loaded NOTHING for an
        # intelligence.yaml app (empty engine → empty /api/graph → no agents run).
        manifest_arg = remote_dir or resolve_manifest_name()
        _BOOT = _bootstrap_load(manifest_arg)
        # Fail LOUD on the silent-empty symptom: a manifest that "loads" but yields
        # zero agents AND zero workflows is almost always an SDK↔manifest mismatch
        # (an older claritty-sdk dropped fields, or extra="forbid" rejected part of
        # it). Serving that as a healthy-but-empty app is exactly the failure this
        # guards against — mark it not-ready instead.
        n_agents = len(getattr(_BOOT.manifest, "agents", None) or [])
        n_workflows = len(getattr(_BOOT.manifest, "workflows", None) or [])
        if n_agents == 0 and n_workflows == 0:
            _BOOT_ERROR = (
                f"manifest '{manifest_arg}' loaded but declares 0 agents and 0 "
                "workflows — likely an SDK↔manifest version mismatch (check that "
                "claritty-sdk supports every field in intelligence.yaml)."
            )
            logger.error(f"❌ {_BOOT_ERROR}")
        else:
            logger.info(
                f"v2 manifest engine ready ({manifest_arg}): "
                f"{n_agents} agents, {n_workflows} workflows."
            )
    except Exception as e:
        _BOOT = None
        # Distinguish a genuinely manifest-LESS (legacy) app — which is fine and
        # stays healthy — from a manifest that is PRESENT but failed to load. The
        # latter is a real defect (bad YAML / SDK rejected a field) and must fail
        # loud so the deploy is blocked rather than shipping an empty app.
        manifest_present = False
        try:
            from backend.manifest_path import resolve_manifest_path

            manifest_present = bool(resolve_manifest_path())
        except Exception:
            manifest_present = False
        if manifest_present:
            _BOOT_ERROR = f"manifest present but failed to load: {e}"
            logger.error(f"❌ {_BOOT_ERROR}")
        else:
            logger.warning(f"v2 manifest engine unavailable (no manifest): {e}")
    return _BOOT


def _manifest_has_workflow(boot, workflow_id: str) -> bool:
    try:
        return any(
            getattr(w, "id", None) == workflow_id
            for w in (boot.manifest.workflows or [])
        )
    except Exception:
        return False


async def _run_workflow(
    db: Session,
    *,
    workflow_id: str,
    user_id: str,
    trigger_data: Dict[str, Any],
    agent_context: Optional[Dict[str, Any]] = None,
    workflow_run_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Run a workflow through the v2 manifest engine (the SAME engine the
    platform uses, so a local 'run now' never diverges from hosting).

    ``workflow_run_id`` is the platform-pre-allocated WorkflowRun id. When set,
    the engine reports each step (checkpoint) + completion back to the platform,
    so the run + per-agent history actually appear in the UI. Without it the run
    executes but stays invisible (the platform row sits ``pending`` forever)."""
    boot = _get_boot()
    if boot is None or not _manifest_has_workflow(boot, workflow_id):
        raise HTTPException(
            status_code=404, detail=f"Workflow '{workflow_id}' not found"
        )
    inputs = dict(trigger_data or {})
    inputs.pop("agent_context", None)
    # A workflow that declares inputs.user_id (and steps that reference
    # ${input.user_id}) would otherwise fail input validation + raise an
    # ExpressionError on a manual Run / trigger dispatch that sends no body
    # (0 runs). The caller's identity is authenticated here — supply it.
    inputs.setdefault("user_id", user_id)
    result = await boot.engine.run(
        workflow_id,
        inputs=inputs,
        trigger=inputs,
        user_id=user_id,
        workflow_run_id=workflow_run_id,
        idempotency_key=idempotency_key,
    )
    status = getattr(result, "status", "")
    # Return the per-step results too. The platform records them on the
    # WorkflowRun synchronously from THIS response, so per-agent run history
    # shows up WITHOUT relying on the async checkpoint callbacks (which post to
    # the app's CLARITTY_PLATFORM_URL — possibly a different platform than the one
    # that created the run row). started/ended are epoch seconds → ms.
    steps = []
    for s in getattr(result, "steps", []) or []:
        steps.append(
            {
                "id": getattr(s, "id", None),
                "status": getattr(s, "status", None),
                "output": getattr(s, "output", None),
                "error": getattr(s, "error", None),
                "startedAt": int((getattr(s, "started_at", 0) or 0) * 1000),
                "endedAt": int((getattr(s, "ended_at", 0) or 0) * 1000),
            }
        )
    return {
        "workflow_id": workflow_id,
        "success": status == "success",
        "outputs": getattr(result, "outputs", {}) or {},
        "error": getattr(result, "error", None),
        "steps": steps,
    }


async def _run_workflow_for_trigger(
    db: Session,
    *,
    workflow_id: str,
    user_id: str,
    trigger_data: Dict[str, Any],
    workflow_run_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    return await _run_workflow(
        db,
        workflow_id=workflow_id,
        user_id=user_id,
        trigger_data=trigger_data,
        workflow_run_id=workflow_run_id,
        idempotency_key=idempotency_key,
    )


@app.post("/internal/run-due-triggers")
async def run_due_triggers(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    _: None = Depends(verify_internal_dispatch),
):
    """Run a platform-dispatched batch of due SCHEDULE instances.

    The dispatcher records the HTTP status as the batch outcome, so we only
    fail (500) when EVERY instance errored; otherwise we report per-instance.
    """
    instances = payload.get("instances") or []
    results = []
    any_ok = False
    for inst in instances:
        instance_id = inst.get("instanceId")
        try:
            r = await _run_workflow_for_trigger(
                db,
                workflow_id=inst.get("workflowId"),
                user_id=inst.get("userId"),
                trigger_data=inst.get("config") or {},
                workflow_run_id=inst.get("workflowRunId"),
                idempotency_key=inst.get("idempotencyKey"),
            )
            ok = bool(r.get("success"))
            any_ok = any_ok or ok
            # Echo the run id + per-step results so the platform records run
            # history from THIS synchronous response (the async checkpoint
            # callbacks may target a different/unreachable platform).
            results.append(
                {
                    "instanceId": instance_id,
                    "workflowRunId": inst.get("workflowRunId"),
                    "success": ok,
                    "error": r.get("error"),
                    "outputs": r.get("outputs", {}),
                    "steps": r.get("steps", []),
                }
            )
        except Exception as e:
            logger.error(f"run-due-triggers: instance {instance_id} failed: {e}")
            results.append(
                {
                    "instanceId": instance_id,
                    "workflowRunId": inst.get("workflowRunId"),
                    "success": False,
                    "error": str(e),
                }
            )
    if instances and not any_ok:
        raise HTTPException(status_code=500, detail="all due triggers failed")
    return {"ok": True, "results": results}


@app.post("/internal/trigger-webhook")
async def run_trigger_webhook(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    _: None = Depends(verify_internal_dispatch),
):
    """Run the workflow mapped to a webhook trigger. The inbound webhook
    headers + body are exposed to the workflow under `trigger_data['webhook']`,
    alongside the instance's configured fields."""
    workflow_id = payload.get("workflowId")
    user_id = payload.get("userId")
    if not workflow_id or not user_id:
        raise HTTPException(
            status_code=400, detail="workflowId and userId are required"
        )
    trigger_data = {
        **(payload.get("config") or {}),
        "webhook": {
            "headers": payload.get("headers") or {},
            "body": payload.get("body"),
        },
    }
    result = await _run_workflow_for_trigger(
        db,
        workflow_id=workflow_id,
        user_id=user_id,
        trigger_data=trigger_data,
        workflow_run_id=payload.get("workflowRunId"),
        idempotency_key=payload.get("idempotencyKey"),
    )
    if not result.get("success"):
        raise HTTPException(
            status_code=500, detail=result.get("error") or "workflow failed"
        )
    return {"ok": True, "outputs": result.get("outputs", {})}


@app.post("/api/workflows/{workflow_id}/execute")
async def execute_workflow(
    workflow_id: str,
    input_data: Optional[Dict[str, Any]] = None,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Execute a workflow immediately.

    Creates execution record and runs workflow synchronously.
    Returns execution results.
    """
    # Get workflow metadata
    logger.info(f"Starting workflow execution: {workflow_id}")

    # Per-agent user context map (agentId -> instructions) travels in the body
    # under `agent_context`; the rest of the body is the workflow trigger data.
    body = dict(input_data or {})
    agent_context = body.pop("agent_context", {}) or {}
    # Platform-pre-allocated run id (canvas direct-run) — thread it through so the
    # run + per-agent steps report back and show in the UI, same as a trigger.
    workflow_run_id = body.pop("workflowRunId", None)
    idempotency_key = body.pop("idempotencyKey", None)

    # Run via the v2 manifest engine when the workflow is in intelligence.yaml (same engine
    # the platform uses), else the legacy v1 executor. Measure duration here — the
    # executor's return shape varies and may omit `duration_seconds`.
    started_at = datetime.utcnow()
    try:
        result = await _run_workflow(
            db,
            workflow_id=workflow_id,
            user_id=user_id,
            trigger_data=body,
            agent_context=agent_context,
            workflow_run_id=workflow_run_id,
            idempotency_key=idempotency_key,
        )

        success = bool(result.get("success", True))
        duration = result.get("duration_seconds")
        if duration is None:
            duration = (datetime.utcnow() - started_at).total_seconds()

        # Create execution record
        execution = models.WorkflowExecution(
            workflow_id=workflow_id,
            user_id=user_id,
            status="completed" if success else "failed",
            input_data=input_data or {},
            output_data=result.get("outputs", {}),
            error_message=result.get("error"),
            started_at=started_at,
            completed_at=datetime.utcnow(),
            duration_seconds=int(duration),
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)

        logger.info(f"Workflow execution completed: {execution.id} (success={success})")

        return {
            "execution_id": execution.id,
            "workflow_id": workflow_id,
            "status": execution.status,
            "success": success,
            "outputs": result.get("outputs", {}),
            "error": result.get("error"),
            "duration_seconds": int(duration),
            # Per-step results so the platform records run history synchronously
            # (independent of the async checkpoint callbacks).
            "steps": result.get("steps", []),
        }

    except Exception as e:
        logger.error(f"Workflow execution failed: {workflow_id} - {e}")

        # Create failed execution record
        execution = models.WorkflowExecution(
            workflow_id=workflow_id,
            user_id=user_id,
            status="failed",
            input_data=input_data or {},
            error_message=str(e),
            started_at=started_at,
            completed_at=datetime.utcnow(),
            duration_seconds=0
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)

        raise HTTPException(status_code=500, detail=f"Workflow execution failed: {str(e)}")


@app.get("/api/workflows/executions/{execution_id}")
async def get_workflow_execution(
    execution_id: str,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get workflow execution status and results.
    """
    execution = db.query(models.WorkflowExecution).filter(
        models.WorkflowExecution.id == execution_id,
        models.WorkflowExecution.user_id == user_id
    ).first()

    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    return {
        "id": execution.id,
        "workflow_id": execution.workflow_id,
        "status": execution.status,
        "input_data": execution.input_data,
        "output_data": execution.output_data,
        "error_message": execution.error_message,
        "started_at": execution.started_at.isoformat(),
        "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
        "duration_seconds": execution.duration_seconds
    }


# ============================================================================
# STARTUP/SHUTDOWN EVENTS
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """
    Initialize database and load agents/workflows/triggers on startup.
    """
    logger.info("🚀 Starting Clarity Agentic App...")

    # Initialize database
    logger.info("📊 Initializing database...")
    init_db()

    # Fabricated starter rules + sample alerts, so the dashboard and the three
    # widget sizes show varied content before Gmail is connected. Local dev and
    # screenshot fixtures only — OFF by default, and deliberately an explicit
    # opt-in rather than an ENVIRONMENT check, so a preview deploy can't turn it
    # on by accident and write placeholder rows to a production database.
    if os.getenv("SEED_DEMO_DATA", "").strip().lower() in ("1", "true", "yes"):
        logger.info("🌱 SEED_DEMO_DATA is set — seeding demo content")
        seed_demo_data()

    # Auto-discover and register all components
    logger.info("🤖 Auto-discovering agents, workflows, and triggers...")
    try:
        from backend.infrastructure import discover_and_register_components
        discover_and_register_components()
    except Exception as e:
        logger.error(f"Failed to discover components: {e}")
        raise

    # Eagerly load the v2 manifest so build_graph() (and GET /api/graph) reflect
    # the manifest's agents/tools/integrations + YAML workflows/triggers. Without
    # this, /api/graph could be hit before the first workflow run (which lazy-loads
    # boot) and serve an empty graph — which the platform then caches.
    try:
        _get_boot()
    except Exception as _e:
        logger.warning(f"⚠️  v2 manifest eager-load skipped: {_e}")

    # Log the manifest's components (the single source of truth in v2) + publish
    # readiness so GET /health is HONEST: a present-but-broken manifest reports
    # 503 and the platform's post-deploy smoke gate blocks the deploy.
    from backend.infrastructure.health import set_readiness

    boot = _get_boot()
    if boot is not None and _BOOT_ERROR is None:
        m = boot.manifest
        n_agents, n_workflows = len(m.agents or []), len(m.workflows or [])
        logger.info(f"✅ Manifest: {n_agents} agents")
        logger.info(f"✅ Manifest: {n_workflows} workflows")
        logger.info(f"✅ Manifest: {len(m.triggers or [])} trigger templates")
        set_readiness(True, agents=n_agents, workflows=n_workflows)
    elif _BOOT_ERROR is not None:
        # Manifest present but broken (failed load, or loaded empty) → NOT ready.
        logger.error(f"❌ App NOT READY: {_BOOT_ERROR}")
        set_readiness(False, reason=_BOOT_ERROR, agents=0, workflows=0)
    else:
        # Genuinely manifest-less (legacy) app — fine, stays ready.
        logger.warning("⚠️  No v2 manifest loaded — /api/agents will be empty.")
        set_readiness(True, agents=0, workflows=0)

    # Cache the graph for the platform's build-time / unreachable fallback
    # (same build_graph() the /api/graph endpoint serves on demand). This is a
    # COLD-START hot path: on Lambda the task dir is READ-ONLY, so the write
    # always failed (and build_graph() ran for nothing) on every cold init.
    # Only do the work where the FS is writable AND the cache is missing — so
    # it's written once at build/first-run and skipped entirely on Lambda.
    try:
        import os as _os
        from pathlib import Path as _Path
        _cache_dir = _Path(__file__).parent / ".clarity"
        _graph_file = _cache_dir / "graph.json"
        if not _graph_file.exists() and _os.access(_cache_dir.parent, _os.W_OK):
            import json as _json
            _cache_dir.mkdir(exist_ok=True)
            _graph_file.write_text(_json.dumps(build_graph(), indent=2))
            logger.info("✅ Wrote graph cache to backend/.clarity/graph.json")
    except Exception as _e:
        logger.warning(f"⚠️  Failed to write graph cache: {_e}")

    # Triggers are owned by the Claritty platform: it stores instances, computes
    # schedules, and dispatches due work to the /internal endpoints below. No
    # in-process scheduler runs here (it wouldn't survive on Lambda anyway).
    logger.info("✅ Clarity Agentic App ready!")


@app.on_event("shutdown")
async def shutdown_event():
    """
    Cleanup on shutdown.
    """
    logger.info("👋 Shutting down Clarity Agentic App...")
    logger.info("✅ Shutdown complete")


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    debug = os.getenv("DEBUG", "false").lower() == "true"

    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info"
    )

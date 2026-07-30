"""
Smoke tests — verify the app's core wiring without needing a DB or network.

These assert that the v2 manifest (intelligence.yaml) loads and declares the
seed's example agent + workflow, and that the platform-facing graph builds from
it. They give the `Test Backend` CI job real coverage and clear the "no tests
directory" warning.
"""


def _load_manifest():
    from claritty_sdk.runtime.bootstrap import load as _bootstrap_load
    from backend.manifest_path import resolve_manifest_name

    return _bootstrap_load(resolve_manifest_name()).manifest


def test_manifest_declares_components():
    m = _load_manifest()

    assert len(m.agents or []) >= 1
    assert len(m.workflows or []) >= 1
    # The seed ships one example trigger; triggers are platform-managed.
    assert len(m.triggers or []) >= 1


def test_graph_builds():
    from claritty_sdk.graph import build_graph_from_manifest

    graph = build_graph_from_manifest(_load_manifest())

    assert isinstance(graph, dict)
    assert "nodes" in graph and "edges" in graph
    assert len(graph["nodes"]) >= 1


def test_no_in_app_credential_or_oauth_surface():
    """Connecting is PLATFORM-OWNED.

    The app reads connection *status* and nothing else — it must never expose an
    endpoint that accepts credentials or runs an OAuth code exchange. The seed
    shipped one (backend/integrations/routes.py); it was removed because nothing
    called it and it was a live credential-write surface. This guards the
    deletion: it fails if that router, or anything shaped like it, comes back.
    """
    from backend.main import app

    paths = {r.path for r in app.routes if getattr(r, "path", "").startswith("/api/integrations")}

    # The two read-only routes the frontend actually calls.
    assert "/api/integrations/required" in paths
    assert "/api/integrations/slack/channels" in paths

    # Nothing else. In particular no catch-all /{integration_id}, which would
    # also shadow /required depending on registration order.
    assert paths == {"/api/integrations/required", "/api/integrations/slack/channels"}, (
        f"unexpected /api/integrations routes: {sorted(paths)}"
    )

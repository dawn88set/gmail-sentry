"""Being able to tell which build is running.

The worst failure this project hit was not a bug in the app: it was that nobody
could tell WHICH BUILD was serving. The platform reported every deploy as
successful, its log endpoint returns placeholder text, and the running API was a
month older than the UI in front of it. A day went into establishing something
the app could have simply stated.
"""
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import build_id


def _version():
    return TestClient(app).get("/api/version").json()


def test_it_answers_without_a_session_or_a_database():
    """The one time this matters is when things are broken. Requiring auth, a
    database or an integration would make it useless exactly then."""
    r = TestClient(app).get("/api/version")
    assert r.status_code == 200


def test_it_names_the_endpoints_that_actually_exist():
    """A missing endpoint is the symptom people notice — "the list won't load".
    This says so directly instead of leaving them to infer it from a 404."""
    routes = _version()["routes"]
    assert "/api/worklist" in routes
    assert "/api/accounts" in routes
    assert all(p.startswith("/api/") for p in routes)


def test_the_fingerprint_is_stable_across_calls():
    """It has to be comparable; a value that changed per request would prove
    nothing about which code is loaded."""
    assert _version()["fingerprint"] == _version()["fingerprint"]


def test_the_fingerprint_changes_when_the_code_changes(tmp_path, monkeypatch):
    """The whole point: a different tree must produce a different answer."""
    build_id.source_fingerprint.cache_clear()
    first = build_id.source_fingerprint()

    extra = tmp_path / "backend"
    extra.mkdir()
    (extra / "zz_new_module.py").write_text("# a file this build did not have\n")
    monkeypatch.setattr(build_id, "_BACKEND_DIR", str(extra))
    build_id.source_fingerprint.cache_clear()

    assert build_id.source_fingerprint() != first
    build_id.source_fingerprint.cache_clear()


def test_the_route_fingerprint_reflects_the_api_surface():
    v = _version()
    assert v["route_count"] == len(v["routes"])
    assert len(v["routes_fingerprint"]) == 12


def test_the_hash_is_reproducible_outside_python(tmp_path, monkeypatch):
    """The CLI computes this same hash before a deploy so the two can be
    compared — "did my code reach production" becomes a comparison instead of a
    guess. That only works if the ordering is something another language can
    reproduce without reimplementing os.walk, so the contract is: collect the
    relative paths, sort them lexicographically, hash path-then-bytes.
    """
    import hashlib
    import os

    root = tmp_path / "backend"
    (root / "services").mkdir(parents=True)
    (root / "z_last.py").write_text("z\n")
    (root / "a_first.py").write_text("a\n")
    (root / "services" / "mid.py").write_text("m\n")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "ignored.py").write_text("nope\n")

    monkeypatch.setattr(build_id, "_BACKEND_DIR", str(root))
    build_id.source_fingerprint.cache_clear()
    got = build_id.source_fingerprint()
    build_id.source_fingerprint.cache_clear()

    # The independent restatement of the contract — flat, sorted, path+bytes.
    rels = sorted(["a_first.py", "z_last.py", os.path.join("services", "mid.py")])
    h = hashlib.sha256()
    for rel in rels:
        h.update(rel.encode())
        h.update((root / rel).read_bytes())

    assert got == h.hexdigest()[:16]
    # …and the cache directory really was skipped.
    assert "nope" not in "".join(rels)

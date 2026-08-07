"""What code is actually running — answerable from outside the container.

The hardest failure this app hit was not a bug in it. It was being unable to
tell WHICH BUILD was serving: the platform reported every deploy as successful,
its logs endpoint returns placeholder text, and the running API turned out to be
a month older than the UI in front of it. That cost a day, and nothing in the
app could have answered the question.

So the app answers it itself. Two facts, both derived at runtime from the code
that is actually loaded — no build step, no git in the image, nothing the deploy
pipeline has to cooperate with:

  * `fingerprint` — a hash of every backend source file. Compute the same hash
    on a working tree and the two either match or they don't. That is the whole
    diagnosis, in one comparison.
  * `routes` — the API surface that is really registered. A missing endpoint is
    the symptom people actually notice ("the list won't load"), and this names
    it directly rather than leaving them to infer it from a 404.
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime
from functools import lru_cache
from typing import Any, Dict, List

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Directories whose contents say nothing about which build this is.
_SKIP = {"__pycache__", "tests", "migrations", ".pytest_cache"}


@lru_cache(maxsize=1)
def source_fingerprint() -> str:
    """SHA-256 over every backend .py file, path-ordered so it is reproducible.

    Cached: the files cannot change under a running process, and hashing on
    every request would put real work on a health check.
    """
    # Collect first, then sort the RELATIVE paths globally. A depth-first walk
    # order would be just as deterministic here, but it is not reproducible in
    # another language without reimplementing the walk — and the CLI computes
    # this same hash before a deploy so the two can be compared. One flat,
    # lexicographic order is the thing both sides can agree on.
    rels = []
    for root, dirs, files in os.walk(_BACKEND_DIR):
        dirs[:] = [d for d in dirs if d not in _SKIP and not d.startswith(".")]
        rels.extend(
            os.path.relpath(os.path.join(root, n), _BACKEND_DIR)
            for n in files
            if n.endswith(".py")
        )

    h = hashlib.sha256()
    for rel in sorted(rels):
        h.update(rel.encode())
        try:
            with open(os.path.join(_BACKEND_DIR, rel), "rb") as fh:
                h.update(fh.read())
        except OSError:
            # An unreadable file is itself a fact about this build; record that
            # rather than silently hashing a different set of files.
            h.update(b"<unreadable>")
    return h.hexdigest()[:16]


_STARTED_AT = datetime.utcnow()


def build_identity(app) -> Dict[str, Any]:
    """Everything needed to tell this build apart from another one."""
    paths: List[str] = sorted(
        {getattr(r, "path", "") for r in getattr(app, "routes", []) if getattr(r, "path", "")}
    )
    api = [p for p in paths if p.startswith("/api/")]
    return {
        "fingerprint": source_fingerprint(),
        # A hash of the API surface alone: it changes when an endpoint is added
        # or removed, which is the divergence that actually gets noticed.
        "routes_fingerprint": hashlib.sha256("\n".join(api).encode()).hexdigest()[:12],
        "route_count": len(api),
        "routes": api,
        "started_at": _STARTED_AT.isoformat() + "Z",
    }

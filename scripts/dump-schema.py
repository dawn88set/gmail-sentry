#!/usr/bin/env python3
"""Phase 5.7 — emit catalog/SCHEMA.json from `claritty_sdk.manifest`.

Run from the seed root::

    python scripts/dump-schema.py

Pydantic v2 exposes ``model_json_schema()`` which is the canonical
JSON-Schema view of the AppManifest. Both IDEs and Claude Code consume
this file for completion + validation; the platform's TypeScript
``automation.ts`` interfaces are diff-checked against it in CI so the
two surfaces never drift.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    # Import manifest.py directly to avoid pulling claritty_sdk/__init__.py
    # (which imports llm.py, which needs httpx). The script only needs
    # PyYAML + pydantic to derive the schema.
    import importlib.util as _ilu

    _sdk_root = Path(__file__).resolve().parents[2] / (
        "claritty-core/packages/clarity-sdk-py/claritty_sdk"
    )
    _candidates = [
        _sdk_root / "manifest.py",
        Path("/usr/local/lib/python3/site-packages/claritty_sdk/manifest.py"),
    ]
    _manifest_path = next((p for p in _candidates if p.is_file()), None)
    if _manifest_path is None:
        raise ModuleNotFoundError(
            f"Could not locate claritty_sdk/manifest.py — searched {_candidates}"
        )
    _spec = _ilu.spec_from_file_location("claritty_sdk_manifest", _manifest_path)
    assert _spec and _spec.loader
    _module = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_module)
    AppManifest = _module.AppManifest  # type: ignore[attr-defined]
except ModuleNotFoundError as e:
    print(
        "Could not load claritty_sdk.manifest. "
        "Install pydantic + PyYAML (`pip install pydantic PyYAML`), "
        "or `pip install -e claritty-core/packages/clarity-sdk-py`.",
        file=sys.stderr,
    )
    print(f"Underlying error: {e}", file=sys.stderr)
    sys.exit(2)


def main() -> int:
    # Forward references resolved against the module's own namespace
    # (the standalone-import path skips claritty_sdk/__init__.py so
    # things like `Literal` need re-binding here for model_rebuild).
    try:
        AppManifest.model_rebuild(_types_namespace=_module.__dict__)
    except Exception:
        pass
    schema = AppManifest.model_json_schema()
    # Top-level metadata so consumers can tell at a glance which version
    # of the schema they're reading without parsing every $ref.
    schema["$id"] = "https://claritty.dev/schema/intelligence.yaml/v1"
    schema["title"] = "Claritty AppManifest"
    schema["description"] = (
        "Canonical schema for the seed's intelligence.yaml. Generated from "
        "claritty_sdk.manifest.AppManifest via Pydantic; do not edit by hand."
    )
    out = Path(__file__).resolve().parent.parent / "catalog" / "SCHEMA.json"
    out.write_text(json.dumps(schema, indent=2) + "\n", "utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

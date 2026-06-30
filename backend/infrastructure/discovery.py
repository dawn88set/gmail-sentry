"""
Auto-Discovery System

Automatically discovers and registers agents, workflows, and triggers.
No more manual __init__.py editing!

How it works:
1. Scans backend/agents/, backend/workflows/, backend/triggers/ directories
2. Imports all .py files (except __init__.py)
3. Decorators (@agent, @workflow, @trigger_template) auto-register on import
4. Components become available immediately

Usage:
    from backend.infrastructure.discovery import discover_and_register_components

    # At app startup:
    discover_and_register_components()

    # That's it! All components are now registered.
"""

import os
import sys
import importlib.util
from pathlib import Path
from typing import List, Tuple
import logging

logger = logging.getLogger(__name__)


def discover_and_register_components() -> Tuple[int, int, int]:
    """
    Discover and register all agents, workflows, and triggers automatically.

    Returns:
        Tuple[int, int, int]: (agents_count, workflows_count, triggers_count)
    """
    logger.info("🔍 Auto-discovering components...")

    backend_path = Path(__file__).parent.parent

    # Discover agents
    agents_discovered = _discover_modules(backend_path / "agents", "backend.agents")

    # Discover workflows
    workflows_discovered = _discover_modules(backend_path / "workflows", "backend.workflows")

    # Discover triggers
    triggers_discovered = _discover_modules(backend_path / "triggers", "backend.triggers")

    # v2 is manifest-first: the authoritative inventory of agents/workflows/
    # triggers comes from intelligence.yaml (loaded by claritty_sdk.runtime.
    # bootstrap), NOT a decorator registry (which no longer exists). Importing
    # the backend/agents/*.py modules above just ensures the @agent handler
    # classes are importable; we report the file-scan counts here.
    logger.info(f"✅ Auto-discovery complete!")
    logger.info(f"   📁 Scanned {agents_discovered} agent files")
    logger.info(f"   📁 Scanned {workflows_discovered} workflow files")
    logger.info(f"   📁 Scanned {triggers_discovered} trigger files")

    return agents_discovered, workflows_discovered, triggers_discovered


def _discover_modules(directory: Path, package_name: str) -> int:
    """
    Discover and import all Python modules in a directory.

    Args:
        directory: Path to directory to scan
        package_name: Python package name (e.g., "backend.agents")

    Returns:
        int: Number of modules discovered
    """
    if not directory.exists():
        logger.warning(f"⚠️  Directory not found: {directory}")
        return 0

    discovered_count = 0

    for file_path in directory.glob("*.py"):
        # Skip __init__.py and private files
        if file_path.name.startswith('_'):
            continue

        module_name = file_path.stem
        full_module_name = f"{package_name}.{module_name}"

        try:
            # Import the module
            # This causes decorators to execute and register components
            spec = importlib.util.spec_from_file_location(full_module_name, file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[full_module_name] = module
                spec.loader.exec_module(module)

                logger.debug(f"   ✓ Loaded {full_module_name}")
                discovered_count += 1
        except Exception as e:
            logger.error(f"   ✗ Failed to load {full_module_name}: {e}")
            # Don't fail startup for one bad module
            continue

    return discovered_count


def get_discovery_summary() -> dict:
    """
    Get a summary of the app's components, read from the v2 manifest
    (intelligence.yaml) — the single source of truth. Useful for debugging.

    Returns:
        dict: Summary with counts and ids
    """
    try:
        from claritty_sdk.runtime.bootstrap import load as _bootstrap_load
        from backend.manifest_path import resolve_manifest_name

        m = _bootstrap_load(resolve_manifest_name()).manifest
    except Exception:
        return {
            "agents": {"count": 0, "ids": []},
            "workflows": {"count": 0, "ids": []},
            "triggers": {"count": 0, "ids": []},
        }

    agents = m.agents or []
    workflows = m.workflows or []
    triggers = m.triggers or []
    return {
        "agents": {"count": len(agents), "ids": [a.id for a in agents]},
        "workflows": {"count": len(workflows), "ids": [w.id for w in workflows]},
        "triggers": {
            "count": len(triggers),
            "ids": [t.id for t in triggers],
            "types": list({getattr(t.type, "value", t.type) for t in triggers}),
        },
    }

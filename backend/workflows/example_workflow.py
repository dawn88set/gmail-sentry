"""DEPRECATED — v1 workflow shape.

In the v2 (manifest-first) SDK, workflows are declared in
``intelligence.yaml#workflows`` and executed by
``claritty_sdk.runtime.workflow_engine.WorkflowEngine``. There is no
Python file per workflow anymore — the YAML block IS the workflow.

This module is kept (empty) only so an old auto-discovery scan that
imports ``backend.workflows.example_workflow`` won't crash. It will be
removed in Phase 4 along with the rest of the legacy entry points.
"""

# No registrations. See intelligence.yaml for the v2 workflow definition.

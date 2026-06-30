"""DEPRECATED — v1 trigger shape.

In the v2 (manifest-first) SDK, triggers are declared in
``intelligence.yaml#triggers`` and dispatched by the platform; the seed-side
``@trigger_template`` decorator is gone. The legacy regex parser on
the platform side (``derive-trigger-recipe.util.ts``) is also slated
for deletion in Phase 4.

This module is kept (empty) only so an old auto-discovery scan that
imports ``backend.triggers.example_trigger`` won't crash. It will be
removed in Phase 4.
"""

# No registrations. See intelligence.yaml for the v2 trigger definition.

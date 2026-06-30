"""
Triggers Package (DEPRECATED for v2 — triggers live in intelligence.yaml)

In the v2 manifest-first runtime a trigger is YAML declared in
intelligence.yaml#triggers — there are NO python trigger files and NO @trigger_template
decorators (the runtime ignores them). The platform fires triggers; the app has
no in-process scheduler.

Example (in intelligence.yaml, NOT here):
    triggers:
      - id: my-trigger
        type: SCHEDULE                 # or WEBHOOK
        workflow: my-workflow
        configFields:
          - { key: time, type: time, required: true, default: "09:00" }
          - { key: timezone, type: timezone, required: true }

This package is kept only so legacy auto-discovery imports don't crash.
"""

# No imports needed - triggers are declared in intelligence.yaml.
__all__ = []

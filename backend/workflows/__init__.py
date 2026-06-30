"""
Workflows Package (DEPRECATED for v2 — workflows live in intelligence.yaml)

In the v2 manifest-first runtime a workflow is a YAML DAG declared in
intelligence.yaml#workflows — there are NO python workflow files and NO @workflow/
@uses_agent decorators (the runtime ignores them).

Example (in intelligence.yaml, NOT here):
    workflows:
      - id: my-workflow
        inputs: { user_id: { type: string, required: true } }
        steps:
          - id: step1
            agent: agent-1
            input: { user_id: "${input.user_id}" }
          - id: step2
            agent: agent-2
            input: { user_id: "${input.user_id}", data: "${steps.step1.output.data}" }
            onError: { strategy: skip }
        outputs: { result: "${steps.step2.output.result}" }

This package is kept only so legacy auto-discovery imports don't crash.
"""

# No imports needed - workflows are declared in intelligence.yaml.
__all__ = []

# AGENTIC.md — Building Claritty Apps

This file is the entry point for humans and AI coding assistants (Claude
Code, Cursor) opening this seed for the first time. One page; everything
else is linked.

---

## The five primitives

A Claritty app composes five things:

| Primitive | What it is | Where it lives |
|---|---|---|
| **Integration** | A connected third-party service (Gmail, Slack, GitHub…). Provides credentials + a set of tools. | `catalog/integrations/<id>/manifest.json` |
| **Tool** | A typed function the runtime can call: standalone (you author) or provided by an integration (catalog). | `catalog/tools/<id>/` or `backend/custom/tools/<id>/` |
| **Agent** | An LLM + a toolset. Takes input, runs a tool-use loop, returns output. | `catalog/agents/<id>/` or `backend/custom/agents/<id>/` |
| **Workflow** | A declarative DAG of steps (each step is `agent:` or `tool:`). Always YAML in `intelligence.yaml`. | `intelligence.yaml#workflows` |
| **Trigger** | What kicks off a workflow: a schedule, a webhook, an integration push. Catalog-only. | `intelligence.yaml#triggers` |

The single source of truth for an app's wiring is **`intelligence.yaml` at the
seed root**. Decorators in `claritty_sdk` are *binders* that attach a
Python symbol to a manifest entry by id — they never carry data the
manifest doesn't.

Schema: [`catalog/SCHEMA.json`](catalog/SCHEMA.json) (machine-readable)
+ the Pydantic models in `claritty_sdk.manifest` (canonical source).

---

## Authoring loop

### Step 1 — find what's in the catalog

The catalog is the closed library of vetted primitives. Discovery is one
file: [`catalog/INDEX.md`](catalog/INDEX.md). Grep it before you write
new code. Examples:

- Need Gmail? `catalog/integrations/gmail/manifest.json` lists its
  `providedTools[]`.
- Need a summarizer? `catalog/tools/llm.summarize/manifest.json`.

### Step 2 — write `intelligence.yaml`

Reference catalog ids in `integrations:` / `agents:` / `tools:` /
`workflows:` / `triggers:`. The runtime validates the references at boot
and refuses to start on a missing one — typos are caught before deploy.

### Step 3 — author custom tools (when nothing in the catalog fits)

A custom tool lives at `backend/custom/tools/<id>/impl.py` and must
match the validator's rules
([`catalog/validators/custom-tools.rules.yaml`](catalog/validators/custom-tools.rules.yaml)):

```python
from typing import Any, Dict
from claritty_sdk import tool, ToolCtx


@tool(id="app.example")
def run(input: Dict[str, Any], ctx: ToolCtx) -> Dict[str, Any]:
    """One-sentence description that becomes the tool's UI label."""
    # Call any integration the agent's bound to:
    gmail = ctx.integration("gmail")
    gmail.send(to=input["to"], subject=input["subject"], body=input["body"])
    return {"sent": True}
```

The signature is enforced by `signatureRegex` and the decorator id must
match the file's directory name. Forbidden: `subprocess`, `eval`,
`exec`, `compile`, `ctypes`, `__import__`, `os.system`.

### Step 4 — verify before commit

Run `claritty seed verify` (Phase 5.8 — see
[`SECURITY.md`](SECURITY.md)). It validates `intelligence.yaml`, applies the same
rules the platform uses, and scans for accidentally-committed secrets.
Pre-commit hook runs it automatically.

---

## The secret boundary — read this once

**You never write secrets to this repo.** Long version:
[`SECURITY.md`](SECURITY.md). Short version:

- **Authoring** (you + your AI assistant) sees: catalog metadata,
  schema, your prompt, `intelligence.yaml`, custom code. Never: OAuth tokens,
  client_id, client_secret, KMS material.
- **Build** (`claritty seed verify`, CI) sees the same. Hard-fails on
  token-shaped strings.
- **Runtime** (the deployed app on ECS) sees: per-invocation ephemeral
  credentials, scoped to the calling function. Never: long-lived
  tokens, other users' credentials.

Tool authors must never log `ctx.integration(...)` return values or
`credentials.data`. The SDK's logger filter strips token fields, but
that's a backstop — don't lean on it.

---

## Layout

```
agentic-app-seed/
├── AGENTIC.md            ← you are here
├── SECURITY.md           ← three-circle secret contract
├── CLAUDE.md             ← AI-assistant narrative guide (older, deeper)
├── intelligence.yaml              ← single source of truth for this app
├── .claude/
│   └── skills/
│       └── agentic-app-authoring.md   ← auto-loads in Claude Code
├── catalog/
│   ├── SCHEMA.json       ← JSON Schema derived from claritty_sdk.manifest
│   ├── INDEX.md          ← human-readable catalog directory
│   ├── INDEX.json        ← machine-readable mirror
│   ├── categories.json   ← category metadata (colors, etc.)
│   ├── validators/
│   │   └── custom-tools.rules.yaml   ← shared rules: TS + Python
│   ├── integrations/<id>/
│   ├── tools/<id>/
│   ├── agents/<id>/
│   ├── triggers/<id>/
│   └── workflows/<id>/
└── backend/
    ├── custom/
    │   ├── tools/<id>/{manifest.json, impl.py}
    │   └── agents/<id>/{manifest.json, agent.py, prompt.md}
    └── …app code…
```

---

## Where to look next

- **Schema details**: [`catalog/SCHEMA.json`](catalog/SCHEMA.json) +
  `claritty_sdk.manifest`
- **Examples**: see `intelligence.yaml` in this directory + the catalog templates
- **AI-assistant context**:
  [`.claude/skills/agentic-app-authoring.md`](.claude/skills/agentic-app-authoring.md)
  auto-loads when Claude Code opens this directory
- **Security & secrets**: [`SECURITY.md`](SECURITY.md)
- **Validation rules**:
  [`catalog/validators/custom-tools.rules.yaml`](catalog/validators/custom-tools.rules.yaml)

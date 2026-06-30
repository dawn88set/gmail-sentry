---
name: agentic-app-authoring
description: Auto-loads when Claude Code is in a Claritty agentic seed worktree. Teaches the five-primitive model, the manifest schema, the safe custom-tool escape hatch, and what NEVER to write to the repo.
trigger: project
---

# Agentic App Authoring (Claritty)

Auto-loaded when this seed is open. Read once per session, then act on it.

## You are authoring an app composed of five primitives

- **Integration** — a connected third-party (Gmail, Slack, GitHub…). Catalog-only. Lists provided tools.
- **Tool** — a typed function the runtime calls. Catalog (provided by an integration or standalone) or **custom** (you write it).
- **Agent** — an LLM + a toolset. Catalog or custom. Set a `reasoning` tier — `deep` (Opus +
  extended thinking + a grounded, self-critiquing prompt) for the agent that synthesises data into
  the app's valuable output; else `standard`/`light`. See [`implement-agent.md`](../prompts/implement-agent.md).
- **Skill** — a vetted, reusable PROCEDURE an agent follows (the *how*, not the *what* — distinct
  from a tool, which is a callable action). Catalog-only. When a custom agent's job matches a skill
  (draft a reply, triage/classify, summarize with citations…), **inline that skill's procedure into
  the agent's `prompt.md` instead of writing the steps freehand** (see "Custom agent template" below).
- **Workflow** — runs in one of two modes: a **`dag`** (a fixed declarative pipeline of `steps`,
  the default) or a **`team`** (an autonomous coordinator + a `team` roster that decides the flow at
  runtime — for open-ended jobs). Always YAML in `intelligence.yaml`. See
  [`implement-workflow.md`](../prompts/implement-workflow.md).
- **Trigger** — what fires a workflow (schedule, webhook). Catalog-only.

The single source of truth is **`intelligence.yaml`** at the seed root. Decorators
in `claritty_sdk` are binders; the manifest carries the data.

## Before writing any code: ground yourself

0. **Discovery first.** If `docs/plans/0001-brief.md` doesn't exist yet, run
   Claritty's discovery method before designing anything — restate the problem,
   **propose two distinct ideal outcomes** (proactive vs on-demand) for the
   developer to pick, ask 3–5 focused follow-ups (widget glance + automation
   autonomy + data), then write the brief. Playbook:
   [`.claude/prompts/brainstorm.md`](../prompts/brainstorm.md). If signed in to the
   CLI, `claritty discover outcomes "<problem>"` / `claritty discover questions
   "<problem>"` give the platform's real output (else generate them per the playbook).
1. Read [`AGENTIC.md`](../../AGENTIC.md) (one-page overview).
2. Grep [`catalog/INDEX.md`](../../catalog/INDEX.md) for the integration / tool / agent / **skill** you need. If it's there, reference it by id in `intelligence.yaml`. Don't reinvent.
   - **For every custom agent, also scan the `## Skills` section** — if one fits the agent's job (by its "Fits agents that:" tools or its intent), open `catalog/skills/<id>/procedure.md` and inline that vetted procedure into the agent's `prompt.md`. The procedure is proven; writing the steps freehand is the thing to avoid.
3. If you must build something new, the **only** custom escape is custom tools and custom agents (custom integrations and custom triggers are refused — the platform owns OAuth and the dispatcher).
4. Skim [`SECURITY.md`](../../SECURITY.md). Internalize what you must never write.

## Integrations are built in — declare, don't mock (no API keys)

Claritty ships ~33 integrations in [`catalog/INDEX.md`](../../catalog/INDEX.md) (Gmail, Slack,
LinkedIn, X, HubSpot, Salesforce, Stripe, Notion, GitHub, Linear, …). For ANY external service the
app reads from or acts on:

1. **Grep `catalog/INDEX.md`.** If the service is there, it's a built-in integration — **the platform
   manages OAuth/credentials per user. You write NO OAuth code and need NO API keys.**
2. **Declare it** under `intelligence.yaml#integrations` (`- id: <id>`), and **list its tools in the
   agent's `tools:`** (e.g. `linkedin.fetch_posts`, `gmail.send`) — declaring the integration alone
   does NOT grant tool access. The agent calls the tool (named in its `system_prompt`), or a custom
   tool reaches the live connection via `ctx.integration("<id>")`.
3. **Local testing:** set `CLARITTY_FAKE_CREDS_<ID>='{"access_token":"…"}'` in `.env` — this drives
   the REAL integration path without OAuth. It is NOT a mock data layer.
4. **Honest failure:** when the service isn't connected, return a 409 / inline connect-prompt; on a
   real failure, surface it. NEVER fake a success or simulate the external call.
5. **No catalog match** (e.g. reddit, g2, hn): write a custom read-only `@tool`, or seed
   **clearly-labeled** sample data — and say which. Never pass a mock off as the real source.
6. **No in-app connect surface.** Connecting is platform-owned: declaring the integration is all the
   app does — the platform lists it + runs OAuth on the app's Intelligence / Settings → Integrations
   tabs. Do NOT build an Integrations page, a `SetupChecklist` / "connect N services" banner, or an
   Integrations nav route. The seed ships none — don't add one.

Do NOT, for a catalog service: ask the user for API keys, write OAuth code, `pip install` a provider
SDK, build a mock data layer, or hand-roll a connect/Integrations UI. (Custom *integrations* and
custom *triggers* are refused — the platform owns OAuth + the dispatcher.) Full pattern + examples:
[`INTEGRATIONS.md`](../../INTEGRATIONS.md).

## Custom tool template — copy/adapt, don't deviate

```python
from typing import Any, Dict
from claritty_sdk import tool, ToolCtx


@tool(id="app.your_id_here")  # MUST match the directory name
def run(input: Dict[str, Any], ctx: ToolCtx) -> Dict[str, Any]:
    """One-sentence description (shows up in the agent's tool list)."""
    # Call any integration the calling agent is bound to:
    # gmail = ctx.integration("gmail")
    # gmail.send(to=..., subject=..., body=...)
    return {"key": "value"}
```

Rules enforced by `claritty seed verify` AND by the platform's
`CustomToolService` (one rules file, two consumers —
`catalog/validators/custom-tools.rules.yaml`):

- Exact signature: `def run(input: Dict[str, Any], ctx: ToolCtx) -> Dict[str, Any]:`
- Decorator `@tool(id="…")` must match the tool's directory name
- File size ≤ 64 KiB UTF-8
- **Forbidden patterns**: `subprocess`, `eval`, `exec`, `compile`, `ctypes`, `__import__`, `os.system`, `open("/etc/…")`
- Imports allowed: `typing`, `claritty_sdk`, pure-Python stdlib without subprocess/eval/exec/ctypes surface. No third-party packages — use `ctx.integration(...)` for everything external

## Custom agent template

```python
from claritty_sdk import agent, BaseAgent


@agent(id="app.your_agent_id")
class Agent(BaseAgent):
    prompt_file = "prompt.md"  # the file next to this one
```

Then write `prompt.md` next to it. The `tools:` / `integrations:` /
`inputs:` / `outputs:` schema lives in `manifest.json` in the same dir,
NOT inline in Python.

**Before writing `prompt.md` freehand, check `catalog/skills/` for a vetted
procedure that matches this agent's job** (grep the `## Skills` section of
`catalog/INDEX.md`; match on the skill's "Fits agents that:" tools or its
intent). If one fits — e.g. `draft-on-brand-reply`, `classify-and-triage`,
`summarize-with-citations` — open its `procedure.md` and **inline that text
into `prompt.md`** (then add the app-specific context around it). The vetted
procedure is the proven way to do the task; reinventing the steps yields
weaker, less consistent agents. Only write the procedure from scratch when no
skill fits.

## The secret boundary — non-negotiable

**Never write to the repo:**
- OAuth `client_id` / `client_secret` (the platform owns these)
- Access tokens or refresh tokens (per-invocation, from the platform)
- KMS keys, `CLARITTY_INTERNAL_SECRET`, `INTEGRATION_OAUTH_STATE_SECRET`
- Encrypted credential blobs
- Hard-coded URLs to internal endpoints

**Never log:**
- `ctx.integration(...)` return values
- `credentials.data`, `.token`, `.access_token`, `.refresh_token`, `.api_key`
- Full request/response bodies of integration calls

The SDK's `Credentials.__repr__` is redacted and the logger filter
strips token fields — but those are backstops, not your safety net.
Don't put secrets into `print()` or `f"…{token}…"`.

**Dev-time mock creds** (safe pattern): the SDK reads
`CLARITTY_FAKE_CREDS_<INTEGRATION_ID>` env vars during local testing.
Use these in `.env` (which is `.gitignored`). NEVER commit a real token
behind this pattern.

## Verify before you push

```sh
claritty seed verify   # validates intelligence.yaml, custom tools, scans for secrets
```

Pre-commit hook runs it automatically. CI runs it again on the PR. Both
hard-fail on token-shaped strings — there is no "warn-only" mode.

If a legitimate string trips the scanner (e.g. a CSS class that looks
like `sk-…`), add it to `.claritty-allowlist` (one regex per line) — but
think twice before doing so.

## Design & UI — make it look designed, not generated

When you build the frontend (`Dashboard.tsx`, `Widget.tsx`, pages), match the
**golden references** — they are the bar for polish and state-handling:

- [`docs/golden/Dashboard.golden.tsx`](../../docs/golden/Dashboard.golden.tsx)
- [`docs/golden/Widget.golden.tsx`](../../docs/golden/Widget.golden.tsx)

Study their hierarchy, spacing, and state handling; then ADAPT to this app's
domain — do not copy the content. The five non-negotiables they demonstrate:

1. **Theme tokens only** — `text-foreground` / `text-muted-foreground` /
   `text-accent` / `bg-card` / `border`. NEVER hardcode hex or a fixed Tailwind
   palette (`bg-indigo-500`, `#6366f1`) — it fights the per-app theme. Fill
   `frontend/src/theme.css` with the app's palette first.
2. **One primary action per view**; everything else is quiet/secondary.
3. **All three states, high-contrast** — skeleton while loading, a calm empty
   state (short line + the primary action), and a legible inline error with
   retry. Never a blank screen, a raw spinner, or muted-on-glass text.
4. **Mobile-first** — single column → grid at `md`; tap targets ≥ 44px; no
   horizontal scroll. (The Widget is the exception: fixed-frame, branches on the
   `size` prop only — no responsive prefixes inside it.)
5. **No AI tells** — no emoji in chrome, no decorative icons glued to headings,
   no rainbow/multi-stop gradients, no "Welcome to…" hero. lucide icons only
   where they aid scanning; sentence case; concise domain copy.

## When you don't know

- "Is this integration in the catalog?" → grep `catalog/INDEX.md`
- "Is there a vetted procedure for what this agent does?" → grep the `## Skills` section of `catalog/INDEX.md`, then read `catalog/skills/<id>/procedure.md` and inline it into the agent's `prompt.md`
- "What's the manifest schema?" → read `catalog/SCHEMA.json` (machine) or `claritty_sdk.manifest` (canonical Pydantic source)
- "What can a custom tool import?" → see the forbidden list above; anything not on it is OK if it's stdlib
- "Where do credentials come from at runtime?" → `ctx.integration(id)` — never construct them yourself
- "Why is my custom tool failing the validator?" → run `claritty seed verify` and read the line:col

## Anti-patterns Claude Code should refuse

- Writing OAuth code in the seed (refuse → "use a catalog integration; if it doesn't exist, surface as an unmatched intent")
- Inlining a token as a default arg (refuse → "platform-injected at runtime via `ctx.integration(...)`")
- Adding a third-party package to `requirements.txt` for an external API the catalog covers (refuse → "use the catalog integration")
- Inventing an integration id that's not in `catalog/INDEX.md` (refuse → "list the closest match + propose adding it to the catalog")
- Writing a custom agent's procedure freehand when a catalog skill covers it (refuse → "inline `catalog/skills/<id>/procedure.md` instead; reinventing it yields a weaker, inconsistent agent")
- Editing files under `catalog/` from the seed (refuse → "catalog is upstream; changes happen there, not in an app worktree")

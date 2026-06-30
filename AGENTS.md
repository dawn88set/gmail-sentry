# AGENTS.md — building a Claritty app with any AI tool

This is the **Claritty agentic-app template**. Whatever AI coding tool you use
(Cursor, Claude Code, Windsurf, …), follow the same flow Claritty's own builder
uses. Full guidance lives in **`CLAUDE.md`**; the design/identity rules in
**`IDENTITY.md`**, **`WIDGETS.md`**, **`INTEGRATIONS.md`**.

## Step 0 — Discovery FIRST (don't jump to code)

Run Claritty's discovery method before designing or writing anything. The complete
playbook is **`.claude/prompts/brainstorm.md`**. In short:

1. **Restate the problem** in one line.
2. **Propose TWO ideal outcomes** — two *distinct* end-states (one proactive "it
   handles it for me", one on-demand "it helps me when I act"), ≤6-word titles,
   concrete, self-contained. Let the developer pick one or write their own.
3. **Ask 3–5 focused follow-ups** (concrete options + a "Let me specify…" choice),
   covering at least the **widget glance** (the one thing seen + one action),
   **automation** (cadence + autonomy: autonomous / suggestive / observational),
   and **data** (its own data, or a catalog integration).
4. **Write the brief** → `docs/plans/0001-brief.md`, and set
   `app-config.json` → `clarity_marketplace.core_action.definition_of_done`.

**Parity (optional):** if the developer is signed in to the Claritty CLI, get the
platform's *real* discovery output instead of improvising:

```
claritty discover outcomes  "<their problem>"     # → {"outcomes":[…]}
claritty discover questions "<their problem>"     # → {"questions":[…]}
```

Each prints one line of JSON. If it prints `{"unauthenticated":true}` (or errors),
generate the outcomes/questions yourself with the playbook rules — the method is
identical either way.

## Then build

Only after the brief is written: design the agents/workflow/trigger, the widget per
size, the data model, and the app's own identity, then implement per `CLAUDE.md`.
Run `node scripts/check-not-template.mjs` (the identity gate) before calling it done.

**Compose from the catalog — don't reinvent.** Grep `catalog/INDEX.md` for the
integrations, tools, agents, and **skills** you need. For each custom agent, check the
`## Skills` section: a skill is a vetted procedure (draft a reply, triage, summarize with
citations…) — when one fits the agent's job, inline `catalog/skills/<id>/procedure.md` into
its `prompt.md` instead of writing the steps freehand. Proven procedure beats improvised.

**Invariants:** widget sizes are exactly 170×170 / 360×170 / 360×360; triggers are
schedule / webhook / event / manual; the app is self-contained (no OAuth/keys except
catalog integrations the platform manages — see `INTEGRATIONS.md`).

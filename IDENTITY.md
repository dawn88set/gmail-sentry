# Make this app YOURS — identity & redesign guide

> **This repo is a TEMPLATE.** If you only swap the backend logic, your app will
> still *look* exactly like the seed — same colors, same landing page, same logo.
> A real app must **keep the platform contract** and **completely replace the
> template's identity**. This file is the source of truth for what to keep vs.
> change. An automated **identity gate** (`scripts/check-not-template.mjs`)
> enforces it — see the bottom.

---

## Step 0 — turn the gate on

The very first thing you do when you start building:

```bash
rm .claritty-seed-pristine
```

That marker keeps the bare seed's own CI green. Deleting it activates the
identity gate, which then refuses to let the build be "done" until your app has
its own identity and the example code is gone.

---

## KEEP — the platform contract (do NOT change)

These are the "basic required parts." Change them and the app stops working on
the Claritty platform.

| Area | What must stay |
|------|----------------|
| **Backend endpoints** | `GET /health`, `GET /api/widget?size=`, `GET /api/graph`, `/api/agents*`, `/api/workflows*`, `/api/trigger-templates`, `POST /api/{agents,workflows}/{id}/execute`, `POST /internal/run-due-triggers`, `POST /internal/trigger-webhook` |
| **Startup** | `backend/main.py` order: `init_db → seed → discover_and_register_components → build_graph`; auto-discovery of `backend/{agents,workflows,triggers}/*.py` and `backend/routes/*.py` exporting `router` |
| **SDK (v2 manifest-first)** | agents/tools/workflows/triggers declared in `intelligence.yaml`; an agent is a `system_prompt` (zero-Python `promptFile`, or an `@agent(id)` class — NEVER `def execute()`/`AgentResult`); workflows + triggers are YAML; AI runs through the SDK tool-use loop (never a raw provider SDK) |
| **Multi-tenancy** | `X-User-ID` header; every user-data model has `user_id`; every query filters by it |
| **Infra** | `Dockerfile`, `docker-compose.yml`, `frontend/nginx.conf`, ports 3200/8000, `VITE_API_URL=''` (relative URLs), required env vars `DATABASE_URL` / `CLARITTY_PLATFORM_URL` / `CLARITTY_AUTH_TOKEN` |
| **Widget contract** | `/widget?size=`, the 3 fixed sizes (170×170 / 360×170 / 360×360), `WidgetContainer` / `WidgetButton` / `WidgetBadge` from `@clarittyai/widget-toolkit`, the `data-widget-size` attribute, `p-4` (content) / `rounded-3xl`, **no responsive prefixes** (`sm:`/`md:`/`@media`/`window.innerWidth`), and **no box-shadow / no host background-padding-margin** (the iframe is exactly the widget size — see WIDGETS.md) |
| **CSS token NAMES** | Keep the token *names* (`--background`, `--foreground`, `--accent`, `--card`, `--muted`, `--border`, `--ring`, `--brand-font`, `--brand-accent`, `--brand-accent-600`). The UI kit reads them. You change their **values**, not their names. |
| **Integration store** | `UserIntegration` (in `backend/models.py`) is the sanctioned place to store per-user credentials when your app connects an external service. Keep it. See **[INTEGRATIONS.md](INTEGRATIONS.md)**. |

> **Identity ≠ done.** This file is about how the app *looks*. Making it actually *work* —
> connecting external services, an approve→act lifecycle, scheduling reality, a definition of
> done — is covered in **CLAUDE.md → "Build patterns that make the app actually WORK"** and
> **[INTEGRATIONS.md](INTEGRATIONS.md)**. The gate also prints non-blocking advisories for these.

---

## REPLACE — the template identity (you MUST redesign these)

This is where "the design completely changes." None of it is platform contract;
all of it is what currently makes every app look like the seed.

| File / area | What to do |
|-------------|-----------|
| `frontend/src/theme.css` | **Fill it.** Add a real `:root { … }` override with YOUR palette + font (see below). Ships empty in the seed. |
| `frontend/src/lib/app-meta.ts` | Set the real `appName` + `appDescription`. |
| `frontend/src/pages/Dashboard.tsx` | Replace the template **showcase** (HowItWorks / AgentGraph / WidgetGallery) with your app's real landing/dashboard. |
| `frontend/src/components/AgentGraph.tsx`, `HowItWorks.tsx`, `WidgetGallery.tsx` | Remove (or repurpose) — these are "how Claritty works" tutorial chrome. |
| `frontend/src/components/Layout.tsx` | Restyle the chrome and **swap `/claritty-logo.png` for your app's own mark**. |
| `frontend/src/components/ui/*` | Reskin (radii, shadows, spacing, weights). Keep the component APIs + token names. |
| `frontend/src/index.css` | Adjust the component classes / typography scales if your brand needs it. |
| `public/` | Replace `favicon` / `apple-touch-icon` with your icon. |
| `backend/agents/example_agent.py`, `backend/workflows/example_workflow.py`, `backend/triggers/example_trigger.py` | **Delete** and build your domain's agent/workflow/trigger. |
| `backend/models.py`, `backend/routes/app.py` | Replace the `Task` example with your real models + endpoints (keep `UserIntegration`, `WorkflowExecution`, the `/api/widget` route, and `user_id` on every model). |

### How to set your palette — `frontend/src/theme.css`

Token **names** are fixed; you set their **values** (HSL channels, no `hsl()` wrapper):

```css
:root {
  --brand-accent: 268 84% 58%;      /* your primary action / accent */
  --brand-accent-600: 268 84% 48%;  /* its darker hover shade */
  --brand-primary: 240 6% 10%;      /* headings / strong text */
  --brand-font: 'Sora', system-ui, sans-serif;  /* load the font in index.html */
}
```

Pick a palette + type that fit the app's *purpose* (a finance app ≠ a kids app ≠
a travel app). This single file is the biggest lever on "it doesn't look like the
template." See `.claude/design-tokens.md` for the full token list.

---

## The redesign checklist (mirrors the gate)

Your build is not done until all of these are true:

- [ ] `.claritty-seed-pristine` deleted
- [ ] `frontend/src/theme.css` has an active `:root` override with `--brand-*` values
- [ ] `frontend/src/lib/app-meta.ts` uses your real `appName` + `appDescription`
- [ ] `frontend/src/pages/Dashboard.tsx` is your real landing page (no showcase)
- [ ] `frontend/src/components/Layout.tsx` uses your own mark (no `claritty-logo.png`)
- [ ] The 3 seed example components are deleted, replaced by your domain
- [ ] The problem the app solves is actually delivered end-to-end (agent → workflow → widget → UI)
- [ ] `npm run check:identity` passes (and `npm run type-check` + `npm run test:widgets`)

---

## The identity gate (enforcement)

`scripts/check-not-template.mjs` checks the items above and **exits non-zero**
while any residue remains. It runs:

- as a **Claude Code Stop hook** (`.claude/settings.json`) — blocks "done" mid-build,
- via **`npm run check:identity`** (in `frontend/`),
- in **CI** (`.github/workflows/validate-app.yml`).

It is a no-op while `.claritty-seed-pristine` exists (the untouched seed).

---

## Publishing changes to this seed (maintainers)

Editing this repo does **not** affect future scaffolds until it's published.
`create-claritty-app` clones the GitHub seed at a pinned tag. To roll out:

1. Commit + push the seed.
2. `git tag v1.1.0 && git push --tags`.
3. Bump `DEFAULT_SEED_REF` to `v1.1.0` in
   `claritty-core/packages/create-claritty-app/src/index.ts`.
4. `npm publish` the `create-claritty-app` package.
5. `npm run seed:sync` in `clarity-api` to update the S3 seed catalog (platform pipeline).

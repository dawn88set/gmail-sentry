# Testing integrations locally — the dev experience

Connecting an integration (Gmail, Slack, HubSpot, …) is **platform-managed**: the
one-click OAuth + the encrypted token live on the Claritty platform, and
integration **actions** run through the platform's **executor** (the token never
touches your app). So you don't need to deploy to test most things — but you also
can't fake a real external send. Use this 3-tier loop.

## Tier 1 — Local, faked I/O (default, seconds)
Everything except real external calls. Run the app against a local DB; satisfy the
"connected" check with fake creds; the agent's `fallback()` runs without the LLM.

```bash
# backend (from the app dir)
DATABASE_URL=postgresql://localhost:5432/<db> NODE_ENV=development \
  uvicorn backend.main:app --port 8000
# trigger the intelligence on demand (no scheduler locally):
scripts/run-now.sh <workflow-id> http://127.0.0.1:8000 dev-user
# exercise an integration read path without OAuth:
export CLARITTY_FAKE_CREDS_GMAIL='{"access_token":"ya29.test","scope":["gmail.modify"]}'
```
A real send still 409s here (no connected account) — that's honest-publish, correct.

## Tier 2 — Local runtime + REAL hosted creds (the sweet spot)
Connect the account **once on the platform**, then run the app **locally** pointed
at the platform. Integration **actions delegate to the platform executor**, so the
real send works on your machine and **the token stays server-side**.

```bash
# Prereq: connect the integration once on the platform UI (one-click OAuth).
export CLARITTY_PLATFORM_URL=https://api.staging.claritty.ai   # the platform
export CLARITY_INTERNAL_SECRET=<ask a platform admin>          # internal-dispatch secret
DATABASE_URL=postgresql://localhost:5432/<db> NODE_ENV=development \
  uvicorn backend.main:app --port 8000
```
With `CLARITTY_PLATFORM_URL` set, `backend/shared/adapters` runs every action via
`POST {platform}/internal/integrations/tools/{id}/{tool}/execute` (executor path) —
the laptop never holds the user's token. A not-connected account → 409, a real
failure → 5xx, a real id → `published`. Same code path the hosted app uses.

> Security: `CLARITY_INTERNAL_SECRET` is a password — keep it out of git and logs.
> If you instead read raw creds (`load_credentials`), the token transits your app;
> prefer the executor path (it's the default when `CLARITTY_PLATFORM_URL` is set).

## Tier 3 — Publish to a test app (the fidelity gate, minutes)
Reserve deploy for what only the platform proves: the one-click connect UX,
scheduled triggers firing (`/internal/run-due-triggers`), edge auth, the real
build/deploy. Don't use it as your inner loop — it's slow to iterate.

## Summary
| Need | Tier |
|------|------|
| App logic, lifecycle, widget, agent shape | 1 (local, fake creds) |
| Real Gmail/Slack behavior without deploy | 2 (local + platform creds via executor) |
| Connect UX, scheduling, edge, deploy | 3 (publish) |

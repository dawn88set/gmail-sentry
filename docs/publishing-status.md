# Publishing status — where the marketplace submission stands

Submission `6819e987-ee90-457f-ae4d-0c41374bcc3e` · app **Gmail Sentry** ·
`dawn88set@gmail.com`

## Resolved: the submission had no repo attached

It was created as a **direct upload**, so `githubRepoUrl` was `null`, and the
validation orchestrator refuses to start without one:

```
Submission 6819e987-… has no githubRepoUrl — validation pipeline only
handles developer submissions
```
`clarity-api/src/modules/validation/services/validation-orchestrator.service.ts:111`

The CLI can't fix this: `--repo` is **create-time only**. `buildSubmission()`
sends it to `POST /api/apps/templates` (create), while both re-deploy paths —
`POST /:id/resubmit` (no body) and `POST /api/apps/templates/direct` — carry no
repo field. And clearing `templateId` from `.claritty.json` doesn't help, because
the server matches on **`userId` + app NAME + `isDraft`**
(`app-template.service.ts:107`) and re-derives the same id.

**Fixed** with the endpoint the CLI never calls:

```
PATCH /api/apps/templates/6819e987-ee90-457f-ae4d-0c41374bcc3e
{"githubRepoUrl":"https://github.com/dawn88set/gmail-sentry","githubBranch":"main"}
→ 200 "Repository updated! Full verification has started and will complete shortly."
```

`marketplaceStatus: PENDING_REVIEW` was preserved. The same thing is available
without curl at `app.claritty.ai/developers/6819e987-…` (the repository field).

## Remaining: install the Claritty GitHub App — needs you

Validation now genuinely runs and fails on one prerequisite:

```
GitHub access failed: GitHub App not connected.
Please connect your GitHub account to continue.
```

A public repo is **not** sufficient. `github-validator.service.ts:84` calls
`getInstallationIdForRepo(owner, repo)`, which is a live
`apps.getRepoInstallation` call as the Claritty App — so the App has to actually
be installed on the repository.

**→ Install it on `dawn88set/gmail-sentry` at https://github.com/apps/claritty-validator**
(verified to exist; `claritty` and `clarity-validator` are 404s.)

There is no API for this — `/api/github/install-url`, `/status` and
`/installations` are all 404 on the platform. It is a GitHub-side action.

Once installed, re-trigger by re-sending the same PATCH (any repo change sets
status to `VERIFYING` and fires the pipeline), then poll
`claritty status --app-id 6819e987-…`.

---

## ✅ Tested in production — the outage hypothesis was WRONG

Ran a real scan through the deployed app on 2026-08-02, signed in as the real
user with Gmail and Slack both connected:

```
Scanned 20 emails — flagged 4, filed 0, notified 0
```

Promotions moved 139 → 207, Social 2 → 4, attention 29 → 33, "scanned just now",
and new genuine alerts appeared. Those numbers come from `gmail.count`,
`gmail.search` and `gmail.get_message` — every one of them through
`execute_tool`.

**So the broker is not rejecting unproven callers in production.** Either prod
isn't running the strict-identity build yet, or `BROKER_STRICT_APP_IDENTITY` is
set to `false` somewhere outside the repo. The reasoning below was sound from the
source, and wrong about the deployed reality. Left on the record because it is
still a live *latent* risk: the moment prod picks up that build, every generated
app's integration actions start failing. The seed fix is worth making before
that happens, not after.

## 🔴 ROOT CAUSE FOUND: the platform's draft build is failing

The app editor (`app.claritty.ai/apps/7e925d43-…`) shows:

> **Draft build failed — the live app wasn't updated**
> Build failed. Please check that your app builds successfully locally.

That is why every deploy left the live app untouched.

### How the deploy model actually works (undocumented, and the CLI lies about it)

`upload-deploy.processor.ts:63` states it plainly:

> *"a CLI re-deploy of an ALREADY-LIVE app builds the DRAFT runtime (the
> developer Publishes to go live) … the FIRST upload (no deployedAt yet) still
> goes live."*

So `claritty deploy` on a live app **only ever updates the draft**. Going live
needs a separate **Publish to live** (UI) or
`POST /api/generation/apps/:appId/publish-draft`.

**The CLI reports the wrong thing.** `waitForUploadDeploy` polls
`GET /api/apps/templates/direct/:appId`, which returns the app's *current*
status — already `ACTIVE` from a previous deploy — so the CLI prints
"✓ Gmail Sentry is live in your workspace" for a build that failed and a live
app it never touched. It should report the draft outcome. **That's a real bug
worth fixing in `create-claritty-app`**, because it makes a failed deploy
indistinguishable from a successful one.

### It is NOT our code

Everything reproducible locally passes, from exactly what's on `main`:

| Check | Result |
|---|---|
| Fresh `git clone` + `npm ci` + `npm run build` | ✅ builds, 1947 modules |
| `pip install --dry-run -r backend/requirements.txt` | ✅ resolves |
| `import backend.main` with the seed's PLATFORM_INFRA_FILES restored over ours | ✅ boots |
| `docker compose up --build` | ✅ healthy, migrations to head |
| 175 backend tests · `npm run test:all` | ✅ green |

The last successful live deploy was **2026-07-20**, and `draftDeployedAt` is
stuck at the same date — so the draft build has failed on every attempt since.
Every other app in the workspace deployed as recently as 2026-07-31, and Gmail
Sentry is the only one with `hasDraftChanges: true`. The deployment queue is
healthy; this app's build specifically is not.

### What's needed to get past it

The actual compiler/packaging error only exists in **AWS CodeBuild logs** for
the draft build of app `7e925d43-…` (draft Lambda
`claritty-app-7e925d43-dft`, per `metadata.draftInfrastructure`). The platform
surfaces only a generic string — `draftError` carries no detail, and
`GET /api/apps/:id/logs` returns stub lines, not build output.

**→ Read the CodeBuild log for that draft build.** That is the one piece of
information nobody outside the AWS account can get, and it turns this from a
guess into a fix.

## Secondary: the running app is 12 days stale

The deployed container is from **2026-07-20** (`deployedAt`, and
`installedSourceKey: apps/7e925d43-…/generations/2026-07-20T18-28-17-232Z/`).
The live UI proves it: two nav tabs instead of four, "29 need attention" instead
of "open loops", and no Follow-ups, Folders or People anywhere.

**None of the ledger, counterparties, follow-ups, filing, nudges or People work
is running** — even though `claritty deploy --yes` reported
"✓ Gmail Sentry is live in your workspace" on every attempt.

The chain: `claritty deploy` updates the **template submission**, and the
installed **app instance** is only refreshed when validation passes. Validation
is stuck on the GitHub App. So the same missing App blocks *both* the marketplace
listing *and* getting the new code live — which makes installing it the single
highest-value action outstanding.

## Also seen in production: Slack channel listing fails

The Rules screen reports:

```
Channel list unavailable (slack.list_channels failed: HTTP 502
integration tool execution failed: Slack conversations.list …)
```

A 502, not a 403 — so this is `IntegrationError`, a genuine downstream failure
rather than the identity gate. Worth a look, but it degrades gracefully: the
channel picker falls back to manual ID entry, which is why the guide text is
there.

## The original reasoning (kept for the seed fix)

Found while investigating something else. **This matters more than the listing**,
because it would affect every user who installs the app.

`clarity-api`'s broker now requires apps to *prove* which app they are:

- `assertBrokerCaller` is applied to the tool-execute route
  (`internal-integrations.controller.ts:204`) and demands
  `X-Claritty-App-Secret` = `HMAC(master, appId)`.
- `BROKER_STRICT_APP_IDENTITY` defaults to `'true'` — fail-closed — and is set
  **nowhere** in the monorepo's infra, env files or task definitions
  (`broker-auth.service.ts:49`).
- But the seed's `execute_tool` sends only `X-Claritty-Internal`
  (`agentic-app-seed/backend/shared/adapters/__init__.py:193`). Every generated
  app checked does the same.

If prod runs current `main`, **every integration action 403s with "app identity
not proven"** — scan, reply, filing, nudge, all of it. The app would install and
then do nothing.

Two details that make this look like an oversight rather than a decision:

1. The SDK's own `executor_client.py` **does** send the header, and this repo's
   `backend/routes/integrations_setup.py` (the *status* path) does too. The
   *action* path is the odd one out — strict identity was rolled out to the
   status path and missed here.
2. Both files are in `GeneratedAppDeployService.PLATFORM_INFRA_FILES`, so they
   are **overwritten from the seed on every deploy**. That means this repo's
   local improvements to `integrations_setup.py` are already being silently
   discarded — and a fix made here would be too. **The fix belongs in
   `agentic-app-seed`**, where it also fixes every other generated app.

### How to settle it in one request

```
POST {api}/internal/integrations/tools/gmail/count/execute
  X-Claritty-Internal: <master>
  {"userId":"<platform-user-uuid>","appId":"6819e987-…","arguments":{"query":"in:inbox"}}
```
`403` = outage confirmed · `409` = auth fine, Gmail just not connected ·
`200` = hypothesis wrong · `401` = wrong master secret

Repeat **with** `X-Claritty-App-Secret: HMAC-SHA256(master, appId)`. If the first
is `403` and the second isn't, that proves both the bug and its one-line fix.

Not run here: it needs the platform's shared internal secret, which we chose not
to handle.

---

## Also still unverified: the ledger's broker assumptions

`scripts/verify_ledger_broker.py` has never run against a real mailbox. Two of
its probes are load-bearing for the whole follow-up layer — that `after:`/
`before:` accept epoch seconds, and that search stubs carry `threadId`. Both are
currently verified only against a fake broker.

If epoch windows turn out not to work, `SENTRY_LEDGER_EPOCH_QUERIES=0` switches
`window_query()` to relative `newer_than:`/`older_than:` hours and nothing else
changes (`test_window_query_relative_fallback` covers it). If `threadId` is
missing from stubs, that is not recoverable by config and the follow-up layer's
foundation needs rethinking.

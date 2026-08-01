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

## ⚠️ Before this goes public: a likely production outage

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

# Deploying Gmail Sentry

No GitHub. No CI. Three commands, the way Firebase works:

```bash
npm i -g create-claritty-app     # once
claritty login                   # once, opens the browser
claritty deploy                  # every time
```

`deploy` tars this folder (minus `node_modules`, `.git`, `.env`, `dist`,
`__pycache__`, `test-results`…), uploads it to a presigned URL, and the platform
builds and runs it. Your source goes straight from this machine to Claritty —
nothing is pulled from a repository, and the deploy works with no git remote at
all.

## The binding

`.claritty.json` is this repo's `.firebaserc`: it maps the app to one template
per platform, so every deploy updates the same app instead of creating a new
one. It is committed on purpose — that is what makes a deploy from any machine
land on the same app.

```json
{ "deployments": { "https://api.claritty.ai": { "templateId": "d0fa0236-…" } } }
```

Delete that binding and the next deploy creates a **new** app. Point it at a
different template id and the next deploy targets that app instead.

## Why the original template was abandoned

`6819e987-…` was created from a GitHub submission on 2026-07-01, so it carries
`githubRepoUrl: https://github.com/dawn88set/gmail-sentry`. Every deploy to it
runs a GitHub App access check that fails:

```
Validation failed after 1 attempts:
GitHub access failed: GitHub App not connected.
Please connect your GitHub account to continue.
```

That check cannot be removed. `PATCH` with `githubRepoUrl: null` returns HTTP
200 and is silently ignored; `""` returns HTTP 400; each attempt increments
`resubmissionCount`. The field is write-once, which permanently welds a
GitHub-created template to a validation path — so the only way to a git-free
deploy is a template that never had a repo URL.

`d0fa0236-…` is that template. It was created by `claritty deploy` from this
folder, has `githubRepoUrl: None`, and never touches GitHub.

## Known: the build is nondeterministic

Deploys currently fail far more often than they succeed, on Claritty's side. The
proof is a control run on 2026-08-04: one untouched `create-claritty-app` seed,
the same directory deployed twice about thirty minutes apart — the first built,
the second failed. Same bytes, opposite outcomes, so nothing in this app can
explain it.

Everything verifiable here passes: `docker build --platform linux/amd64
--no-cache` succeeds, the container answers `/health` 200 in 2 s, all migrations
apply to a fresh Postgres, `npm ci` is clean, the frontend builds in 9 s under a
1 GB cap, and `claritty doctor` passes including the platform's own dry-run.

Two things to know when a deploy fails:

* **Do not trust the CLI's verdict.** It prints `✓ <app> is live in your
  workspace` for builds that fail a minute later, because it polls the app's
  *current* status — already ACTIVE from a previous deploy — so it can't observe
  the real outcome. Check `deployedAt` / `draftErrorAt` on
  `GET /api/apps/:id` instead.
* **Ignore "check that your app builds successfully locally."** The same API
  record carries the platform's own verdict: `"Deployment was interrupted -
  please retry"`, `userActionable: false`.

`scripts/deploy-until-live.mjs` retries on that basis until a build lands:

```bash
node scripts/deploy-until-live.mjs                   # this repo's app
APP_DIR=/path/to/copy node scripts/deploy-until-live.mjs   # a second instance
```

It trusts only the API, publishes a built draft to live (a built draft does not
go live on its own), and stops itself if the platform ever reclassifies the
failure as something this app owns.

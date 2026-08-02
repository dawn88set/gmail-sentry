# Support request — ready to send

**To:** support@claritty.ai
**Subject:** Draft build failing since 20 Jul — need the CodeBuild log (app 7e925d43, submission 6819e987)

Paste the block below. Everything in it is verified; nothing is a guess.

---

Hi,

Every draft build of my app has failed since **2026-07-20T19:36:07Z**, always
with the same generic string, and the platform doesn't expose enough for me to
act on it. I've ruled out my own code as thoroughly as I can from outside your
AWS account — details below — so I need one thing from you: **the CodeBuild log
for the failing draft build.**

**IDs**

| | |
|---|---|
| App | `7e925d43-7188-4d48-8a55-9eb203f59378` |
| Submission / template | `6819e987-ee90-457f-ae4d-0c41374bcc3e` |
| Draft lambda | `claritty-app-7e925d43-dft` |
| Account | dawn88set@gmail.com |
| Last successful `draftDeployedAt` | 2026-07-20T19:36:07.271Z |
| Most recent `draftErrorAt` | 2026-08-02T02:52:28.309Z |

**What the failure looks like**, polled every 30 s during a fresh
`claritty deploy` on 2026-08-01:

```
21:50:56  Preparing to publish
21:51:26  Building image · Preparing · 0.5m
21:51:56  Building image · Building  · 1.0m
21:52:27  Building image · Building  · 1.5m
21:52:58  Draft deploy failed        ← draftErrorAt 2026-08-02T02:52:28.309Z
```

It dies **~60–90 s into the build phase**. For reference, the full build takes
63 s on my machine, so this is either a build timeout set just below what this
app needs, or an early failure in a step I can't see.

`draftError` is only:

> Build failed. Please check that your app builds successfully locally. If
> issues persist, contact support with your submission ID.

and `GET /api/apps/:id/logs` returns four canned lines ("App started", "Database
connection established", "Server listening on port 3000", "Health check passed")
rather than build output — note it even reports port 3000, which isn't the port
this app uses.

**Your own API says this is on your side.** `GET /api/apps/7e925d43-…` returns:

```json
"errorAnalysis": {
  "type": "UNKNOWN", "userActionable": false, "fixable": true,
  "userMessage": "Something went wrong on our end. Please try again in a moment.",
  "technicalDetails": "Deployment was interrupted - please retry …"
}
```

and the app-level `error` is `"Deployment was interrupted - please retry"`. I
have retried repeatedly over twelve days.

**What I verified before writing to you**

1. Rebuilt the exact tarball the CLI uploads — same `tar` invocation and same
   `BUNDLE_EXCLUDES` as `create-claritty-app/src/index.ts:772`. **1.4 MB, 320
   files**, far under the CLI's 100 MB limit.
2. Extracted it to a clean directory (no working-tree contamination).
3. Built it with the platform-generated `Dockerfile` from my repo,
   `--platform linux/amd64`, `--no-cache`. **Builds in 63 s, exit 0.**
4. Ran that image: `/health` → 200, `/api/*` → 401 without `X-User-ID` (correct),
   Alembic migrates to head against Postgres.
5. `claritty doctor` passes every check, including your authoritative
   platform-side manifest dry-run.
6. `claritty deploy` passes all five pre-flight gates (seed-verify, identity,
   type-check, build, widget-tests).

**Why I think the failing image isn't one I can test.** My app's
`infrastructure.lambda.imageUri` is `…:1.0.0-lambda` and the function is
`claritty-app-7e925d43`, so you build a **Lambda** image. The Dockerfile in my
repo is the **Fargate** variant — its own header says
`Platform: linux/amd64 (AWS Fargate requirement)` and it runs nginx +
supervisor, which is not a Lambda entrypoint. So the Dockerfile that actually
fails is generated on your side at build time and I have no way to build or read
it. That would explain why every local reproduction passes.

**The ask:** please send the CodeBuild log for the draft build of
`claritty-app-7e925d43-dft`. If it turns out to be a timeout, I'd also like to
know the current limit.

---

## Two separate bugs, worth their own tickets

### 1. The CLI reports success for a failed deploy

On the run above, `claritty deploy --yes` printed:

```
✓ Gmail Sentry is live in your workspace
```

**about 90 seconds before the draft build failed**, and the live app was never
touched. `waitForUploadDeploy` polls `GET /api/apps/templates/direct/:appId`,
which returns the app's *current* status — already `ACTIVE` from an earlier
successful deploy — so it can never observe the draft outcome.

The effect is that a failed deploy is indistinguishable from a successful one
from the CLI, which is how this went unnoticed for twelve days. It should poll
the draft (`draftDeployedAt` / `draftError`) and exit non-zero on failure.

Related, and undocumented outside a source comment
(`upload-deploy.processor.ts:63`): a CLI re-deploy of an already-live app builds
only the **draft**, and going live needs a separate "Publish to live". The CLI's
wording ("is live in your workspace") states the opposite.

### 2. `GET /api/apps/:id` returns the tenant database password

The `infrastructure` object in that response includes `databasePassword` and a
full `databaseConnectionString` with the credential inline, to any caller
holding a session token. Even scoped to the app owner, a live RDS credential
does not belong in an app-metadata response — it ends up in browser devtools,
proxy logs, CI output, and terminal scrollback.

Please rotate the credential for
`tenant_7ac1b8d7_app_f90d5653` (mine has been exposed in local logs), and
consider removing the field from this endpoint.

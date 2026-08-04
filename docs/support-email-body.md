Subject: Build succeeds only in intermittent windows — need the CodeBuild log (app 7e925d43)

Hi,

**Your image build works only in windows.** Inside a window everything deploys;
outside one, everything fails — brand-new apps and redeploys alike, my app and
an untouched `create-claritty-app` seed alike. Nothing about the app being
deployed predicts the outcome; only the time does.

Observed good windows (UTC):

    2026-08-02  16:38 – 17:29
    2026-08-03  ~01:57 – 13:17

Everything outside them failed. Two observations pin it down:

* **Same app, same bytes, 29 minutes apart.** An app deployed successfully at
  13:17Z. The very next deploy of identical source to that same app failed at
  13:46Z, and again at 13:55Z.
* **A pristine seed and my full app behave identically.** `npx
  create-claritty-app`, untouched, deployed fine at 01:57Z. My complete
  application deployed fine at 13:17Z and is serving `/health` 200 today. Both
  fail now.

So "check that your app builds successfully locally" cannot be the issue. My
app builds locally, builds in your pipeline during a window, and is running in
your infrastructure right now.

**The build itself succeeds — the failure is after it.** Polling
`installationStep` through a deploy on 2026-08-03:

```
15:13:34  Building image · Building · 0.5m
15:14:15  Building image · Done · 1.5m      <- image built
15:14:56  Draft deploy failed: Build failed…
```

Your own pipeline reports the image as **Done**, then fails ~40 seconds later,
and the message shown to the developer still says "Build failed. Please check
that your app builds successfully locally." So the failing step is whatever
happens after the image is built — ECR push, Lambda update, or the post-deploy
health check — and the error text points developers at the one thing that is
demonstrably fine. It also auto-retried once and failed the same way
(`draftErrorAt` moved twice, 15:14:45 then 15:16:35).

**Your own API already classifies this as your problem.** The developer-facing
message says to check that the app builds locally, but `GET /api/apps/:id`
carries a different verdict on the very same failure:

```json
"error": "Deployment was interrupted - please retry",
"errorAnalysis": {
  "type": "UNKNOWN", "severity": "medium",
  "userActionable": false,
  "userMessage": "Something went wrong on our end. Please try again in a moment."
}
```

`userActionable: false` and "on our end" is the correct diagnosis. Please show
*that* text to developers instead — the current wording sent me through about
fifty deploys, a byte-level bisect of `app-config.json`, and a pristine-seed
control, all to rule out an app that your own analyzer had already cleared.

**Recorded-successful builds may not be serving.** `claritty doctor` passes
every check on this app, including your platform dry-run
(`✓ platform dry-run: manifest valid (runnable + fired)`). Yet the app renders
a two-item `Inbox | Rules` navigation, which exists only in commit `5cb0420`
(2026-07-03). The two builds your API records as successful —
`deployedAt 2026-08-02T16:42:58` and `draftDeployedAt 2026-08-02T17:29:03` —
were both built from commit `2294185`, whose navigation has five items
(`Today | Follow-ups | Alerts | Activity | Rules`). So the running container is
roughly a month older than the build the API reports.

I can't fully close this one from outside, and I'd rather flag it than overstate
it: the Draft pane may simply be falling back to the installed build because the
newest draft failed, which would explain the screen without implying the 2 Aug
build never served. I can't distinguish the two, because the app origin
`7e925d43-….apps.claritty.ai` answers `403 {"error":"Forbidden"}` to every path —
`/`, `/api/*`, with a bearer token and without, from curl and from a signed-in
browser alike. There is no way for a developer to ask the deployed container
what code it is running. If `deployedAt` can move while the old image keeps
serving, that is a more serious bug than the build failures, and it would be
invisible to every developer on the platform.

**Two independent failures, and the second is the one that matters.**

The submission record for `6819e987` carries a `failureReason` that is never
shown in the CLI or the UI:

```
Validation failed after 1 attempts:
GitHub access failed: GitHub App not connected.
Please connect your GitHub account to continue.
```

That is real and actionable — but it is *not* what breaks the builds, and the
control that shows it is clean. `claritty deploy` uses the direct-upload path
(`POST /api/apps/templates/direct`), which never touches GitHub. I deployed the
identical source to a brand-new template with `githubRepoUrl: None`
(`a6aff507-aa49-4752-b1ff-41cd2ec99805`), so no GitHub check could run at all:

```
Scanning + building + deploying… (failed)
✗ Build failed. Please check that your app builds successfully locally.
```

So the image build fails for direct uploads with no GitHub involvement
whatsoever. Please treat the two separately — and note that
`githubRepoUrl` cannot be cleared to route around it: `PATCH` with `null` is
accepted (HTTP 200) but silently ignored, `""` is rejected (HTTP 400), and each
attempt increments `resubmissionCount` as a side effect. That field appears to
be write-once, which permanently welds a template created from GitHub to a
validation path its owner may no longer want.

**The ask:** the CodeBuild log for any failing build of
`claritty-app-7e925d43-dft`. Failures die ~60–90s into "Building image", while
successful builds take ~3 minutes — so they're failing early rather than timing
out, and the log should say why in one line.

The practical impact is severe: Gmail Sentry
(`7e925d43-7188-4d48-8a55-9eb203f59378`) first went live 2026-07-20 and has not
been updatable since. Roughly 50 deploys, all failed.

**A third path is broken too, and this one has an exact cause.** Trying to
install the app into my own workspace:

```
POST /api/marketplace/install  {"templateId":"6819e987-…"}
→ 400  DatabaseError
   pg 42703: column AppPurchase.paymentProvider does not exist
```

That is a migration missing on your production database, not anything to do
with my app — the endpoint fails before it looks at what is being installed. It
means self-install is unavailable as a workaround for the build problem.

Two related bugs worth their own tickets:

1. **The CLI reports success for a failed deploy, and failure for a running
   one.** `claritty deploy` printed "✓ <app> is live in your workspace" at
   08:53Z for a build that failed at 08:55Z. It also printed "✗ Deploy failed"
   at 14:05Z for an app the API still showed as DEPLOYING. `waitForUploadDeploy`
   polls the app's *current* status — already ACTIVE from a previous deploy — so
   it can never observe the real outcome. This is why the problem went unnoticed
   for twelve days.

2. **`GET /api/apps/:id` returns the tenant Postgres password** and full
   connection string in `infrastructure`, to any caller with a session. Please
   rotate the credential for `tenant_7ac1b8d7_app_f90d5653` and consider
   dropping the field from that response.

Account: dawn88set@gmail.com · submission `6819e987-ee90-457f-ae4d-0c41374bcc3e`

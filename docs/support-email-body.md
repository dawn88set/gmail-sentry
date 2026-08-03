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

**The ask:** the CodeBuild log for any failing build of
`claritty-app-7e925d43-dft`. Failures die ~60–90s into "Building image", while
successful builds take ~3 minutes — so they're failing early rather than timing
out, and the log should say why in one line.

The practical impact is severe: Gmail Sentry
(`7e925d43-7188-4d48-8a55-9eb203f59378`) first went live 2026-07-20 and has not
been updatable since. Roughly 50 deploys, all failed.

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

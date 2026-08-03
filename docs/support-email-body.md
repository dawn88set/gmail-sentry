Subject: Draft build path is broken — a live app can never be updated (app 7e925d43)

Hi,

**Your DRAFT build path is broken. The LIVE build path works.** The practical
effect is that once an app has gone live it can never be updated again, because
every update builds the draft.

I proved this today by deploying ~15 apps, and the split is perfect:

| app state at deploy time | which runtime is built | result |
|---|---|---|
| no live instance yet (`deployedAt` null) | LIVE | **succeeds** |
| already live (`deployedAt` set) | DRAFT | **fails** |

Successes — all first deploys, all today:
  * a pristine `npx create-claritty-app` seed, untouched  → live 01:57Z
  * that seed + my frontend                               → live 02:05Z
  * my complete application, backend and frontend         → live 13:17Z

Failures — all redeploys of an app that was already live:
  * Gmail Sentry `7e925d43-7188-4d48-8a55-9eb203f59378`, every attempt since
    2026-07-20 (~50 of them)
  * the app I just deployed successfully at 13:17Z — the very next deploy of
    the SAME code to the SAME app failed at 13:46Z and again at 08:55Z

That last pair is the cleanest evidence: identical source, identical app,
twenty-nine minutes apart. It went live once, then became permanently
un-updatable.

**This is not app code.** My full application deploys and runs — `/health`
returns 200 on `f15d06b3-be89-45e3-b75d-dfa80b455e49`. A pristine seed with no
edits at all behaves identically: fine on first deploy, and it too would be
stuck the moment it went live.

**The ask:** the CodeBuild log for a failing DRAFT build of
`claritty-app-7e925d43-dft`. Given the split above I'd start by comparing how
the draft image build is configured against the live one — they clearly diverge.

Two related bugs worth their own tickets:

1. **The CLI reports success for a failed deploy.** `claritty deploy` prints
   "✓ <app> is live in your workspace" while the draft build is still running,
   and it prints exactly the same thing when that build then fails. I watched it
   claim success at 08:53Z for a build that failed at 08:55Z.
   `waitForUploadDeploy` polls the app's *current* status, which is already
   ACTIVE from the previous deploy, so it can never observe the draft outcome.
   This is why the problem went unnoticed for twelve days.

2. **`GET /api/apps/:id` returns the tenant Postgres password** and full
   connection string in `infrastructure`, to any caller with a session. Please
   rotate the credential for `tenant_7ac1b8d7_app_f90d5653` and consider
   dropping the field from that response.

Account: dawn88set@gmail.com · submission `6819e987-ee90-457f-ae4d-0c41374bcc3e`

(I created several probe apps while isolating this — "Probe Services", "Probe
Frontend", "Probe Backend", "Probe BackendOnly", "Inbox Sentry", "Claritty
Template". Please feel free to delete them.)

# Support request — submission stuck in DRAFT validation

> Copy the message below to Claritty support. Everything it references is
> verifiable from the CLI output quoted at the bottom.

---

**Subject:** Submission `6819e987-ee90-457f-ae4d-0c41374bcc3e` has no `githubRepoUrl` — validation can't start

Hi,

My app **Gmail Sentry** (submission `6819e987-ee90-457f-ae4d-0c41374bcc3e`,
account `dawn88set@gmail.com`) is stuck: `validation: DRAFT`,
`marketplace: PENDING_REVIEW`, and validation never progresses.

`claritty deploy --repo` returns:

```
HTTP 400 {"success":false,"error":"Bad Request",
"message":"Failed to start validation: Submission 6819e987-ee90-457f-ae4d-0c41374bcc3e
has no githubRepoUrl — validation pipeline only handles developer submissions"}
```

The submission was originally created as a **direct upload**, so it has no
`githubRepoUrl`. I've since published the source to a public repo, but I can't
attach it:

- `claritty deploy --repo https://github.com/dawn88set/gmail-sentry` still
  resolves to this submission and returns the 400 above.
- Clearing `templateId` from `.claritty.json` doesn't create a new submission —
  the platform matches the app server-side ("Existing app found —
  re-deploying…") and returns to `6819e987`.
- The CLI (v0.7.1) has no `delete` / `unpublish` / `rename` command.

So there's no client-side path to a GitHub-backed submission without renaming
the app, which I'd rather not do.

**Could you either:**

1. attach `githubRepoUrl: https://github.com/dawn88set/gmail-sentry` (branch
   `main`) to submission `6819e987-ee90-457f-ae4d-0c41374bcc3e`, **or**
2. delete that submission so a fresh `claritty deploy --repo …` can register it
   cleanly?

Either unblocks me. Note the `PENDING_REVIEW` state predates this — I suspect
that review has been waiting on the same stalled validation for a while.

For reference, everything on my side is green:

- Repo is public with CI passing: https://github.com/dawn88set/gmail-sentry
  (`Validate Clarity App`, `Test Deployment`, `seed-verify` all green on `main`)
- `claritty doctor` — all checks passed
- `claritty deploy --dry-run` — all five pre-flight gates pass
  (seed-verify, identity, type-check, build, widget-tests)
- `claritty deploy --yes` succeeded: the app is live in my workspace

Thanks,
Shahar Cohen

---

## Reference — CLI output

```
$ claritty status --app-id 6819e987-ee90-457f-ae4d-0c41374bcc3e
  validation:  DRAFT
  marketplace: PENDING_REVIEW
  still validating — re-run `claritty status` shortly.

$ claritty deploy --yes --repo https://github.com/dawn88set/gmail-sentry
✓ pre-flight gates passed
✓ signed in as dawn88set@gmail.com
✓ manifest valid (platform dry-run)
› Submitting to your workspace…
  Existing app found — re-deploying…
✗ re-validate failed: HTTP 400 … has no githubRepoUrl …

$ claritty deploy --yes          # direct-upload path
✓ Gmail Sentry uploaded (6819e987-ee90-457f-ae4d-0c41374bcc3e)
✓ Gmail Sentry is live in your workspace
```

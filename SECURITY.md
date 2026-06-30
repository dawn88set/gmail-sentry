# SECURITY.md — The three-circle secret contract

Claritty apps run on infrastructure the platform owns. The seed repo
(this directory) is the **innermost circle** of trust: it carries the
declarative manifest and the custom Python the agent runs, but nothing
sensitive. This file codifies that boundary so you and your AI
assistant know exactly what stays out.

---

## The three circles

```
┌─ Authoring ─ Claude Code, IDE, planner prompts ─────────┐
│   sees:    catalog metadata (ids, descriptions,         │
│            intent hints, authType, providedToolIds),    │
│            schema, user intent, intelligence.yaml, custom code   │
│   NEVER:   client_id, client_secret, OAuth tokens,      │
│            KMS material, CLARITTY_INTERNAL_SECRET,      │
│            encrypted credentials                        │
│   guard:   Catalog manifests carry zero secret fields.  │
│            CatalogRegistryService.getSummary() strips   │
│            any field that smells. The same call powers  │
│            the planner prompt AND the INDEX dumped to   │
│            the seed.                                    │
│                                                         │
│  ┌─ Build ─ materializer + `claritty seed verify` ───┐  │
│  │   sees:    Authoring set + validator rules        │  │
│  │   NEVER:   anything the authoring layer can't     │  │
│  │   guard:   Materializer copies catalog .tmpl      │  │
│  │            files verbatim and never injects       │  │
│  │            creds; `claritty seed verify`          │  │
│  │            HARD-FAILS commits containing token-   │  │
│  │            shaped strings (see scanner rules).    │  │
│  │                                                   │  │
│  │  ┌─ Runtime ─ deployed app on ECS ─────────────┐  │  │
│  │  │   sees:    intelligence.yaml, CLARITTY_INTERNAL_     │  │  │
│  │  │            SECRET (env-injected, never      │  │  │
│  │  │            logged), CLARITTY_PLATFORM_URL,  │  │  │
│  │  │            per-invocation ephemeral         │  │  │
│  │  │            credentials scoped to the        │  │  │
│  │  │            function call stack              │  │  │
│  │  │   NEVER:   long-lived OAuth tokens, KMS     │  │  │
│  │  │            keys, other users' creds         │  │  │
│  │  │   guard:   Credentials.__repr__ redacts;    │  │  │
│  │  │            logger filter strips token       │  │  │
│  │  │            fields; ENABLE_DEBUG=False       │  │  │
│  │  │            enforced in prod boot; 404       │  │  │
│  │  │            errors redact userId             │  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## Things you NEVER write to this repo

- **OAuth client_id / client_secret.** Platform owns one OAuth client
  per provider, stored in AWS Secrets Manager. Apps consume per-user
  tokens via the runtime credential fetch — they don't authenticate
  to providers themselves.
- **Access tokens / refresh tokens / api keys.** Even for testing.
  Use the `CLARITTY_FAKE_CREDS_<INTEGRATION_ID>` dev pattern in
  `.env` (which is `.gitignored`).
- **`CLARITTY_INTERNAL_SECRET`.** Runtime-injected by ECS, used to
  authenticate platform callbacks. Never appears in source or images.
- **`INTEGRATION_OAUTH_STATE_SECRET`, `INTEGRATION_KMS_KEY_ID`.**
  Platform-only.
- **KMS data keys, envelope-encrypted credential blobs.** The seed
  never holds these in memory longer than one function-call stack.
- **Hard-coded URLs to internal endpoints.** Use the SDK's
  `ctx.integration(...)` and let `CLARITTY_PLATFORM_URL` resolve at
  runtime.

If a piece of source code contains one of these by mistake,
`claritty seed verify` blocks the commit. There is no `--force`.

---

## Things you NEVER log

In any custom tool, agent, or background script:

```python
# WRONG — leaks the credential into CloudWatch:
logger.info(f"calling gmail with token {creds.access_token}")
logger.info(f"creds: {ctx.integration('gmail')!r}")

# Also wrong — the entire response carries cred-bound headers:
logger.info(f"gmail response: {response.headers}")

# Right — log identifiers, not material:
logger.info(f"sending email for user={ctx.user_id} via gmail")
```

The SDK's `Credentials.__repr__` is redacted and the runtime logger
filter strips `access_token` / `refresh_token` / `api_key` / `secret`
fields from any structured log record — but those are **backstops**,
not your safety net. Don't put secrets into `print()`, f-strings, or
debug exception messages.

---

## What lives where at runtime

| Symbol | Where it lives | Set by | Rotatable? |
|---|---|---|---|
| `CLARITTY_INTERNAL_SECRET` | ECS env, in-memory only | Platform at deploy | Yes (manual; re-deploy required) |
| `CLARITTY_PLATFORM_URL` | ECS env | Platform at deploy | Trivially |
| `CLARITTY_AUTH_TOKEN` | ECS env | Platform at deploy | Yes |
| `CLARITTY_FAKE_CREDS_<ID>` | `.env` (dev only — `.gitignored`) | You | Trivially |
| Encrypted OAuth tokens | Platform DB | OAuth flow | Per-user revoke |
| Decrypted creds at runtime | Function-stack only | `ctx.integration(...)` | Per-invocation |

The `.env` file at the seed root is `.gitignored` — never commit it.
Even with the scanner, slipping a real token into `.env` and then
copy-pasting it into a tool file would defeat the gate.

---

## What `claritty seed verify` checks

Per [`Phase 5.8`](.) of the master plan, the CLI runs in pre-commit
hooks and in CI. It hard-fails on:

1. **Invalid `intelligence.yaml`** — shape, cross-references against the catalog
2. **Invalid custom-tool / custom-agent source** — signature, decorator,
   banned imports, byte ceiling (rules:
   [`catalog/validators/custom-tools.rules.yaml`](catalog/validators/custom-tools.rules.yaml))
3. **Token-shaped strings** under `backend/` matching the scanner
   blocklist (`gh_*`, `sk-*`, `xoxb-`, `AKIA*`, PEM markers, etc.)

Exit codes:

- `0` everything passes
- `1` invalid shape
- `2` reference error
- `3` setup error (no intelligence.yaml, no catalog)
- `4` secret-shaped string found

Allowlist legitimate false positives (one regex per line) in
`.claritty-allowlist`. **Think twice before adding an entry** — most
matches are real.

---

## If you find a leak

1. **Rotate the credential immediately** at the provider (Gmail OAuth
   client, Slack token, etc.).
2. Open an issue tagged `security` on the platform repo.
3. Do not push a fix that just removes the line — the commit history
   carries it. Rotate first; the commit history is auditable.

---

## Why the boundary is this strict

Every Claritty app the platform generates will be open-sourced or
shared as a template at some point. The 2026-06-03 architecture audit
identified the three-circle model as the only design that's safe at
that scale. If the gate were "warn-only", a single missed leak in one
shared app could compromise every user of that app. Hard-fail is the
cost of the model working.

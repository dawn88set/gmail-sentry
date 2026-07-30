"""
Gmail Sentry's integration layer.

Connecting is PLATFORM-OWNED — the host runs OAuth and the broker holds the
decrypted token, so this package contains no OAuth machinery and no
credential-write API. What lives here:

- `gmail_ops` / `notify` — app-owned verbs that call the broker via
  `backend.shared.adapters.execute_tool`. The token never enters app code.
- `store` / `crypto` — the encrypted local credential store, used only by the
  self-host fallback path in `backend.shared.adapters` when there is no
  platform to broker to.

Never read provider keys from environment variables and never hand-roll OAuth.
"""

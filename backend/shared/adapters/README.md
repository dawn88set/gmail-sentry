# Integration adapters (B3)

Thin, typed wrappers over the per-user encrypted credential store so app code and
the HITL `/approve` path call `gmail.send(...)` / `slack.post_message(...)`
instead of re-authoring OAuth/HTTP per app.

## The contract every adapter follows

- Read creds with `load_credentials(db, user_id, SERVICE)` — it raises
  `IntegrationNotConnected` when there's no usable credential.
- A real API/HTTP failure → raise `IntegrationError`.
- A "write" verb returns `{"external_id": "<real id>", "account": "<who/where>"}`.
  **Never** return a success without a real external id — the route factory
  treats a missing id as a failure (this is the platform's "never fake success"
  rule, enforced in `backend/shared/item_routes.py`).
- After a call that may refresh tokens, persist them with `persist_refreshed`.
- Expose `test_connection(db, user_id) -> {"ok": bool, ...}` and register the
  service in `_LIVENESS` (in `__init__.py`) so `/api/integrations/{id}/test`
  picks it up automatically.

## Status

| Provider | Module | State | Notes |
|----------|--------|-------|-------|
| Gmail | `gmail.py` | ✅ real | wraps the existing `GmailClient`; `list_unread`, `get_message`, `send`, `test_connection`. Returns the Gmail message id. |
| Slack | `slack.py` | ✅ real | `chat.postMessage` via bot token (returns `ts`); `auth.test` liveness. Uses bot token, not an incoming webhook (a webhook returns no id). |
| Google Calendar | `gcal.py` | ⛔ not shipped | needs the platform OAuth model resolved (prereq #1) + API-verified client. Add `create_event`, `list_events`. |
| Google Drive | `gdrive.py` | ⛔ not shipped | add `list_files`, `get_file`, `upload`. |
| CRM (HubSpot/Salesforce/Pipedrive) | `crm.py` | ⛔ not shipped | one interface, per-provider impl behind it: `upsert_contact`, `create_note`, `update_deal`. |
| Accounting (Stripe + generic) | `accounting.py` | ⛔ not shipped | `list_invoices`, `list_overdue`; Stripe invoice id is the external id. |

**Do not ship a `⛔` adapter that fakes success.** Until its client is real and
verified, an app that needs it should surface a connect/not-implemented state —
never a fabricated external id. This is what keeps live demos honest.

To add one: copy the shape of `slack.py` (apikey) or `gmail.py` (oauth),
implement the verbs against the real API, return real external ids, add a
`test_connection`, and register it in `_LIVENESS`.

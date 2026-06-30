# Connecting external services (do this when your app acts on the outside world)

> If your app's core verb hits an external system — **post** to LinkedIn, **send** an email,
> **charge** with Stripe, **sync** to Notion — then "generate the content" is only half the app.
> You MUST also ship a way for the user to **connect** that service, or the app can't do its job.
> The AI assistant should add this **proactively**, even if the user didn't name the platform.

Integrations are **platform-owned**. The user connects a service once (OAuth/API key) through the
platform; credentials are stored **encrypted at rest (KMS) on the platform**, never in the app's own
database and never in the app's env. Your code reaches a connected service through the SDK — it never
sees raw OAuth client secrets.

---

## The rule (read this — it's the #1 thing apps get wrong)

If the app's **external action** is non-empty, do all three:
1. **Declare** the integration in `intelligence.yaml#integrations` (`- id: <id>`). That is the whole
   "connect" surface — the **Claritty platform** owns connecting it: it lists the app's declared
   integrations and runs OAuth on the app's **Intelligence** and **Settings → Integrations** tabs
   (and intercepts the `claritty:connect-integration` postMessage). **Do NOT build an in-app
   Integrations page, a "connect N services" banner, or an Integrations nav item** — that just
   duplicates platform UI.
2. the **action**, performed through a real catalog tool (e.g. `linkedin.create_post`),
3. **honest failure**: when the service isn't connected, surface a clear "connect X to do this"
   state (HTTP **409** from the route, an inline prompt at the action) — and when the external call
   fails, surface the error.

**NEVER fake success.** Do not "simulate" a post, do not swallow the error and mark the row as done,
do not downgrade `posted` → `approved` in an `except`. A user who clicks Approve and sees "posted"
must actually have a post on LinkedIn. Faking it is the worst possible outcome — it hides a broken app.

---

## How an agent or tool reaches a connected service

Inside a `@tool` handler (or an agent's tools), call `ctx.integration("<id>")` — or use the
integration's **provided catalog tool** directly. The catalog ships real tools; e.g. the `linkedin`
integration provides `linkedin.fetch_posts` and `linkedin.create_post`. Reference them by their
dotted id in your agent's `system_prompt` and list them in `intelligence.yaml#agents[].tools`; the tool-use
loop dispatches them. A provided tool returns `{"error": "<id>_not_connected"}` when the user hasn't
connected the service — handle that, don't crash.

```python
from claritty_sdk import tool, ToolCtx

@tool(id="app.publish_draft")
def publish_draft(input: dict, ctx: ToolCtx) -> dict:
    li = ctx.integration("linkedin")          # ConnectedIntegration or None
    if li is None:
        return {"error": "linkedin_not_connected"}
    # ... call li / a provided tool; raise on a real failure, never fake a post id.
```

Agents do **not** call the LLM or import `openai`/`requests` themselves, and do **not** call a
`run_tool()` helper (there is none). They declare tools in `intelligence.yaml`; the loop invokes them.

---

## Publishing from a human-in-the-loop route (the Approve button)

When the user approves a draft, the route should invoke the real publish tool and translate the
result into honest HTTP:

```python
import inspect
from claritty_sdk import decorators as _sdk
from claritty_sdk.context import ToolCtx
from claritty_sdk.integrations.client import make_resolver

@router.post("/{item_id}/approve")
async def approve_post(item_id: str, db=Depends(get_db), user_id: str = Depends(require_user)):
    row = _get_owned_draft(db, item_id, user_id)        # 404 if missing, 400 if not a draft
    handler = _sdk.get_registered_tool("linkedin.create_post")
    if handler is None:
        raise HTTPException(500, "publish tool not registered")
    ctx = ToolCtx(user_id=user_id, integration_resolver=make_resolver(user_id, optional_ids=set()))
    result = handler({"text": row.draft_text}, ctx)
    if inspect.isawaitable(result):
        result = await result
    if isinstance(result, dict) and result.get("error") == "linkedin_not_connected":
        raise HTTPException(409, "LinkedIn not connected — connect it to publish")
    post_id = result["post_id"]                          # KeyError → 500; do NOT swallow
    row.status, row.external_id = "posted", str(post_id)
    db.commit(); db.refresh(row)
    return row.to_dict()
```

A missing connection is a **409** (the UI turns it into a connect prompt); a real LinkedIn failure
bubbles up as a 5xx with the row left un-posted for retry. Only a genuine `post_id` flips to `posted`.

---

## Frontend — do NOT build a connect surface

The Claritty platform already owns connecting integrations. Once the app **declares** them in
`intelligence.yaml#integrations`, the platform shows them — with Connect / Bind / Disconnect + OAuth
— on the app's **Intelligence** tab and **Settings → Integrations** tab. So:

- **Do NOT** ship an in-app Integrations page, a `SetupChecklist` / "Connect N services" banner, or
  an Integrations nav item. The seed deliberately ships none — don't add one.
- The only connect-related UI in the app is the **inline 409 prompt** at the action ("LinkedIn isn't
  connected — connect it on the Integrations tab to publish"), shown when a publish returns the
  not-connected state. Nothing standalone.

---

## Secrets

- **Production:** the platform injects `CLARITTY_PLATFORM_URL` + `CLARITY_INTERNAL_SECRET`; the SDK
  uses them to fetch the user's decrypted credentials at call time. You store nothing.
- **Local:** set `CLARITTY_FAKE_CREDS_<INTEGRATION>` to a JSON bundle (e.g.
  `CLARITTY_FAKE_CREDS_LINKEDIN='{"access_token":"…","sub":"…"}'`) to exercise the path without OAuth.
- Keep using `claritty_sdk.llm.get_llm_client` for the model — that's separate from user integrations,
  and agents should not call it directly (the tool-use loop drives the model).

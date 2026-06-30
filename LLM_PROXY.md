# LLM Proxy — Calling AI Models from Your App

Every Claritty-deployed app routes its LLM calls through a **proxy hosted by the platform**, instead of calling Anthropic / OpenAI / etc. directly. This is a hard rule (the `LlmComplianceValidator` blocks deploy + marketplace publish on direct provider imports). This doc explains why, and how.

---

## TL;DR

```python
# backend/agents/my_agent.py
from claritty_sdk.llm import get_llm_client

client = get_llm_client("claude-sonnet-4-6")
result = client.chat([{"role": "user", "content": "Hello"}])
print(result.content)
```

```ts
// frontend/src/components/Widget.tsx — the frontend NEVER calls an LLM directly.
// It calls YOUR app's Python backend, which calls the proxy via claritty_sdk.
import axios from "axios";
const r = await axios.post("/api/summarize", { text: "Hello" });
console.log(r.data.summary);
```

No API keys, no provider imports, no LLM SDK in the frontend, no `baseURL` config. The platform injects everything via env vars into the backend at deploy time.

---

## Why the proxy is mandatory

Three reasons:

1. **End-user billing.** When your app is in someone else's workspace and they run it, the LLM tokens come out of *their* plan — not yours. The proxy looks up the running user's account, applies their plan's quota, and either uses their BYOK key (free, unmetered) or Claritty's pooled key (counts against their token budget, with a small tier markup).
2. **Budget enforcement.** When a user hits their monthly budget, the proxy returns `HTTP 402 { reason: 'TOKEN_BUDGET_EXCEEDED' }` and the Claritty platform pops a paygate banner with an upgrade CTA. Direct provider calls would just bill the user's credit card opaquely with no UX.
3. **Provider portability.** Routing through the proxy means we can swap Anthropic for Bedrock (or add Google, Cohere, …) without changing your app.

---

## Available models

You pass any model id the underlying provider accepts. The proxy routes by prefix:

| Model id (examples) | Provider | Pricing tier |
|---|---|---|
| `claude-sonnet-4-6`, `claude-opus-4-7`, `claude-haiku-4-5-20251001` | Anthropic | varies |
| `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`, `gpt-3.5-turbo`, `o1-preview`, `o1-mini`, `o3-mini` | OpenAI | varies |

Unknown model ids default to Anthropic. New providers / model ids land in `clarity-api/src/modules/llm-proxy/llm-proxy.service.ts` (server-side); your app code doesn't need to know.

---

## Python (`backend/**`)

### Install (already in the seed)

`backend/requirements.txt` already includes `claritty-sdk>=1.0.0,<2.0.0`. Nothing to add.

### Non-streaming

```python
from claritty_sdk.llm import get_llm_client

client = get_llm_client("claude-sonnet-4-6")
result = client.chat(
    [
        {"role": "user", "content": "Summarize: ..."},
    ],
    temperature=0.3,
    max_tokens=500,
    system="You are a concise summarizer.",
)

print(result.content)        # "..."
print(result.usage.total_tokens)
```

### Streaming

```python
client = get_llm_client("claude-sonnet-4-6")
for delta in client.chat_stream(messages=[{"role": "user", "content": "Tell a story"}]):
    print(delta, end="", flush=True)
```

### Handling 402 (budget exceeded)

```python
from claritty_sdk.llm import get_llm_client, LlmProxyError

try:
    result = client.chat([...])
except LlmProxyError as e:
    if e.status_code == 402:
        # The Claritty platform already shows a paygate banner to the user.
        # Just surface a friendly UI message and stop the workflow.
        return {"error": "Out of LLM budget. Please upgrade or add your own API key."}
    raise
```

---

## JS / TS (`frontend/**`)

**The frontend must NOT call LLMs directly and must NOT depend on any LLM SDK.**
There is no JS LLM SDK to install — do not add `@claritty/sdk` (or any LLM client)
to `frontend/package.json`. Direct frontend calls have latency/CORS/body-size
problems and bypass the per-app auth token the proxy needs.

When a widget needs LLM output, add a route to **your app's Python backend** (which
uses `claritty_sdk.llm`, see above) and call it from the frontend with plain
`axios`/`fetch`:

```python
# backend/routes/summarize.py
from fastapi import APIRouter
from pydantic import BaseModel
from claritty_sdk.llm import get_llm_client

router = APIRouter()

class SummarizeBody(BaseModel):
    text: str

@router.post("/api/summarize")
def summarize(body: SummarizeBody):
    client = get_llm_client("claude-sonnet-4-6")
    result = client.chat([{"role": "user", "content": f"Summarize: {body.text}"}])
    return {"summary": result.content}
```

```ts
// frontend/src/components/Widget.tsx
import axios from "axios";

const { data } = await axios.post("/api/summarize", { text: "..." });
console.log(data.summary);
```

This keeps token billing, budget enforcement, and provider portability working
(all handled by the backend SDK + proxy), and keeps the frontend dependency-free
of any LLM client.

---

## Environment variables (platform-injected, don't set manually)

The platform sets these on every deployed app:

| Var | Used for |
|---|---|
| `CLARITTY_LLM_PROXY_URL` | The proxy base URL (`{platform}/api/v1`) — SDK reads this. |
| `CLARITTY_AUTH_TOKEN` | Per-app token resolving to `(user, app)` server-side — SDK sends this as `Authorization: Bearer ...`. |
| `CLARITTY_PLATFORM_URL` | Platform base URL (fallback for the SDK if `CLARITTY_LLM_PROXY_URL` is missing). |

In local development (`docker-compose up`), set them yourself:

```sh
export CLARITTY_PLATFORM_URL=http://host.docker.internal:4000
export CLARITTY_AUTH_TOKEN=<your-dev-app-token>
```

---

## What the validator catches

`LlmComplianceValidator` scans `.py` / `.ts` / `.tsx` / `.js` / `.jsx` files and **hard-fails** on:

- Direct provider imports: `import anthropic`, `from openai import ...`, `import google.generativeai`, `import cohere`, `import mistralai`
- Direct client instantiation: `OpenAI(...)`, `AsyncOpenAI(...)`, `Anthropic(...)`
- Hardcoded API keys: `sk-ant-...`, `sk-proj-...`, `sk-...`

Skips: `node_modules/`, `.venv/`, `__pycache__/`, `dist/`, `.git/`.

If your app needs to call a provider the proxy doesn't support yet, **don't work around the validator** — open an issue. We add providers server-side; your app code doesn't change.

---

## FAQ

**Can I use the official `openai` / `@anthropic-ai/sdk` packages pointing at the proxy `baseURL`?**
The wire format IS OpenAI-compatible Chat Completions, so technically yes. But the validator's forbidden-import regex still hard-fails on `import openai` / `from openai import`. Use the Claritty SDK; it's a thin wrapper over the same wire format.

**Why isn't the Anthropic SDK whitelisted "just for typing"?**
Because the next person to copy that code pattern will use it for an actual call, bypass metering, and ship to the marketplace. The all-or-nothing rule keeps the policy enforceable.

**What if my user adds their own Anthropic key in settings?**
The proxy uses their key automatically — no app code change. Those calls don't count against the monthly budget (they're paying their provider directly).

**Does this affect local development?**
Locally you typically don't have a Claritty proxy running. Either point `CLARITTY_LLM_PROXY_URL` at your local `clarity-api` instance, or stub the LLM call in dev with an env-conditional fallback.

# GitHub Copilot Instructions - Clarity Agentic App Seed

## 🚨 Infrastructure Files - PROTECTED

**CRITICAL**: The following files are managed by the Clarity Platform and MUST NOT be modified. When suggesting code, NEVER recommend changes to:

### Protected Files

1. **`docker-compose.yml`** - Port configuration and service orchestration
2. **`frontend/Dockerfile`** - Build configuration with VITE_API_URL
3. **`frontend/nginx.conf`** - Nginx reverse proxy configuration
4. **`frontend/src/lib/api.ts`** - API client base URL (only the `API_BASE_URL` constant)

### Why Protected?

This template uses **monolithic container architecture** with Nginx reverse proxy:
```
Single Container (port 3200):
  ├── Nginx (serves frontend + proxies /api/*)
  └── FastAPI (port 8000, accessible via localhost)
  Managed by supervisord
```

**Key requirement**: use relative API URLs (empty `VITE_API_URL`) so the frontend calls `/api/...` on its own origin (nginx proxies to FastAPI). The app is self-hosted (Docker) — you host it yourself.

## ❌ NEVER Suggest These Patterns

### 1. Hardcoded Localhost URLs
```typescript
// ❌ WRONG - breaks production
const API_BASE_URL = 'http://localhost:8000';
const API_BASE_URL = 'http://localhost:8001';

// ✅ CORRECT - works everywhere
const API_BASE_URL = import.meta.env.VITE_API_URL || '';
```

### 2. Removing Nginx /api/ Proxy
```nginx
# ❌ WRONG - breaks API communication
location / {
    try_files $uri $uri/ /index.html;
}

# ✅ CORRECT - keeps proxy block (same container)
location /api/ {
    proxy_pass http://localhost:8000;
    # ... headers
}
location / {
    try_files $uri $uri/ /index.html;
}
```

### 3. Hardcoded Ports in docker-compose.yml
```yaml
# ❌ WRONG - conflicts with platform
ports:
  - "8000:8000"  # Hardcoded

# ✅ CORRECT - uses environment variables
ports:
  - "${BACKEND_PORT:-8000}:${BACKEND_INTERNAL_PORT:-8000}"
```

### 4. Setting VITE_API_URL to Localhost in Dockerfile
```dockerfile
# ❌ WRONG - breaks production
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=http://localhost:8001

# ✅ CORRECT - empty for relative URLs
ARG VITE_API_URL=
ENV VITE_API_URL=${VITE_API_URL}
```

## ✅ Safe Suggestions

You CAN suggest changes to:

### In `docker-compose.yml`:
- Adding environment variables for app-specific configuration
- Adjusting resource limits (memory, CPU)
- Adding volumes for data persistence
- Adding new services (but keep existing port patterns)

### In `frontend/nginx.conf`:
- Adding new `location` blocks for custom routes
- Adjusting cache settings for static assets
- Adding custom headers (preserving /api/ proxy)

### In `frontend/src/lib/api.ts`:
- Adding new API client methods
- Customizing request/response interceptors
- Adding authentication logic
- **NOT** changing the `API_BASE_URL` constant

### In `frontend/Dockerfile`:
- Changing Node version
- Adding build optimizations
- Installing additional dependencies
- **NOT** changing `VITE_API_URL` ARG/ENV

## 🎯 Widget Development Rules

**CRITICAL**: Platform supports EXACTLY three widget sizes (Apple HIG) — no others:
- **Small**: 170×170px (1:1 square)
- **Medium**: 360×170px (2.1:1 wide)
- **Large**: 360×360px (2:2 square)

### Widget Implementation Pattern

```typescript
// ✅ CORRECT - three sizes (see src/lib/widget-sizes.ts)
import type { WidgetSize } from '@/lib/widget-sizes';

export default function Widget({ size = 'medium' }: { size?: WidgetSize }) {
  if (size === 'small') return <SmallView />;   // 170×170px — one metric
  if (size === 'medium') return <MediumView />; // 360×170px — compact list
  return <LargeView />;                          // 360×360px — rich list
}
```

### Backend Widget Endpoint

```python
@app.get("/api/widget")
async def get_widget_data(
    size: str = "large",  # "small" | "medium" | "large"
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    if size == "small":
        return {"open_count": 3, "top_priority": "high"}  # minimal
    return {                                              # medium + large
        "open_count": 3,
        "tasks": [{"id": "...", "title": "...", "priority": "high"}],
    }
```

## 🏗️ Project Architecture

### Directory Structure

Focus development on these areas:

```
clarity-agentic-app-seed/
├── backend/
│   ├── agents/          ✅ Add your AI agents here
│   ├── workflows/       ✅ Add your workflows here
│   ├── triggers/        ✅ Add your trigger templates here
│   ├── main.py          ✅ Add API endpoints here
│   └── models.py        ✅ Add database models here
├── frontend/
│   ├── src/
│   │   ├── components/  ✅ Add React components here
│   │   ├── pages/       ✅ Add React pages here
│   │   └── lib/api.ts   ⚠️ Add API methods (NOT base URL)
│   ├── Dockerfile       🚫 DO NOT MODIFY
│   └── nginx.conf       🚫 DO NOT MODIFY (except adding locations)
└── docker-compose.yml   🚫 DO NOT MODIFY (except env vars)
```

### Monolithic Container Pattern

The Clarity Platform deploys ONLY ONE container per app. This template provides:
- Root `Dockerfile` that combines frontend + backend
- Supervisord to run both Nginx and FastAPI in same container
- Nginx proxies `/api/*` to `localhost:8000` (not `backend:8000`)

**DO NOT**:
- Separate into multiple Dockerfiles
- Use Docker Compose multi-service pattern in production
- Proxy to `backend:8000` (use `localhost:8000`)

### Required Patterns (v2 manifest-first — declare everything in `intelligence.yaml`)

#### 1. Agents are a system PROMPT, not an `execute()` method
```yaml
# intelligence.yaml — schema lives here
agents:
  - id: my-agent
    source: custom
    promptFile: backend/custom/agents/my_agent/prompt.md   # zero-Python (preferred)
    model: claude-sonnet-4-6
    tools: [app.save_item]
    input:  { user_id: { type: string, required: true } }
    output: { output: { type: string, required: true } }
```
```python
# Only if you need before/after/fallback hooks — NEVER def execute()/AgentResult:
from claritty_sdk import agent, AgentContext, BaseAgent
@agent(id="my-agent")
class MyAgent(BaseAgent):
    system_prompt = "…call tools by id, then __finish with {output}…"
    def fallback(self, ctx: AgentContext) -> dict: ...
```

#### 2. NEVER write the v1 shape
```python
# ❌ WRONG — the v2 runtime never calls execute() and rejects it at boot (app does nothing)
async def execute(self, context): return AgentResult(...)
# ❌ WRONG — agents don't drive the LLM or do HTTP; the tool-use loop does
get_llm_client(); import requests
```

#### 3. Workflows + triggers are YAML in `intelligence.yaml` (no Python files)
```yaml
workflows:
  - id: my-workflow
    inputs: { user_id: { type: string, required: true } }
    steps:
      - id: run
        agent: my-agent
        input: { user_id: "${input.user_id}" }
    outputs: { output: "${steps.run.output.output}" }
```

#### 4. User-Configurable Triggers (YAML, not hardcoded cron)
```yaml
triggers:
  - id: daily-task
    type: SCHEDULE                 # platform fires it; NO in-process cron/scheduler
    workflow: my-workflow
    configFields:
      - { key: time, type: time, required: true, label: "What time?" }
      - { key: timezone, type: timezone, required: true, label: "Timezone" }
```

## 📚 When Developer Needs Help

If developer asks about modifying protected files:

1. **Be careful** with infra files (`Dockerfile`, `nginx.conf`, `docker-compose.yml`):
   they're yours to change for self-hosting, but a mistake can stop the app from
   serving. Test with `docker compose up --build` after editing them.

2. **DIRECT** them to:
   - `README.md` - quick start + self-hosting
   - `.cursorrules` / `CLAUDE.md` - editing rules
   - `CLAUDE.md` - Comprehensive AI assistant guide

3. **EXPLAIN** why the file is protected (multi-service architecture, dynamic ports, relative URLs)

4. **SUGGEST** alternatives that don't require modifying protected files

## 🎓 Code Suggestion Guidelines

### DO Suggest:
- ✅ New agents declared in `intelligence.yaml#agents` (prompt in `backend/custom/agents/<id>/prompt.md`)
- ✅ New workflows as YAML in `intelligence.yaml#workflows` (NOT `backend/workflows/*.py`)
- ✅ New trigger templates as YAML in `intelligence.yaml#triggers` (NOT `backend/triggers/*.py`)
- ✅ New custom tools in `backend/custom/tools/<id>/impl.py` (`@tool(id)` `def run(input, ctx)`)
- ✅ New React components in `frontend/src/components/`
- ✅ New API methods in `frontend/src/lib/api.ts`
- ✅ Environment variables for app logic
- ✅ Widget implementations (3 sizes: 170×170, 360×170, 360×360)

### DON'T Suggest:
- ❌ Hardcoded localhost URLs
- ❌ Changing `API_BASE_URL` in `api.ts`
- ❌ Removing `/api/` proxy from `nginx.conf`
- ❌ Hardcoded ports in `docker-compose.yml`
- ❌ Setting `VITE_API_URL` to localhost in `Dockerfile`
- ❌ Widget dimensions other than 170×170 / 360×170 / 360×360

## 🚀 Summary for AI Code Suggestions

**Focus development on**:
- AI agents, workflows, and triggers
- React components and pages
- Database models and API endpoints
- Widget implementations (3 sizes: small/medium/large)

**Protect from modification**:
- Infrastructure files (docker-compose, Dockerfile, nginx.conf)
- API base URL configuration
- Port mappings and VITE_API_URL settings

**Key principles**:
- Use relative URLs (empty VITE_API_URL)
- Use environment variables for ports
- Keep /api/ proxy in nginx.conf
- Three widget sizes only: 170×170 (small), 360×170 (medium), 360×360 (large)
- Always use decorators and async patterns
- Always register new components in __init__.py

**When in doubt**: Direct developer to `README.md` / `CLAUDE.md`.

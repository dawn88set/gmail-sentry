# 🚀 Agentic App Seed - Claritty Platform Template

**Build production-ready agentic apps in minutes** - optimized for Claude Code

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Claritty Platform](https://img.shields.io/badge/Claritty-Platform_Ready-green.svg)](https://claritty.ai)

---

## 🎯 What is This?

A **minimal, best-practice, self-hostable template** for building agentic apps
(FastAPI + React + Postgres). You host it yourself — anywhere you can run Docker.
Its only Claritty dependencies are **the LLM (via the `claritty_sdk` proxy)** and
**the widget UI kit (`@clarittyai/widget-toolkit`)**.

**Perfect for:**
- Developers with an agentic app idea
- Anyone wanting to automate tasks with AI
- Shipping a real agentic app in hours, not weeks

**Developer workflow:**
```bash
1. npx create-claritty-app my-app   (scaffolds this template + .env for you)
2. Open in Claude Code, Cursor, or Codex
3. Brainstorm your app idea with AI
4. Implement agents/workflows/triggers + your UI
5. docker compose up --build  →  host it wherever you like
```

---

## ⚡ 5-Minute Quick Start

### 1. Scaffold your app
```bash
npx create-claritty-app my-awesome-app
cd my-awesome-app
# Clones this template, creates .env, and inits a fresh git repo for you.
# No API keys needed — AI runs through the Claritty platform proxy
# (and each agent's fallback(ctx) runs instead when no proxy is set locally).
```

> **Claude Code users:** install the plugin instead and run `/claritty:new my-awesome-app`:
> ```
> /plugin marketplace add Clarittyai/claritty-plugins
> /plugin install claritty@claritty
> ```
>
> **Prefer to clone manually?**
> ```bash
> git clone https://github.com/Clarittyai/agentic-app-seed.git my-awesome-app
> cd my-awesome-app && cp .env.example .env
> ```

### 2. Start Development Environment
```bash
docker-compose up -d
```

**That's it!** ✅
- **Frontend**: http://localhost:3200
- **Backend API**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

### 3. Open Claude Code & Brainstorm
```bash
code .  # Open in VS Code with Claude Code extension
```

In Claude Code, run:
```
/superpowers:brainstorming
```

**Tell Claude:**
- What problem your app solves
- What tasks should be automated
- When/how users want it to run
- **Its design identity** — palette, typography, landing page, app name/logo

**Claude will help you design:**
- AI agents for specific tasks
- Workflows to chain agents
- User-configurable triggers
- Widget interfaces (small & large)
- A distinct visual identity (so it doesn't look like this template)

> ⚠️ **This is a template — make the app your own.** Keep the platform contract,
> but completely replace the look (theme, landing page, logo, name). Run
> `rm .claritty-seed-pristine` to activate the **identity gate**
> (`npm run check:identity`, also a Claude Code Stop hook) which blocks "done"
> until you do. Full guide: **[IDENTITY.md](IDENTITY.md)**.

---

## 🏗️ What's Included

### Backend (FastAPI + Python)
```
backend/
├── agents/           # ONE minimal agent example
├── workflows/        # ONE minimal workflow example
├── triggers/         # ONE minimal trigger template
├── main.py           # Core API (ready to extend)
└── infrastructure/   # Auto-discovery (platform-managed)
```

### Frontend (React + TypeScript)
```
frontend/
├── src/
│   ├── components/Widget.tsx   # 3 widget sizes (small/medium/large)
│   ├── lib/widget-sizes.ts     # canonical widget dimensions
│   ├── pages/Dashboard.tsx     # Full app interface (Tasks example)
│   └── lib/api.ts              # API client
```

### Platform Integration
- ✅ **Dockerfile** (ECR Public Gallery, resilient builds)
- ✅ **Environment variables** (DATABASE_URL, PORT auto-injected)
- ✅ **Widget specifications** (Apple HIG: 170×170px, 360×170px, 360×360px)
- ✅ **Multi-tenancy** (user isolation built-in)
- ✅ **Health checks** (ALB-compatible)

---

## 🎨 Core Concepts

### 1. Agentic Apps = AI Workers on User's Schedule

**Traditional apps:** User does the work manually
**Agentic apps:** AI agents work automatically

**Example** (the seed's `example-agent`) — v2: the agent is a system prompt; the SDK's
tool-use loop runs it. No `execute()` method.
```python
@agent(id="example-agent")            # schema lives in intelligence.yaml
class ExampleAgent(BaseAgent):
    system_prompt = "You triage a task… call __finish with {priority, suggested_action}."
    def fallback(self, ctx): ...      # optional no-LLM local result
```

### 2. Widgets = Primary Interface

Users interact mainly through dashboard widgets (Apple HIG 3-size standard):
- **Small (170×170px)**: Single quick info
- **Medium (360×170px)**: List view, calendar, detailed + actions
- **Large (360×360px)**: Complex multi-row content

**NOT a traditional web app** - widgets come first!

### 3. User-Configurable Triggers

**You define templates (YAML in `intelligence.yaml`), users create instances:**
```yaml
triggers:
  - id: daily-review
    type: SCHEDULE
    workflow: my-workflow
    configFields:
      - { key: time, type: time, required: true }       # User picks time
      - { key: timezone, type: timezone, required: true } # User picks timezone
```
```
# User A: 9am EST   ·   User B: 6pm PST   ·   both run automatically (platform fires them)
```

---

## 📚 Documentation

### Core Guides (Start Here)
- **[CLAUDE.md](CLAUDE.md)** - AI assistant guide (for Claude Code / Cursor)
- **[WIDGETS.md](WIDGETS.md)** - Widget design specifications (3 sizes, the UI kit)
- **[LLM_PROXY.md](LLM_PROXY.md)** - calling Claude via the Claritty SDK proxy

### Detailed Reference (When Needed)
- **[docs/archive/](docs/archive/)** - Comprehensive guides (not loaded by default)

---

## 🔧 Common Tasks

Everything below is declared in **`intelligence.yaml`** (the v2 manifest the SDK runs). There are NO
`backend/workflows/*.py` or `backend/triggers/*.py` files.

### Add a New Agent
1. Declare it in `intelligence.yaml#agents` (schema here) with `promptFile: backend/custom/agents/my_agent/prompt.md`.
2. Write the agent's instructions as prose in that `prompt.md` (call tools by id, end with `__finish`).
3. (Optional) a handler class for hooks/offline `fallback` — `@agent(id)` + `system_prompt`, never `execute()`.

### Add a New Workflow
1. Declare it in `intelligence.yaml#workflows`: `steps` with `agent:`/`tool:`, pipe data via
   `${steps.<id>.output.<key>}` / `${input.<x>}`, add `onError` where needed.

### Add a New Trigger Template
1. Declare it in `intelligence.yaml#triggers`: `type: SCHEDULE|WEBHOOK`, `workflow`, `configFields`.
   The platform fires it and renders the config UI.

**📖 See [CLAUDE.md](CLAUDE.md) Tasks 1–3 + `.claude/prompts/implement-{agent,workflow}.md` for full examples**

---

## 🚀 Host it

This is a normal Docker app — run it anywhere you can run a container + Postgres.

```bash
# Build + run locally (nginx → FastAPI on one container, + Postgres)
docker compose up --build
# → app on http://localhost:3200
```

**Required env vars** (set in `.env` — don't delete them):
- `DATABASE_URL` — Postgres connection
- `CLARITTY_PLATFORM_URL` + `CLARITTY_AUTH_TOKEN` — the Claritty LLM proxy
  (for real AI; without them, the SDK runs each agent's `fallback(ctx)` — a no-AI result)

To deploy, ship the same image to your host of choice (any container platform) and
point `DATABASE_URL` at your Postgres. The schema is managed by Alembic migrations
(`backend/alembic.ini`); the app runs `upgrade head` on startup.

---

## 🛠 Infrastructure files (yours)

You self-host, so `Dockerfile`, `docker-compose.yml`, and `frontend/nginx.conf`
are yours to change. Two things to keep working:
- `frontend/src/lib/api.ts` uses **relative** URLs (empty `VITE_API_URL`) so the
  frontend calls `/api/...` on its own origin.
- Test with `docker compose up --build` after editing infra.

---

## 🧪 Testing

```bash
# Manual API testing
curl http://localhost:8000/api/agents
curl -X POST http://localhost:8000/api/workflows/my-workflow/execute

# Startup validation
cd backend && python validate_startup.py

# Widget testing
curl http://localhost:8000/api/widget?size=small  # Should be < 200ms
curl http://localhost:8000/api/widget?size=large  # Should be < 500ms
```

---

## 💡 Best Practices

### Design Workflow
1. ✅ **Start with widgets** - Design small/large widgets first
2. ✅ **Think user schedule** - What do users want automated?
3. ✅ **Minimize examples** - Keep template clean
4. ✅ **Use Claude Code** - Leverage /superpowers:brainstorming

### Implementation Workflow
1. ✅ **One agent at a time** - Build, test, iterate
2. ✅ **Chain into workflows** - Compose agents
3. ✅ **Add trigger templates** - Let users configure
4. ✅ **Test locally** - `docker compose up --build`
5. ✅ **Host it** - ship the container anywhere (keep the required env vars)

---

## 🆘 Need Help?

**For Claude Code users:**
- Run `/superpowers:brainstorming` to design your app
- Run `/superpowers:systematic-debugging` for issues
- Check [CLAUDE.md](CLAUDE.md) for AI assistant guidance

**For developers:**
- Check [CLAUDE.md](CLAUDE.md) + [WIDGETS.md](WIDGETS.md)
- `docker compose up --build` to run it
- Email support@claritty.ai

---

## 🌟 What You Can Build

**Real examples:**
- **AI Task Manager** - Auto-prioritize tasks, suggest schedules
- **Email Assistant** - Triage inbox, draft responses
- **CRM Agent** - Lead scoring, follow-up automation
- **Report Generator** - Automated weekly/monthly reports
- **Content Pipeline** - Research → Write → Edit → Publish
- **Data Monitor** - Track metrics, alert on anomalies

**The limit is your imagination!**

---

## 📄 License

MIT License - See [LICENSE](LICENSE)

---

## 🚀 Get Started Now

```bash
git clone https://github.com/Clarittyai/agentic-app-seed.git
cd agentic-app-seed
docker-compose up -d
code .  # Open Claude Code and run /superpowers:brainstorming
```

**Build something amazing!** 🎉

---

**Questions?** Check [CLAUDE.md](CLAUDE.md) | [WIDGETS.md](WIDGETS.md) | [docs/archive/](docs/archive/)

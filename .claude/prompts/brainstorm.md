# Agentic App Brainstorming Prompt

**Use this with `/superpowers:brainstorming` in Claude Code**

---

## 🎯 Goal

Help you design a production-ready agentic app for Claritty Platform by answering key questions about:
- Problem you're solving
- AI agents needed
- User experience (widgets!)
- Automation schedules
- **Design identity** (so the app doesn't look like the template — see §7)

> **Before you build:** run `rm .claritty-seed-pristine` to activate the identity
> gate, and read **IDENTITY.md** (keep the platform contract; replace the template
> look). The gate (`npm run check:identity`, also a Claude Code Stop hook) will
> block "done" until the app has its own identity.

---

## 🧭 Discovery method — run this FIRST (it's how Claritty itself works)

Claritty's own builder never jumps straight to features. It runs a short, specific
discovery: **problem → two ideal outcomes → a few focused follow-ups → a brief.**
Use the SAME method here before you design or write anything. It takes ~2 minutes
and makes the rest of the build obvious.

> **Parity (hybrid):** if the developer is signed in to the CLI, get the *real*
> platform output instead of improvising — run
> `claritty discover outcomes "<their problem>"` and
> `claritty discover questions "<their problem>"`. Each prints JSON
> (`{ "outcomes": [...] }` / `{ "questions": [...] }`). If it prints
> `{"unauthenticated":true}` (or errors), fall back to generating them yourself
> with the rules below — the method is identical either way.

### Step 1 — Restate the problem (one line)
Reflect the user's problem back in a single sentence so you're aligned before
proposing anything.

### Step 2 — Propose TWO ideal outcomes (the user picks/edits)
Offer **exactly two distinct** end-states a great app could deliver — don't ask
"what features?", show where this could land:
- **Distinct in approach:** one **proactive** ("it handles it for me" — the app
  acts on a schedule/automatically), one **on-demand** ("it helps me when I act" —
  the app assists in the moment). Not two rewordings of the same idea.
- **Concrete + value-framed:** ≤6-word title + 1–2 sentences naming the result the
  user gets and the key thing that delivers it. Written in their voice ("I…").
- **Self-contained:** realistic for a Claritty widget app (its own data + built-in
  Claude + schedule/manual triggers; **no external-account connections** unless a
  catalog integration covers it — see §6).

Present both (in Claude Code, as AskUserQuestion options) and let the user pick one
or write their own. This chosen outcome is the app's north star.

### Step 3 — Ask 3–5 focused follow-ups (concrete options, plain language)
Tailor each question to *their* idea, give 3–5 concrete options, and **always**
include a final "Let me specify…" option. Never use the words *trigger / workflow /
agent / endpoint* — translate them. Across your questions you MUST cover at least:
- **Widget glance** (the primary surface): *"When you glance at this on your
  dashboard, what's the ONE thing you need to see?"* — options should imply the
  widget's shape (a single number, a short ranked **list**, a **status** indicator,
  or a small **chart**) AND the one tap-action.
- **Automation** (cadence **and** autonomy): when should it act, and how
  independently — **autonomous** (acts on its own), **suggestive** (proposes, you
  one-tap approve), or **observational** (just reports, you act)?
- **Data** (where the app's data comes from): its own captured data, or an outside
  source? If they name Gmail/Slack/LinkedIn/etc., check the catalog (§6) — deliver
  the value WITHOUT a "connect your account" step when it isn't a catalog integration.

### Step 4 — Write the brief
Synthesize problem + chosen outcome + the answers into the plan: agents/workflow/
trigger, the widget per size, the data model, and the design identity (§7). Save it
to **`docs/plans/0001-brief.md`** and put the one-sentence success line into
`app-config.json` → `clarity_marketplace.core_action.definition_of_done` (§6c). Only
then start building.

**Parity invariants** (what these questions must respect — mirrors the platform):
widget sizes are exactly **170×170 / 360×170 / 360×360**; trigger kinds are
**schedule / webhook / event / manual**; autonomy is **autonomous / suggestive /
observational**; the app is **self-contained** (no OAuth/credentials except catalog
integrations the platform manages). These are fixed — see WIDGETS.md / INTEGRATIONS.md.

The sections below are the detailed reference your Step 3 questions and Step 4 brief
draw from.

---

## 📋 Questions to Answer

### 1. Problem & Users

**What problem does your app solve?**
- Who experiences this problem?
- How do they currently solve it (manually)?
- Why is manual work painful/time-consuming?

**Example**: "Sales teams spend 2 hours/day manually prioritizing leads from multiple sources"

---

### 2. Agentic Automation

**What tasks should AI agents handle automatically?**

Think about:
- Data collection (fetching, aggregating)
- Analysis (prioritization, classification, insights)
- Content generation (emails, reports, summaries)
- Actions (sending notifications, updating records)

**Example**:
- Agent 1: Fetch leads from CRM API
- Agent 2: Score leads using Claude (urgency, fit, intent)
- Agent 3: Generate personalized email drafts

---

### 3. User Schedule (Triggers)

**When/how often should your app run?**

Consider:
- Daily at specific time? (e.g., "9am every weekday")
- Interval-based? (e.g., "every 2 hours")
- Event-triggered? (e.g., "when new lead arrives via webhook")
- Data threshold? (e.g., "when pending count > 50")

**Key**: Users configure their own schedules! You define the template, they set their time/frequency.

**Example**:
- Template: "Daily Lead Review"
- User A: 9am EST, Mon-Fri
- User B: 6pm PST, Every day

---

### 4. Widget Interface (PRIMARY UX!)

**What should users see at a glance in their dashboard?**

Remember:
- Widgets are the PRIMARY interface (users see them 90% of the time)
- There are EXACTLY 3 Apple-HIG sizes (these only): Small 170×170, Medium 360×170, Large 360×360
- Design for glanceability - they should understand status in < 1 second
- Widgets are window-size invariant: fixed px, never responsive to the viewport

**Small Widget (170×170px)** — single quick metric:
- The one most important number
- An optional status chip + one action button

**Medium Widget (360×170px)** — a compact row / short list:
- A headline metric + 2-3 list rows (or a calendar/forecast strip)
- One or two quick actions

**Large Widget (360×360px)** — a rich multi-row view:
- Headline metric(s) + a fuller list (5-6 rows) that fills the height
- Quick actions; surface "+N more" rather than scrolling

**Example for Lead Scoring App**:
- Small: "47 New Leads" + "Score Now" button
- Medium: "47 New" + top 2-3 leads + "View All"
- Large: Hot (12) / Warm (24) / Cold (11) + top 5 leads + "View All"

---

### 5. Data & Multi-Tenancy

**What data will your app store?**

Every app gets:
- PostgreSQL database (DATABASE_URL)
- Per-user isolation (filter every user-data query by the X-User-ID caller)

Think about:
- What entities? (e.g., Leads, Tasks, Reports)
- What fields? (e.g., title, status, priority, score)
- Relationships? (e.g., Lead → ContactHistory)

**CRITICAL**: Every user-data model has a `user_id` column and EVERY query filters by it!

```python
# ✅ CORRECT — caller comes from the X-User-ID header (see routes/app.py)
leads = db.query(Lead).filter(Lead.user_id == user_id).all()

# ❌ WRONG - returns data across all tenants!
leads = db.query(Lead).all()
```

---

### 6. External data & actions (don't skip this!)

**Does this app read from or act on an outside system?** read→Gmail/Slack/LinkedIn feed,
post→LinkedIn/X, send→email, charge→Stripe, sync→Notion, CRM→HubSpot/Salesforce, message→Slack…

**Check the catalog FIRST.** Claritty ships ~33 **built-in integrations** (`catalog/INDEX.md`) —
Gmail, Slack, LinkedIn, X, HubSpot, Salesforce, Stripe, Notion, GitHub, Linear, and more. For each
service the app touches, grep `catalog/INDEX.md`:

- **In the catalog → use it.** It's a real, platform-managed integration: **the platform handles
  OAuth/credentials per user — you need NO API keys and write NO OAuth code.** Declare it in
  `intelligence.yaml#integrations`, put its tools in the agent's `tools:`, and call them via the
  agent's `system_prompt` or `ctx.integration("<id>")` (see INTEGRATIONS.md). Test locally with
  `CLARITTY_FAKE_CREDS_<ID>='{"access_token":"…"}'` — that exercises the REAL path, it is not a mock.
  Do **NOT** ask the user for keys and do **NOT** build a mock data layer for a catalog service.
- **Not in the catalog** (e.g. reddit, g2, hn) → write a custom read-only `@tool`, or seed
  **clearly-labeled** sample data — and say which. Never pretend a mock is the real source.
- When a catalog service isn't connected yet, show a **connect prompt (409)** — never a
  faked/simulated success.
- **Which service?** If the user didn't name one, **infer the obvious one and confirm it** (Idea:
  "auto-post marketing" → LinkedIn, confirm). **Self-contained?** If it truly touches no external
  system (like the Tasks example), say so explicitly.

AI itself is NOT an integration — it's built in via the Claritty LLM proxy (no API key).

### 6b. Approval gate

**Should the AI act on its own, or should the user approve first?** If a human should sign off
(publishing, sending, charging), plan a **draft → approve → act** lifecycle (status field + an
approve action in the UI/widget). If it's safe to act automatically, note that instead.

### 6c. Definition of done

**Write one concrete sentence describing end-to-end success for THIS app.** e.g. "A daily run
produces 2 post drafts; approving one publishes it to LinkedIn (or prompts to connect if not yet connected) and the widget shows it."
This becomes `app-config.json` → `core_action.definition_of_done` and the bar for "done."

---

### 7. Design Identity (MAKE IT YOURS — don't ship the template look!)

This repo is a TEMPLATE. If you skip this, the app ships looking exactly like the
seed (indigo palette, template landing page, Claritty logo) and the **identity
gate will block the build**. Decide the app's *own* identity now:

**What is this app's visual personality?**
- **Palette**: pick a primary/accent color + a heading color that fit the app's
  purpose (calm finance ≠ playful kids ≠ earthy travel). You'll set these as
  `--brand-accent`, `--brand-accent-600`, `--brand-primary` in `frontend/src/theme.css`.
  Pick an accent **dark enough that WHITE text on it clears WCAG-AA (~4.5:1)** — a
  light accent fails the rendered contrast gate on the primary button. Use the
  accent for **fills / large headings, never body or nav text** (a single accent
  rarely clears AA as text in BOTH light and dark themes).
- **Typography**: a font that matches the voice (e.g. `Sora`, `Inter`, `Space Grotesk`).
  Set `--brand-font` and load it in `index.html`.
- **Voice/tone**: how copy reads (terse & pro? warm & encouraging?).
- **Landing page**: what the app's real home screen shows (NOT the template
  showcase) — replace `frontend/src/pages/Dashboard.tsx`.
- **App mark + name**: your own logo/wordmark (replace `/claritty-logo.png` in
  `Layout.tsx`) and `appName`/`appDescription` in `lib/app-meta.ts`.

**Keep** the CSS token *names* and the platform contract — change values, not the
system. Full manifest + checklist: **IDENTITY.md**.

**Example for a Lead Scoring App**: deep emerald accent (`152 60% 38%`), near-black
headings, `Space Grotesk`; landing = "Today's pipeline" board; mark = a bolt glyph.

---

## 🎨 Design Output

After brainstorming, you should have:

### Design Identity
- Palette: accent `H S% L%`, accent-600 `…`, primary `…`  (→ `frontend/src/theme.css`)
- Font: `[name]`  (→ `--brand-font` + `index.html`)
- Landing page concept: [what the real Dashboard shows]
- App name + mark: [name] + [logo idea]  (→ `app-meta.ts`, `Layout.tsx`)



### Agents (1-3 recommended)
- **Agent 1**: [Name] - [What it does]
- **Agent 2**: [Name] - [What it does]
- **Agent 3**: [Name] - [What it does]

### Workflows (1-2 recommended)
- **Workflow 1**: [Name] - Chains Agent 1 → Agent 2 → Agent 3
- **Workflow 2**: [Name] - Runs Agent X in parallel with Agent Y

### Triggers (1-3 recommended)
- **Trigger 1**: [Type] - Runs Workflow 1 at [user-configured time]
- **Trigger 2**: [Type] - Runs Workflow 2 every [user-configured interval]

### Widgets
- **Small Widget**: Shows [single metric] + [action button]
- **Large Widget**: Shows [2-4 metrics] + [recent activity] + [actions]

### Database Entities
- **Entity 1**: [Name] - Fields: [list]
- **Entity 2**: [Name] - Fields: [list]

### External data & actions
- **Sources/actions**: for each outside service, mark it `catalog integration <id>` (in
  catalog/INDEX.md → declare + use its tools, platform OAuth, no keys), `custom tool` (no catalog
  match), or `honest seed` (clearly-labeled samples). e.g. "LinkedIn → catalog `linkedin`; Reddit →
  custom tool", or "none — self-contained".
- **Connect**: [catalog tool / ctx.integration + 409 connect-prompt when not connected; CLARITTY_FAKE_CREDS locally — see INTEGRATIONS.md]

### Approval gate
- [Yes — draft → approve → act, with an approve action] / [No — acts automatically]

### Definition of done
- [one concrete end-to-end success sentence → app-config.json core_action.definition_of_done]

---

## ✅ Validation Checklist

Before implementing, verify:

- [ ] Problem is clear and specific
- [ ] Agents have well-defined single responsibilities
- [ ] Workflows chain agents logically
- [ ] Triggers allow user customization (time, frequency, filters)
- [ ] External action identified + a Connect flow planned (or confirmed self-contained)
- [ ] Approval gate decided (draft→approve→act, or auto)
- [ ] Definition of done written (the end-to-end success sentence)
- [ ] Small widget shows ONE key metric (glanceable)
- [ ] Large widget shows 2-4 metrics + activity
- [ ] Database entities have a `user_id` field (filtered on every query)
- [ ] External API keys identified and added to .env.example

---

## 🚀 Next Steps

After brainstorming:

1. **Create implementation plan** with Claude Code
2. **Start with agents** - Implement one agent at a time
3. **Chain into workflows** - Test agent composition
4. **Add trigger templates** - Let users configure schedules
5. **Design widgets** - Make them beautiful and fast (< 200ms small, < 500ms large)
6. **Test locally** - docker-compose up, test all endpoints
7. **Deploy to Claritty** - Submit GitHub URL to platform

---

## 💡 Example: Lead Scoring App

**Problem**: Sales teams waste time manually reviewing 100+ leads/day from multiple sources

**Agents**:
1. **Lead Fetcher** - Fetches leads from CRM API (HubSpot, Salesforce)
2. **Lead Scorer** - Uses Claude to score leads (urgency, fit, intent)
3. **Email Composer** - Generates personalized outreach emails

**Workflow**:
- **Daily Lead Review** - Fetches leads → Scores them → Generates emails → Sends summary

**Triggers**:
1. **Daily Review** - User configures time (e.g., 9am EST)
2. **New Lead Alert** - Webhook triggers when lead score > 90

**Widgets**:
- **Small**: "47 New Leads Today" + "Review Now" button
- **Large**: Hot (12), Warm (24), Cold (11) + Top 3 leads with scores + "View All"

**Database**:
- **Lead**: id, user_id, name, email, score, status, created_at
- **EmailDraft**: id, user_id, lead_id, subject, body, sent_at

**Integrations** (catalog-first — declare in intelligence.yaml, platform handles OAuth, no keys):
- Claude (scoring) — built in via the Claritty LLM proxy, not an integration
- `hubspot` (fetching leads) — catalog integration; use `hubspot.search_contacts`
- `gmail` (sending outreach) — catalog integration; use `gmail.send`
  (a service NOT in catalog/INDEX.md → custom read-only tool or a clearly-labeled seed)

---

**Ready to build?** Run `/superpowers:brainstorming` in Claude Code and let's design your app! 🚀

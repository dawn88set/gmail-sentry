# 🚀 Clarity Agentic App Template

**Build AI-powered applications that work for users on their schedule**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](https://www.docker.com/)

---

## 🌟 What is Clarity Platform?

**Clarity** is an AI-native platform that brings intelligent automation to everyone through a unified dashboard. Instead of juggling dozens of disconnected AI tools, users discover, install, and use **agentic applications** that work together seamlessly.

### The Vision

Imagine your workday where AI handles routine tasks automatically:
- Your email inbox is triaged every morning at 8 AM
- Task priorities are analyzed before your standup at 9 AM
- Reports are generated and sent every Friday at 4 PM
- Customer inquiries get drafted responses within minutes

**The key**: You control when these things happen. You set the schedule. The AI agents work on your terms.

This is **Clarity** - a marketplace of intelligent applications that automate your work, your way.

---

## 🤖 What Are Agentic Apps?

**Agentic apps** are fundamentally different from traditional applications:

### Traditional Apps
```
You open the app → Perform the task manually → Close the app
Repeat daily...
```

### Agentic Apps
```
You configure once → AI agents work automatically → You review results
Automation runs on your schedule without manual intervention
```

### The Three Components

Every agentic app has:

**1. Agents** - AI-powered workers that perform specific tasks
- Analyze tasks and estimate time
- Draft emails and responses
- Generate reports and summaries
- Process data and extract insights

**2. Workflows** - Chains of agents working together
- Sequential: One agent after another
- Parallel: Multiple agents working simultaneously
- Complex: Conditional logic and decision trees

**3. Triggers** - User-controlled schedules
- "Run every weekday at 9 AM"
- "Check every 2 hours between 8 AM - 6 PM"
- "Execute every Friday at 4 PM"
- Users choose their own times and frequencies

---

## 🎨 The Widget-First Revolution

**⚠️ CRITICAL CONCEPT FOR DEVELOPERS**: Agentic apps on Clarity are **NOT** traditional web applications. They are **widget-first** applications.

### Why This Changes Everything

**Traditional Apps**:
- User opens app in browser or mobile
- Performs tasks manually
- Closes app when done
- Must remember to check back later

**Agentic Apps on Clarity**:
- **Widgets are ALWAYS visible** on user's dashboard
- Agents work automatically in the background
- Widgets show results and require user attention
- **Users interact primarily through widgets, not full pages**

### The Widget-First Model Explained

Think of it this way:

```
┌─────────────────────────────────────────────────────┐
│                 User's Dashboard                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │  Email   │  │  Tasks   │  │  CRM     │          │
│  │Assistant │  │ Manager  │  │Assistant │          │
│  │          │  │          │  │          │          │
│  │ 3 urgent │  │ 5 due    │  │ 2 hot    │  ← Always visible
│  │ 95% done │  │ today    │  │ leads    │  ← Real-time updates
│  └──────────┘  └──────────┘  └──────────┘  ← Primary interface
│                                                       │
│  [Click widget → Opens full app for details]         │
└─────────────────────────────────────────────────────┘
```

### ⚠️ CRITICAL: Two Widget Sizes ONLY

**NO medium size exists!** The platform supports exactly TWO widget sizes (Apple standards):

#### Small Widget (170×170px - 1:1 SQUARE) - The "At a Glance" View

**Purpose**: Quick status check, always-on monitoring
**What to show**: Essential metrics only
**User behavior**: Scans their grid of 10-20 widgets in seconds

```
┌─────────────────────┐
│  Email Assistant    │
│  ──────────────────  │
│  ✉️  3 important     │
│  🚨 1 urgent         │
│  ✅ 95% handled      │
└─────────────────────┘
```

**Design principle**: Answer "Is everything okay?" in 2 seconds

#### Large Widget (360×170px - 2.1:1 WIDE RECTANGLE) - The "Interactive Dashboard"

**Purpose**: Detailed monitoring and immediate action
**What to show**: Recent activity, trends, quick actions
**User behavior**: Actively manages and interacts with the app

```
┌──────────────────────────────────────────────────┐
│  Email Assistant                                  │
│  ──────────────────────────────────────────────── │
│                                                   │
│  📊 Last 24 Hours:                                │
│    • 47 emails processed                          │
│    • 3 marked important (↓ 2 from yesterday)      │
│    • 1 requires immediate attention               │
│                                                   │
│  🔥 Urgent - Requires Your Attention:             │
│  ┌────────────────────────────────────────────┐  │
│  │ "RE: Q1 Budget Review" - CFO (2m ago)      │  │
│  │ → AI Draft Ready: "Thank you for..."       │  │
│  │ [✓ Send]  [✎ Edit]  [⊗ Dismiss]           │  │
│  └────────────────────────────────────────────┘  │
│                                                   │
│  📈 This Week: 327 emails, 98% handled            │
│                                                   │
│  [View All Emails]  [Adjust Settings]             │
└──────────────────────────────────────────────────┘
```

**Design principle**: Enable action without opening full app

**📖 Complete Widget Design Guide**: See [Widget Design Guide](docs/WIDGET_DESIGN_GUIDE.md) for comprehensive specifications, layout patterns, and AI code generator instructions.

### When Users Access the Full App

Full app pages exist for:
- **Initial setup**: Connecting integrations, configuring triggers
- **Deep dives**: Viewing complete history, advanced analytics
- **Complex tasks**: Detailed configuration, bulk operations

**But 90% of daily interaction happens through widgets.**

### Why This Matters for You as a Developer

**Traditional mindset** ❌:
- Design full web app first
- Add widgets as an afterthought
- Widgets just show basic stats

**Agentic app mindset** ✅:
- Design widgets FIRST
- Widgets are the primary interface
- Full app is for advanced/setup tasks only

**Your success metric**: Can users accomplish their daily tasks without ever opening your full app?

---

## 👥 How Users Experience These Apps

### Discovery & Installation
1. **Browse the Clarity Marketplace** - Discover apps built by developers
2. **View live widget previews** - See real functionality before installing
3. **Install with one click** - Widget appears on their dashboard instantly

### Daily Workflow

**Morning - 8:00 AM**:
Sarah glances at her dashboard while drinking coffee. She sees:
- Email widget: 3 important, 1 urgent (red indicator)
- Task widget: 5 tasks due today, all prioritized
- CRM widget: 2 hot leads need follow-up

**Takes action without opening anything**:
- Clicks "Send" on AI-drafted urgent email directly from widget
- Checks task priorities in task widget
- All done in 30 seconds

**Only opens full app when**:
- Needs to adjust email filtering rules (setup)
- Wants to see complete email history (deep dive)
- Configures new trigger schedule (advanced)

### Configuration & Triggers

Users control WHEN and HOW apps work:

**Setting up triggers through widget**:
1. Click "⚙️ Settings" button on widget
2. Choose "Add Trigger"
3. Select template: "Check my email every 2 hours"
4. Configure: Time range (8 AM - 6 PM), timezone (PST)
5. Done! Widget shows "Active: 1 trigger"

**The magic**: Everything configurable from widget interface

### The Result

**One unified dashboard** where users:
- ✅ See all their automations at a glance (widgets grid)
- ✅ Monitor real-time status without clicking
- ✅ Take immediate action on urgent items
- ✅ Never context switch between 10 different tools
- ✅ Control when everything runs (trigger configuration)

**Users love it because**: They never have to remember to check anything. The widgets are always there, always updated.

---

## 🎯 The Goal of Agentic Apps

### For End Users

**Transform work from reactive to proactive:**
- ❌ Checking email constantly → ✅ AI triages and surfaces important items
- ❌ Manual task prioritization → ✅ AI analyzes and recommends priorities
- ❌ Remembering to send reports → ✅ Automated generation and delivery
- ❌ 10 separate tools and logins → ✅ One unified dashboard

**The promise**: Automation that respects your time and preferences.

### For Organizations

- **Consistency**: Every team member has AI-powered assistance
- **Efficiency**: Routine tasks handled automatically
- **Scalability**: Add more apps as needs grow
- **Control**: Central management and governance

### For Developers (That's You!)

Build applications that:
- **Reach users instantly** through the Clarity Marketplace
- **Integrate seamlessly** with the Clarity ecosystem
- **Scale automatically** with platform infrastructure
- **Generate revenue** through the marketplace

---

## 🛠️ About This Template

This template helps you **build agentic apps for Clarity Platform**. It provides everything you need:

### What You Get

- 🤖 **SDK for defining AI agents** - Simple decorator-based API
- 🔄 **Workflow orchestration** - Chain agents in any pattern
- ⏰ **User-configurable triggers** - Let users set their own schedules
- 🎨 **Widget components** - Pre-built UI for dashboard integration
- 🔒 **Security & multi-tenancy** - Built-in user isolation
- 🚀 **Auto-discovery** - No manual registration needed
- 📦 **One-command deployment** - Start coding immediately

### The Key Innovation

**You define templates, users create instances:**

```python
# You write this once:
@trigger_template(
    id="daily-review",
    name="Daily Task Review",
    config_fields=[
        {"key": "time", "label": "What time?", "type": "time"},
        {"key": "timezone", "label": "Your timezone", "type": "timezone"}
    ]
)
class DailyReview:
    pass

# Sarah (New York) creates: 9:00 AM EST
# John (San Francisco) creates: 6:00 PM PST
# Maria (London) creates: 7:30 AM GMT

# System schedules all three automatically!
```

**Same app, personalized for every user.**

---

## ⚡ Quick Start for Developers

### One-Command Setup

```bash
git clone https://github.com/Clarittyai/agentic-app-seed.git
cd agentic-app-seed
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env
./start.sh  # Mac/Linux or start.bat for Windows
```

**That's it!** 🎉
- 📖 Frontend: http://localhost:3200
- 🔧 Backend API: http://localhost:8000
- 📚 API Docs: http://localhost:8000/docs

### Build Your First Agent (3 Steps)

#### 1. Create Agent File

`backend/agents/task_analyzer.py`:

```python
from claritty_sdk import agent, BaseAgent, AgentResult, AgentContext

@agent(
    id="task-analyzer",
    name="Task Analyzer",
    description="Analyzes tasks and provides insights"
)
class TaskAnalyzer(BaseAgent):
    async def execute(self, context: AgentContext) -> AgentResult:
        task = context.get_input("task_description")

        # Use Claude AI to analyze
        analysis = await self.analyze_with_ai(task)

        return AgentResult(
            success=True,
            data={
                "priority": analysis.priority,
                "estimated_hours": analysis.time_estimate,
                "insights": analysis.recommendations
            }
        )
```

#### 2. That's It!

**No registration needed.** The auto-discovery system finds your agent automatically.

#### 3. Test It

```bash
curl -X POST http://localhost:8000/api/agents/task-analyzer/execute \
  -H "Authorization: Bearer test-user" \
  -d '{"task_description": "Prepare Q1 budget review"}'

# Response:
# {
#   "success": true,
#   "data": {
#     "priority": "high",
#     "estimated_hours": 3.5,
#     "insights": "Strategic task requiring executive attention..."
#   }
# }
```

---

## 📖 Complete Documentation

### 🚀 Getting Started (Essential Reading)

- **[Developer Guide](DEVELOPER_GUIDE.md)** - Complete technical reference for building agentic apps
  - Quick start (60 seconds)
  - Building agents step-by-step
  - Creating workflows
  - Widget endpoint implementation
  - Database patterns
  - Testing & deployment

- **[Customization Guide](CUSTOMIZATION_GUIDE.md)** - Step-by-step guide to customize this template
  - Planning your app
  - Replacing example agents
  - Real-world example (RedditSignals)
  - Common patterns

- **[Requirements Checklist](REQUIREMENTS.md)** - Platform requirements for deployment
  - Critical requirements (blockers)
  - Recommended practices
  - Validation checklist
  - Common failures & fixes

### 🔧 Tools & Validation

- **[Validation Script](scripts/validate-app.py)** - Automated requirement checking
  ```bash
  python scripts/validate-app.py
  # Validates health endpoint, widget, agents, workflows, Docker
  ```

- **[FAQ & Troubleshooting](FAQ.md)** - Common questions and solutions
  - Getting started issues
  - Agent/workflow problems
  - Database errors
  - Docker troubleshooting
  - Real developer experiences

### 📚 Advanced Topics
- **[Understanding Clarity Platform](docs/CLARITY_PLATFORM.md)** - Complete ecosystem guide
- **[Architecture Guide](docs/ARCHITECTURE.md)** - Technical deep dive
- **[API Reference](docs/API.md)** - Complete endpoint documentation

### 🚢 Deployment
- **[Submission Requirements](docs/SUBMISSION_REQUIREMENTS.md)** - How to submit your app
- **[GitHub CI Workflows](.github/workflows/)** - Automated validation on push

---

## 🎨 Building for the Widget-First Model

### The Golden Rule for Developers

**❌ WRONG**: Build a full web app, then add widgets as an afterthought
**✅ RIGHT**: Design widgets FIRST, build full app for edge cases only

### Implementation Requirements

#### 1. Widget Component (Frontend)

**Location**: `frontend/src/components/Widget.tsx`

```typescript
interface WidgetProps {
  size?: 'small' | 'large';  // Only 2 sizes, no 'medium'
  userId: string;
}

export default function Widget({ size = 'large', userId }: WidgetProps) {
  const { data } = useQuery(['widget', size, userId], () =>
    api.getWidgetData(size)
  );

  if (size === 'small') {
    return (
      <div className="widget-small">
        <h3>{data.appName}</h3>
        <div className="metrics">
          <span>Active: {data.activeTriggers}</span>
          <span>Success: {data.successRate}%</span>
        </div>
      </div>
    );
  }

  // Large widget with interactive elements
  return (
    <div className="widget-large">
      <h3>{data.appName}</h3>

      {/* Recent activity */}
      <div className="recent-activity">
        {data.recentExecutions.map(exec => (
          <ExecutionItem key={exec.id} {...exec} />
        ))}
      </div>

      {/* Quick actions - enable interaction without full app */}
      <div className="quick-actions">
        <button onClick={() => handleAction('trigger')}>
          Add Trigger
        </button>
        <button onClick={() => handleAction('settings')}>
          Settings
        </button>
      </div>
    </div>
  );
}
```

#### 2. Widget API Endpoint (Backend)

**Location**: `backend/main.py`

```python
@app.get("/api/widget")
async def get_widget_data(
    size: str = "large",  # 'small' or 'large' only
    user_id: str = Depends(get_current_user)
):
    """
    Widget data endpoint - optimized for fast response
    This is called EVERY TIME user's dashboard loads (frequently!)
    """

    if size == "small":
        # Minimal data for quick glance
        return {
            "active_triggers": db.query(UserTriggerInstance)
                .filter_by(user_id=user_id, enabled=True)
                .count(),
            "success_rate": calculate_success_rate(user_id),
            "status": "healthy"  # or "attention_needed"
        }

    # Large widget - detailed but still fast
    return {
        "active_triggers": get_trigger_count(user_id),
        "total_executions": get_execution_count(user_id),
        "success_rate": calculate_success_rate(user_id),
        "recent_executions": get_recent_executions(user_id, limit=5),
        "alerts": get_urgent_alerts(user_id),  # Important!
        "quick_stats": {
            "today": get_today_stats(user_id),
            "this_week": get_week_stats(user_id)
        }
    }
```

#### 3. Authentication via X-User-ID Header

**CRITICAL**: Widgets load via iframe in Clarity dashboard. The platform injects user identity:

```typescript
// frontend/src/lib/api.ts
api.interceptors.request.use((config) => {
  // Priority 1: X-User-ID from Clarity platform (production)
  const userId = localStorage.getItem('user_id');
  if (userId) {
    config.headers['X-User-ID'] = userId;
  }

  // Priority 2: Bearer token (development fallback)
  const token = localStorage.getItem('auth_token') || 'test-user';
  config.headers.Authorization = `Bearer ${token}`;

  return config;
});
```

### Widget Design Principles

#### Small Widget Design

**Goal**: Answer "Is everything okay?" in 2 seconds

```
DO show:
✅ Number of active automations
✅ Overall health status (green/yellow/red)
✅ One critical metric (success rate, items pending, etc.)

DON'T show:
❌ Detailed logs
❌ Configuration options
❌ Long lists of items
```

#### Large Widget Design

**Goal**: Enable daily tasks without opening full app

```
DO show:
✅ Last 5 executions with status
✅ Quick action buttons (Add Trigger, Settings)
✅ Important alerts that need attention
✅ This week's summary stats
✅ Interactive elements (buttons, forms)

DON'T show:
❌ Complete history (that's for full app)
❌ Complex configuration (link to full app)
❌ Detailed analytics (link to full app)
```

### Performance Requirements

Widgets load **every time** a user opens their dashboard:

- **Small widget**: < 200ms response time
- **Large widget**: < 500ms response time
- **Real-time updates**: Use WebSocket or polling for status changes
- **Error handling**: Never show error to user, show "Unable to load" state

### Required Screenshots

**MUST include** in `./screenshots/` directory:

```
screenshots/
├── widget-small.png    # Small widget with real data
├── widget-large.png    # Large widget with real data
└── full-app.png        # (Optional) Full app screenshot
```

Configure in `app-config.json`:
```json
{
  "screenshots": [
    {
      "url": "./screenshots/widget-small.png",
      "type": "widget-small",
      "required": true
    },
    {
      "url": "./screenshots/widget-large.png",
      "type": "widget-large",
      "required": true
    }
  ]
}
```

### Testing Your Widgets

```bash
# Test widget endpoint performance
time curl http://localhost:8000/api/widget?size=small

# Should respond in < 200ms

# Test with different user IDs
curl http://localhost:8000/api/widget?size=large \
  -H "X-User-ID: user-123"

# Test real-time updates
# Open dashboard in browser, trigger workflow, see widget update
```

### Common Widget Mistakes to Avoid

❌ **Showing too much data in small widget**
- Small widget should have 2-3 metrics MAX

❌ **No interactive elements in large widget**
- Users should be able to take action directly

❌ **Slow API responses**
- Optimize queries, use caching, return minimal data

❌ **Designing for full app first**
- Always design widgets before full app pages

❌ **Forgetting real-time updates**
- Widgets should update when triggers fire

**[📖 Complete Widget Design Guide →](docs/WIDGET_DESIGN_GUIDE.md)** - Essential reading for building great widgets

---

## 🚀 What You Can Build

Real applications developers have built with this template:

### Productivity Apps
- **AI Task Manager** - Automatically prioritize and schedule tasks
- **Email Assistant** - Triage inbox and draft responses
- **Meeting Summarizer** - Generate summaries and action items

### Business Apps
- **CRM Assistant** - Lead scoring and follow-up automation
- **Customer Support AI** - Ticket analysis and response drafting
- **Report Generator** - Automated weekly/monthly reports

### Content & Marketing
- **Content Pipeline** - Research, write, edit, publish flow
- **Social Media Manager** - Scheduled posting and engagement tracking
- **SEO Analyzer** - Content optimization and keyword research

### Data & Analytics
- **Analytics Dashboard** - Automated data analysis and insights
- **Alert Monitor** - Track metrics and notify on anomalies
- **Data Pipeline** - ETL and transformation workflows

**[See more examples →](docs/GUIDE.md#example-applications)**

---

## 💡 Why Build on Clarity?

### For Developers

**Before Clarity:**
- Build full auth system ❌
- Set up hosting infrastructure ❌
- Handle scaling and monitoring ❌
- Market and acquire users ❌
- No clear monetization path ❌

**With Clarity:**
- Auth handled by platform ✅
- Infrastructure provided ✅
- Auto-scaling included ✅
- Instant access to users ✅
- Built-in marketplace revenue ✅

**Focus on what matters**: Building great AI agents and workflows.

### For Users

**Before Clarity:**
- 10 different AI tools ❌
- 10 different logins ❌
- No integration between tools ❌
- Constant context switching ❌
- Manual scheduling for everything ❌

**With Clarity:**
- One unified dashboard ✅
- Single sign-on ✅
- Apps work together ✅
- Stay in one place ✅
- Set your schedule once ✅

**The promise**: Powerful automation that's actually easy to use.

---

## 🏗️ Architecture Overview

### Clean Template Structure

```
clarity-agentic-app-seed/
├── backend/              # FastAPI server (your business logic)
│   ├── agents/           # Your AI agents
│   ├── workflows/        # Your workflow definitions
│   ├── triggers/         # Your trigger templates
│   └── infrastructure/   # Auto-discovery (don't touch)
├── frontend/             # React UI with widgets
├── requirements.txt      # Includes claritty-sdk from PyPI
└── docker-compose.yml    # One-command startup
```

**No SDK bloat!** The Clarity SDK is installed from PyPI as a dependency:
```bash
pip install claritty-sdk  # Installed automatically
```

### Technology Stack

- **Clarity SDK**: `pip install claritty-sdk` - Decorator-based framework
- **AI**: Anthropic Claude + LangChain
- **Backend**: Python, FastAPI, PostgreSQL
- **Frontend**: React, TypeScript, Tailwind CSS
- **Deployment**: Docker containers on Clarity infrastructure

**[Full architecture documentation →](docs/ARCHITECTURE.md)**

---

## ⚠️ Infrastructure Files - Do Not Modify

**IMPORTANT**: Certain infrastructure files are managed by the Clarity Platform and should **NOT be modified** unless you fully understand the implications.

### 🚨 Critical Files (Do Not Touch)
- `docker-compose.yml` - Port configuration managed by platform
- `frontend/Dockerfile` - Build configuration with VITE_API_URL settings
- `frontend/nginx.conf` - The `/api/` location block is REQUIRED
- `frontend/src/lib/api.ts` - API_BASE_URL must use empty string default

### Why?
The Clarity Platform uses **dynamic port allocation** and **Nginx reverse proxying** for multi-tenancy. Your app's frontend makes API calls using **relative URLs** (like `/api/widget`) which are automatically proxied by Nginx to the backend service.

**Common mistake**: Hardcoding `http://localhost:8000` breaks production deployments!

```typescript
// ❌ WRONG - breaks in production
const API_BASE_URL = 'http://localhost:8000';

// ✅ CORRECT - works everywhere
const API_BASE_URL = import.meta.env.VITE_API_URL || '';
```

### Multi-Service Routing Architecture

```
Production URL: https://your-app.apps.claritty.ai/

Frontend (Nginx):
  /            → React SPA
  /widget      → Widget page
  /api/*       → Proxy to backend:8000 ← CRITICAL!

Backend (FastAPI):
  /health      → Health check
  /api/widget  → Widget data
  /api/*       → All API endpoints
```

**[📖 Complete Infrastructure Guide →](INFRASTRUCTURE.md)** - Essential reading before modifying any infrastructure files!

### What You CAN Modify
- ✅ Application logic (`backend/agents/`, `frontend/src/`)
- ✅ Dependencies (`requirements.txt`, `package.json`)
- ✅ Database models and migrations
- ✅ Custom environment variables
- ✅ Resource limits (memory, CPU)

---

## 📊 Key Features

### For Developers
- ✅ **Zero Configuration** - Auto-discovery, no setup
- ✅ **One Command Start** - `./start.sh` and you're coding
- ✅ **Type-Safe** - Full TypeScript and Pydantic validation
- ✅ **Hot Reload** - Changes reflect immediately
- ✅ **Comprehensive Examples** - Learn by example

### For End Users
- ✅ **Personalized Scheduling** - Set your own times
- ✅ **Widget Dashboard** - See everything at a glance
- ✅ **Execution History** - Track what happened when
- ✅ **Beautiful Interface** - Modern, intuitive design

---

## 🧪 Testing Your App

```bash
# Health check
curl http://localhost:8000/health

# List agents
curl http://localhost:8000/api/agents

# Execute workflow
curl -X POST http://localhost:8000/api/workflows/my-workflow/execute \
  -H "Authorization: Bearer test-user"

# Run validation
cd backend && python validate_startup.py
```

**[Complete testing guide →](docs/GUIDE.md#testing)**

---

## 🤝 Contributing

This is a **template repository**. Fork it and make it your own!

- Found a bug? Open an issue
- Have a suggestion? Submit a PR
- Need help? Check the docs or ask in discussions

---

## 📄 License

MIT License - See [LICENSE](LICENSE) file

---

## 🙏 Built With

- [Anthropic Claude](https://www.anthropic.com/) - AI reasoning and generation
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [React](https://react.dev/) - UI library
- [PostgreSQL](https://www.postgresql.org/) - Database
- [Docker](https://www.docker.com/) - Containerization

---

## 🌟 Join the Clarity Ecosystem

**Build apps that:**
- Help users reclaim their time
- Integrate AI into daily workflows
- Respect user autonomy and preferences
- Scale to serve thousands of users

**Start building today:**

```bash
git clone https://github.com/Clarittyai/agentic-app-seed.git
cd agentic-app-seed
./start.sh
```

**Welcome to the future of work automation.** 🚀

---

**Built with ❤️ by the Clarity team**

**[Get Started →](#-quick-start-for-developers)** | **[Read Full Guide →](docs/CLARITY_PLATFORM.md)** | **[View API Docs →](docs/API.md)**

# Quick Start Guide

**Get your agentic app running in 5 minutes**

---

## Prerequisites

- Node.js 18+ and Docker installed
- Anthropic API key ([get one here](https://console.anthropic.com))

---

## Step 1: Setup (2 minutes)

```bash
# Clone the template
git clone https://github.com/Clarittyai/agentic-app-seed.git my-app
cd my-app

# Configure environment
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# Start everything
./start.sh  # Mac/Linux
# or
start.bat  # Windows
```

**That's it!** Your app is running:
- 📖 Frontend: http://localhost:3200
- 🔧 Backend API: http://localhost:8000
- 📚 API Docs: http://localhost:8000/docs

---

## Step 2: Create Your First Agent (2 minutes)

Create `backend/agents/greeting_agent.py`:

```python
from claritty_sdk import agent, BaseAgent, AgentResult, AgentContext

@agent(
    id="greeting-agent",
    name="Greeting Agent",
    description="Generates personalized greetings",
    inputs={
        "name": {"type": "string", "required": True}
    },
    outputs={
        "greeting": {"type": "string"}
    }
)
class GreetingAgent(BaseAgent):
    async def execute(self, context: AgentContext) -> AgentResult:
        name = context.get_input("name")
        greeting = f"Hello, {name}! Welcome to your agentic app!"

        return AgentResult(
            success=True,
            data={"greeting": greeting}
        )
```

**No registration needed!** The auto-discovery system finds it automatically.

**Test it:**
```bash
# Restart backend
docker-compose restart backend

# Execute agent
curl -X POST http://localhost:8000/api/agents/greeting-agent/execute \
  -H "Authorization: Bearer test-user" \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice"}'

# Response:
# {
#   "success": true,
#   "data": {"greeting": "Hello, Alice! Welcome to your agentic app!"}
# }
```

---

## Step 3: Create a Workflow (1 minute)

Create `backend/workflows/greeting_workflow.py`:

```python
from claritty_sdk import workflow, uses_agent, ExecutionMode

@workflow(
    id="greeting-workflow",
    name="Greeting Workflow",
    description="Greets users warmly",
    execution_mode=ExecutionMode.SEQUENTIAL
)
@uses_agent("greeting-agent", output_key="greeting")
async def greeting_workflow(context):
    """Single-step workflow that greets users"""
    pass
```

**Test it:**
```bash
# Restart backend
docker-compose restart backend

# Execute workflow
curl -X POST http://localhost:8000/api/workflows/greeting-workflow/execute \
  -H "Authorization: Bearer test-user" \
  -H "Content-Type: application/json" \
  -d '{"name": "Bob"}'
```

---

## Step 4: Create a User-Configurable Trigger (Optional)

Create `backend/triggers/daily_greeting.py`:

```python
from claritty_sdk import trigger_template, TriggerTemplateType

@trigger_template(
    id="daily-greeting",
    name="Daily Greeting",
    description="Get a daily greeting at your preferred time",
    template_type=TriggerTemplateType.SCHEDULE_DAILY,
    workflow_id="greeting-workflow",
    config_fields=[
        {
            "key": "time",
            "label": "What time?",
            "type": "time",
            "required": True,
            "default": "09:00"
        },
        {
            "key": "timezone",
            "label": "Your timezone",
            "type": "timezone",
            "required": True,
            "default": "America/New_York"
        }
    ]
)
class DailyGreetingTrigger:
    pass
```

**Restart backend, then create a trigger instance:**
```bash
curl -X POST http://localhost:8000/api/my/triggers \
  -H "Authorization: Bearer test-user" \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": "daily-greeting",
    "name": "My Morning Greeting",
    "config": {
      "time": "09:00",
      "timezone": "America/New_York"
    }
  }'
```

Now the workflow runs automatically every day at 9 AM EST!

---

## Next Steps

### Build Your Widgets (Essential!)

Widgets are the primary interface for your app on Clarity Platform. Users interact with your app through widgets 90% of the time.

**📖 Read the Widget Design Guide:** [docs/WIDGET_DESIGN_GUIDE.md](WIDGET_DESIGN_GUIDE.md)

**Key points:**
- Only 2 widget sizes: `small` (300×150px) and `large` (600×400px)
- Small widget: Quick glance at status
- Large widget: Detailed view with actions
- Design widgets FIRST, full app second

**Edit `frontend/src/components/Widget.tsx` to customize your widgets.**

### Learn More

- **Complete Documentation**: [../README.md](../README.md)
- **Widget Design**: [WIDGET_DESIGN_GUIDE.md](WIDGET_DESIGN_GUIDE.md)
- **Architecture**: [ARCHITECTURE.md](ARCHITECTURE.md)
- **API Reference**: [API.md](API.md)
- **Marketplace Submission**: [SUBMISSION_REQUIREMENTS.md](SUBMISSION_REQUIREMENTS.md)

### Common Commands

```bash
# View logs
docker-compose logs -f backend
docker-compose logs -f frontend

# Restart services
docker-compose restart backend
docker-compose restart frontend

# Stop everything
docker-compose down

# Rebuild after dependency changes
docker-compose up --build
```

### Troubleshooting

**Backend not starting?**
- Check `docker-compose logs backend`
- Verify `ANTHROPIC_API_KEY` in `.env`
- Ensure PostgreSQL is running

**Frontend not connecting?**
- Check `VITE_API_URL` in `frontend/.env`
- Ensure backend is running on port 8000

**Agents not found?**
- Agents must be in `backend/agents/` directory
- File must have `@agent` decorator
- Restart backend after adding agents

---

## 🎉 You're Ready!

You've created:
- ✅ A functional agent
- ✅ A workflow that chains agents
- ✅ A user-configurable trigger (optional)

**Next:** Build your widgets and customize the frontend to match your app's purpose.

**Remember**: Widget design is critical! Read the [Widget Design Guide](WIDGET_DESIGN_GUIDE.md) before building your UI.

**Questions?** Check [../README.md](../README.md) for detailed documentation.

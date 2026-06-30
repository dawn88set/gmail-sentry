# Clarity Agentic App - Developer Guide

Complete guide for building agentic applications using the Clarity Platform seed template.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Understanding the Seed Template](#understanding-the-seed-template)
3. [Building Your First Agent](#building-your-first-agent)
4. [Creating Workflows](#creating-workflows)
5. [Implementing the Widget Endpoint](#implementing-the-widget-endpoint)
6. [Database Models & Persistence](#database-models--persistence)
7. [Configuration Management](#configuration-management)
8. [Testing Your App](#testing-your-app)
9. [Deployment to Clarity Platform](#deployment-to-clarity-platform)
10. [Common Pitfalls & Solutions](#common-pitfalls--solutions)

---

## Quick Start

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- Anthropic API key ([get one here](https://console.anthropic.com/))

### 60-Second Setup

```bash
# 1. Clone the seed template
git clone https://github.com/Clarittyai/agentic-app-seed.git my-agentic-app
cd my-agentic-app

# 2. Configure environment
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# 3. Start the app
docker-compose up

# 4. Test it works
curl http://localhost:8000/health
curl http://localhost:8000/api/widget
```

**Your app is now running!**
- Backend API: http://localhost:8000
- Frontend UI: http://localhost:3200
- API Docs: http://localhost:8000/docs

---

## Understanding the Seed Template

### Architecture Overview

The seed template provides a **complete full-stack agentic application** with:

```
agentic-app-seed/
├── backend/                    # FastAPI + AI Agents
│   ├── agents/                # AI agents (your business logic)
│   ├── workflows/             # Multi-agent orchestration
│   ├── triggers/              # Event triggers (coming soon)
│   ├── models.py              # Database models
│   ├── main.py                # FastAPI app & endpoints
│   └── config.py              # Configuration management
├── frontend/                   # React + Vite UI
│   ├── src/
│   │   ├── pages/             # Dashboard, Triggers, Widget
│   │   └── components/        # UI components
│   └── Dockerfile
├── docker-compose.yml          # Full-stack orchestration
├── .env.example                # Environment template
└── README.md                   # Quick reference
```

### Key Concepts

#### 1. **Agents** - Specialized AI Workers
Agents are Python classes that perform specific tasks using AI. Each agent:
- Has a clear single responsibility (analyze email, fetch data, send notification)
- Uses the `@agent` decorator for automatic registration
- Receives input via `AgentContext`
- Returns structured output via `AgentResult`

**Example**: `EmailAnalyzerAgent` takes an email and returns importance score + reasoning.

#### 2. **Workflows** - Multi-Step Orchestration
Workflows chain multiple agents together to accomplish complex tasks:
- Use the `@workflow` decorator
- Execute agents sequentially or in parallel
- Pass data between steps
- Handle errors and retries

**Example**: `EmailMonitoringWorkflow` fetches emails → analyzes them → sends notifications.

#### 3. **Triggers** - Automated Execution
Triggers start workflows automatically based on:
- **Schedule** (every hour, daily at 9am, etc.)
- **Events** (new data, threshold reached, webhook)
- **User actions** (button click, API call)

Users configure triggers through the Clarity Platform UI.

#### 4. **Widget Endpoint** - Dashboard Integration
The `/api/widget` endpoint powers your app's dashboard widget:
- Shows real-time app status
- Supports two sizes: `small` (quick glance), `large` (detailed view)
- Updates automatically when data changes
- **Required for all Clarity Platform apps**

---

## Building Your First Agent

### Step 1: Create Agent File

Create `backend/agents/my_agent.py`:

```python
"""
My First Agent
Simple example showing agent structure
"""

from claritty_sdk import agent, BaseAgent, AgentResult, AgentContext
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


@agent(
    id="my-first-agent",
    name="My First Agent",
    description="A simple example agent that processes data",
    category="example",
    inputs={
        "message": {
            "type": "string",
            "description": "Input message to process",
            "required": True
        }
    },
    outputs={
        "result": {
            "type": "string",
            "description": "Processed result"
        },
        "success": {
            "type": "boolean",
            "description": "Whether processing succeeded"
        }
    },
    integrations=[],  # No external integrations needed
    timeout=30
)
class MyFirstAgent(BaseAgent):
    """
    Example agent showing basic structure.

    This agent:
    1. Receives a message via input
    2. Processes it (in this case, just transforms it)
    3. Returns a result
    """

    async def execute(self, context: AgentContext) -> AgentResult:
        """
        Main execution method - implement your logic here.
        """
        try:
            # Get input data
            message = context.get_input("message")

            if not message:
                return AgentResult(
                    success=False,
                    error="No message provided"
                )

            context.log("info", f"Processing message: {message}")

            # Do your processing here
            result = f"Processed: {message.upper()}"

            context.log("info", "Processing complete")

            return AgentResult(
                success=True,
                data={
                    "result": result,
                    "success": True
                },
                metadata={
                    "agent_id": "my-first-agent",
                    "input_length": len(message)
                }
            )

        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            return AgentResult(
                success=False,
                error=f"Execution failed: {str(e)}"
            )
```

### Step 2: Agent Registration

Agents are **automatically discovered and registered** on startup!

The seed template uses auto-discovery (see `backend/infrastructure/discovery.py`):
- Scans `backend/agents/` for `@agent` decorators
- Registers all agents in `AgentRegistry`
- Makes them available via API at `/api/agents`

**No manual registration needed!**

### Step 3: Test Your Agent

```bash
# Restart the backend to discover your new agent
docker-compose restart backend

# List all agents (should include your new one)
curl http://localhost:8000/api/agents

# Execute your agent
curl -X POST http://localhost:8000/api/agents/my-first-agent/execute \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-user" \
  -d '{"message": "hello world"}'
```

**Expected Response**:
```json
{
  "success": true,
  "data": {
    "result": "Processed: HELLO WORLD",
    "success": true
  },
  "error": null,
  "metadata": {
    "agent_id": "my-first-agent",
    "input_length": 11
  }
}
```

---

## Creating Workflows

### Step 1: Create Workflow File

Create `backend/workflows/my_workflow.py`:

```python
"""
My First Workflow
Example showing multi-agent orchestration
"""

from claritty_sdk import workflow, WorkflowContext, ExecutionMode
import logging

logger = logging.getLogger(__name__)


@workflow(
    id="my-first-workflow",
    name="My First Workflow",
    description="Example workflow that chains multiple agents",
    execution_mode=ExecutionMode.SEQUENTIAL
)
async def my_first_workflow(context: WorkflowContext):
    """
    Example workflow showing agent orchestration.

    This workflow:
    1. Gets input data from trigger
    2. Executes Agent A
    3. Passes results to Agent B
    4. Returns final output
    """
    context.log("info", "🚀 Starting my first workflow")

    # Get input from trigger
    input_message = context.get_input("message", "default message")

    # Step 1: Execute first agent
    context.log("info", "Step 1: Processing with MyFirstAgent...")

    from claritty_sdk import AgentRegistry, AgentContext

    agent_a_class = AgentRegistry.get_agent("my-first-agent")
    if not agent_a_class:
        context.log("error", "MyFirstAgent not found")
        return

    agent_a = agent_a_class()
    agent_a_context = AgentContext(
        user_id=context.user_id,
        input_data={"message": input_message},
        integrations=context.integrations,
        metadata=context.metadata,
        execution_id=f"{context.execution_id}_step1"
    )

    result_a = await agent_a.execute(agent_a_context)

    if not result_a.success:
        context.log("error", f"Agent A failed: {result_a.error}")
        return

    context.log("info", f"✅ Step 1 complete: {result_a.data}")

    # Step 2: Could execute another agent with result_a.data
    # For now, just store final output

    context.set_output("workflow_result", result_a.data)
    context.set_output("success", True)

    context.log("info", "✅ Workflow complete!")
```

### Step 2: Test Your Workflow

```bash
# Restart to discover workflow
docker-compose restart backend

# List workflows
curl http://localhost:8000/api/workflows

# Execute workflow
curl -X POST http://localhost:8000/api/workflows/my-first-workflow/execute \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-user" \
  -d '{"message": "test workflow"}'
```

---

## Implementing the Widget Endpoint

The `/api/widget` endpoint is **REQUIRED** for all Clarity Platform apps. It powers the dashboard widget that users see.

### Widget Requirements

✅ **Must support two sizes**: `small` and `large`
✅ **Must accept `X-User-ID` header** for multi-tenancy
✅ **Must return JSON** with widget data
✅ **Should update in real-time** (when data changes)

### Example Implementation

In `backend/main.py`, the widget endpoint is already implemented:

```python
@app.get("/api/widget")
async def get_widget_data(
    size: str = "large",
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    db: Session = Depends(get_db)
):
    """
    Widget data endpoint - REQUIRED by Clarity platform.

    Args:
        size: "small" (quick glance) or "large" (detailed view)
        x_user_id: User ID from Clarity platform (or "test-user" for dev)

    Returns:
        JSON data customized for widget size
    """
    user_id = x_user_id if x_user_id else "test-user"

    # YOUR LOGIC HERE - Example shows email monitoring data
    if size == "small":
        # Small widget: Key metrics only
        return {
            "important_count": 5,
            "status": "active",
            "last_update": "2 minutes ago"
        }
    else:  # large
        # Large widget: Detailed information
        return {
            "important_count": 5,
            "total_processed": 127,
            "accuracy": "94%",
            "recent_items": [
                {"title": "Item 1", "score": 95},
                {"title": "Item 2", "score": 87}
            ],
            "last_update": "2 minutes ago"
        }
```

### Customizing for Your App

Replace the example email data with your app's data:

**For a Crypto Signals App**:
```python
if size == "small":
    return {
        "buy_signals": 3,
        "hold_signals": 12,
        "avoid_signals": 2
    }
else:  # large
    return {
        "buy_signals": 3,
        "hold_signals": 12,
        "avoid_signals": 2,
        "top_recommendations": [
            {"coin": "BTC", "action": "BUY", "confidence": 85},
            {"coin": "ETH", "action": "HOLD", "confidence": 72}
        ]
    }
```

### Testing Your Widget

```bash
# Test small widget
curl "http://localhost:8000/api/widget?size=small" \
  -H "X-User-ID: test-user"

# Test large widget
curl "http://localhost:8000/api/widget?size=large" \
  -H "X-User-ID: test-user"
```

---

## Database Models & Persistence

### Creating Database Models

Add models to `backend/models.py`:

```python
from sqlalchemy import Column, String, Integer, Boolean, DateTime, JSON
from datetime import datetime
import uuid
from backend.database import Base


class MyData(Base):
    """
    Example data model for your app.
    """
    __tablename__ = "my_data"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)

    # Your fields
    title = Column(String, nullable=False)
    data = Column(JSON)
    score = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

### Database Migrations

The seed uses **SQLAlchemy** with automatic table creation on startup:

```python
# In backend/main.py startup event
from backend.database import init_db

@app.on_event("startup")
async def startup_event():
    init_db()  # Creates all tables
```

**For production**, use Alembic migrations:
```bash
cd backend
alembic init migrations
alembic revision --autogenerate -m "Initial schema"
alembic upgrade head
```

---

## Configuration Management

### Two Configuration Files

#### 1. `.env.platform` (Platform-Managed) - **DO NOT EDIT**
Managed by Clarity Platform:
- Database credentials
- Redis URL
- AI API keys
- Security secrets
- Port allocation

#### 2. `.env` (User-Configured) - **Your Settings**
Your app-specific settings:
- AI operation mode (fast/balanced/quality)
- Workflow settings
- Notification preferences
- Custom integrations

### Using Configuration

```python
from backend.config import get_platform_config, get_app_config

# Platform config (infrastructure)
platform = get_platform_config()
db_url = platform.database_url
api_key = platform.anthropic_api_key

# App config (behavior)
app = get_app_config()
mode = app.ai_operation_mode  # "fast", "balanced", or "quality"
retries = app.workflow_max_retries
```

### Adding New Config Fields

1. **Add to `backend/config.py`** in `AppConfig` class:
```python
class AppConfig(BaseModel):
    my_custom_setting: str = Field(
        'default_value',
        description="Description of setting"
    )
```

2. **Add to `.env.example`**:
```bash
# My Custom Setting
MY_CUSTOM_SETTING=default_value
```

3. **Document in app-config.json** (for Clarity Platform UI)

---

## Testing Your App

### Local Testing

```bash
# Run all tests
docker-compose exec backend pytest

# Run specific test file
docker-compose exec backend pytest tests/test_agents.py

# With coverage
docker-compose exec backend pytest --cov=backend tests/
```

### Testing Agents

Create `backend/tests/test_my_agent.py`:

```python
import pytest
from backend.agents.my_agent import MyFirstAgent
from claritty_sdk import AgentContext


@pytest.mark.asyncio
async def test_my_agent_success():
    """Test agent with valid input"""
    agent = MyFirstAgent()

    context = AgentContext(
        user_id="test-user",
        input_data={"message": "hello"},
        integrations={},
        metadata={},
        execution_id="test-123"
    )

    result = await agent.execute(context)

    assert result.success == True
    assert "HELLO" in result.data["result"]


@pytest.mark.asyncio
async def test_my_agent_missing_input():
    """Test agent with missing input"""
    agent = MyFirstAgent()

    context = AgentContext(
        user_id="test-user",
        input_data={},  # No message
        integrations={},
        metadata={},
        execution_id="test-124"
    )

    result = await agent.execute(context)

    assert result.success == False
    assert "No message provided" in result.error
```

### Testing Workflows

```python
@pytest.mark.asyncio
async def test_my_workflow():
    """Test workflow execution"""
    from backend.workflows.my_workflow import my_first_workflow
    from claritty_sdk import WorkflowContext

    context = WorkflowContext(
        user_id="test-user",
        trigger_data={"message": "test"},
        integrations={},
        metadata={},
        execution_id="workflow-test-1"
    )

    await my_first_workflow(context)

    result = context.get_output("workflow_result")
    assert result is not None
```

### Validation Script

Run the platform validation script:

```bash
# Validates all platform requirements
python scripts/validate-app.py

# Expected output:
# ✅ Health endpoint responding
# ✅ Widget endpoint found
# ✅ At least 1 agent registered
# ✅ At least 1 workflow registered
# ✅ Docker builds successfully
# ✅ All requirements met!
```

---

## Deployment to Clarity Platform

### Pre-Deployment Checklist

- [ ] `/api/health` endpoint returns 200 OK
- [ ] `/api/widget` endpoint implemented
- [ ] At least 1 agent registered
- [ ] At least 1 workflow created
- [ ] Database models defined
- [ ] `.env.example` documents all variables
- [ ] `docker-compose up` works locally
- [ ] Validation script passes: `python scripts/validate-app.py`

### Deployment Steps

1. **Push to GitHub**:
```bash
git add .
git commit -m "My agentic app ready for deployment"
git push origin main
```

2. **Connect to Clarity Platform**:
- Go to Clarity Marketplace
- Click "Deploy New App"
- Connect your GitHub repository
- Platform validates your app automatically

3. **Platform Provisions** (automatic):
- PostgreSQL database (isolated per user)
- Redis instance
- Environment variables
- SSL certificate
- Load balancing

4. **Deploy**:
- Platform builds Docker containers
- Runs health checks
- Goes live at `https://your-app.clarity.ai`

### Post-Deployment

- Widget appears in user dashboards
- Triggers can be configured by users
- Workflows execute automatically
- Logs available in Clarity console

---

## Common Pitfalls & Solutions

### ❌ Pitfall 1: "Agent not found" error

**Problem**: Agent defined but not showing in `/api/agents`

**Solution**:
1. Ensure `@agent` decorator is used
2. Restart backend: `docker-compose restart backend`
3. Check logs: `docker-compose logs backend`
4. Verify file is in `backend/agents/` directory

### ❌ Pitfall 2: Widget endpoint missing

**Problem**: Deployment fails with "Widget endpoint required"

**Solution**: Implement `/api/widget` endpoint in `main.py` (see Widget section above)

### ❌ Pitfall 3: Database connection errors

**Problem**: `sqlalchemy.exc.OperationalError: could not connect to server`

**Solution**:
1. Wait for PostgreSQL: `docker-compose logs postgres`
2. Check `DATABASE_URL` in `.env`
3. Verify `depends_on` in `docker-compose.yml`

### ❌ Pitfall 4: ANTHROPIC_API_KEY not set

**Problem**: Agents fail with "API key not found"

**Solution**:
1. Add key to `.env`: `ANTHROPIC_API_KEY=sk-ant-...`
2. Restart: `docker-compose restart backend`
3. Verify: `docker-compose exec backend printenv | grep ANTHROPIC`

### ❌ Pitfall 5: CORS errors in frontend

**Problem**: Frontend can't call backend API

**Solution**: Check `FRONTEND_URL` in `.env` matches your frontend port (default: `http://localhost:3200`)

### ❌ Pitfall 6: Workflow stuck/not executing

**Problem**: Workflow triggered but never completes

**Solution**:
1. Check workflow logs: `docker-compose logs backend | grep workflow`
2. Verify all agents in workflow exist
3. Check for exceptions in agent execution
4. Add error handling in workflow code

---

## Need Help?

- **Documentation**: See `ARCHITECTURE.md` for technical details
- **Customization**: See `CUSTOMIZATION_GUIDE.md` for step-by-step guide
- **Requirements**: See `REQUIREMENTS.md` for platform requirements
- **FAQ**: See `FAQ.md` for common questions
- **Issues**: https://github.com/Clarittyai/agentic-app-seed/issues

---

**Ready to build something amazing? Start with the Quick Start above!** 🚀

# Clarity Platform Requirements

Complete checklist of requirements for deploying apps to the Clarity Platform.

---

## Quick Validation

Run the automated validation script:

```bash
python scripts/validate-app.py
```

This checks all requirements below automatically. Use this checklist for manual verification or understanding platform expectations.

---

## 🔴 CRITICAL REQUIREMENTS (Deployment Blockers)

These **MUST** be present for deployment to succeed:

### 1. Health Check Endpoint ✅

**Requirement**: `/health` endpoint that returns 200 OK

**Implementation** (`backend/main.py`):
```python
@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

**Test**:
```bash
curl http://localhost:8000/health
# Expected: {"status": "healthy"}
```

**Why Required**: Platform uses this for container health monitoring and load balancing.

---

### 2. Widget Endpoint ✅

**Requirement**: `/api/widget` endpoint that returns dashboard data

**Implementation** (`backend/main.py`):
```python
@app.get("/api/widget")
async def get_widget_data(
    size: str = "large",
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    db: Session = Depends(get_db)
):
    # Must support size: "small" and "large"
    # Must accept X-User-ID header for multi-tenancy
    # Must return JSON

    if size == "small":
        return {"key_metric": 123, "status": "active"}
    else:
        return {"detailed": "data", "metrics": [...]}
```

**Test**:
```bash
curl "http://localhost:8000/api/widget?size=small" -H "X-User-ID: test-user"
curl "http://localhost:8000/api/widget?size=large" -H "X-User-ID: test-user"
```

**Widget Data Requirements**:
- ✅ Must return valid JSON
- ✅ Must support `size` parameter: "small" or "large"
- ✅ Must respect `X-User-ID` header (user isolation)
- ✅ Small widget: 1-3 key metrics, minimal data
- ✅ Large widget: Detailed view with charts/lists
- ✅ Should update in real-time (when data changes)

**Why Required**: Powers user's dashboard widget in Clarity Platform.

---

### 3. At Least ONE Agent ✅

**Requirement**: Minimum 1 agent registered using `@agent` decorator

**Implementation** (`backend/agents/my_agent.py`):
```python
from claritty_sdk import agent, BaseAgent

@agent(
    id="my-agent",
    name="My Agent",
    description="What this agent does",
    category="data",
    inputs={...},
    outputs={...}
)
class MyAgent(BaseAgent):
    async def execute(self, context):
        # Agent logic
        pass
```

**Test**:
```bash
curl http://localhost:8000/api/agents
# Expected: {"agents": [{"id": "my-agent", ...}]}
```

**Why Required**: Agentic apps must have at least one AI agent. Otherwise, it's just a regular web app.

---

### 4. At Least ONE Workflow ✅

**Requirement**: Minimum 1 workflow registered using `@workflow` decorator

**Implementation** (`backend/workflows/my_workflow.py`):
```python
from claritty_sdk import workflow, WorkflowContext

@workflow(
    id="my-workflow",
    name="My Workflow",
    description="What this workflow does",
    execution_mode=ExecutionMode.SEQUENTIAL
)
async def my_workflow(context: WorkflowContext):
    # Workflow logic
    pass
```

**Test**:
```bash
curl http://localhost:8000/api/workflows
# Expected: {"workflows": [{"id": "my-workflow", ...}]}
```

**Why Required**: Workflows orchestrate agents. Without workflows, agents can't work together.

---

### 5. Docker Configuration ✅

**Requirement**: App must build and run with Docker Compose

**Required Files**:
- ✅ `docker-compose.yml` - Orchestrates all services
- ✅ `backend/Dockerfile` - Backend container definition
- ✅ `frontend/Dockerfile` - Frontend container definition

**Services Required**:
- ✅ `postgres` - PostgreSQL database
- ✅ `backend` - FastAPI application
- ✅ `frontend` - React application

**Test**:
```bash
docker-compose build
docker-compose up -d
docker-compose ps
# All services should be "healthy" or "running"
```

**Why Required**: Platform deploys apps as Docker containers for isolation and scalability.

---

### 6. Environment Variables Documented ✅

**Requirement**: All required environment variables listed in `.env.example`

**Minimum Required**:
```bash
# .env.example
ANTHROPIC_API_KEY=sk-ant-xxxxx
```

**Best Practice**:
```bash
# ============================================================================
# REQUIRED
# ============================================================================
ANTHROPIC_API_KEY=sk-ant-xxxxx

# ============================================================================
# OPTIONAL (Auto-configured)
# ============================================================================
# DATABASE_URL=postgresql://...
# BACKEND_PORT=8000
# FRONTEND_PORT=3200
```

**Test**:
```bash
# Verify .env.example exists
ls -la .env.example

# Verify ANTHROPIC_API_KEY is documented
grep "ANTHROPIC_API_KEY" .env.example
```

**Why Required**: Users need to know what configuration is needed before deployment.

---

## 🟡 RECOMMENDED REQUIREMENTS (Best Practices)

Not blockers, but strongly recommended for production apps:

### 7. Database Models for User Data ⚠️

**Recommendation**: Define SQLAlchemy models in `backend/models.py`

**Example**:
```python
class UserData(Base):
    __tablename__ = "user_data"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)  # IMPORTANT
    # ... your fields
```

**Critical**: Always include `user_id` field and filter by it for multi-tenancy:
```python
data = db.query(UserData).filter(
    UserData.user_id == current_user_id
).all()
```

**Why Recommended**: Enables data persistence and user-specific data isolation.

---

### 8. Automated Tests ⚠️

**Recommendation**: Include tests for agents and workflows

**Structure**:
```
backend/
  tests/
    test_agents.py
    test_workflows.py
    test_api.py
```

**Example Test** (`backend/tests/test_agents.py`):
```python
import pytest
from backend.agents.my_agent import MyAgent
from claritty_sdk import AgentContext

@pytest.mark.asyncio
async def test_my_agent():
    agent = MyAgent()
    context = AgentContext(
        user_id="test",
        input_data={"input": "test"},
        integrations={},
        metadata={},
        execution_id="test-1"
    )

    result = await agent.execute(context)
    assert result.success == True
```

**Test**:
```bash
docker-compose exec backend pytest
```

**Why Recommended**: Catches bugs before deployment, ensures reliability.

---

### 9. Error Handling ⚠️

**Recommendation**: All agents and workflows should handle errors gracefully

**Pattern**:
```python
async def execute(self, context):
    try:
        # Your logic
        return AgentResult(success=True, data={...})
    except Exception as e:
        logger.error(f"Agent failed: {e}")
        return AgentResult(success=False, error=str(e))
```

**Why Recommended**: Prevents crashes, provides better user experience.

---

### 10. Logging ⚠️

**Recommendation**: Use context.log() for workflow visibility

**Pattern**:
```python
async def my_workflow(context: WorkflowContext):
    context.log("info", "Starting step 1")
    # ... execute step
    context.log("info", "✅ Step 1 complete")

    context.log("error", "Step failed: reason")
```

**Why Recommended**: Users can see execution progress in Clarity Platform UI.

---

### 11. User Integration Support ⚠️

**Recommendation**: If you need external APIs, use integration system

**Example**:
```python
@agent(
    integrations=[{
        "service": "slack",
        "required": True,
        "auth_type": "oauth"
    }]
)
class SlackNotifierAgent(BaseAgent):
    async def execute(self, context):
        slack_token = context.get_integration("slack").get("token")
        # Use Slack API with token
```

**Why Recommended**: Allows users to connect their own accounts securely.

---

## 🟢 OPTIONAL ENHANCEMENTS

Nice-to-have features for advanced apps:

### 12. Trigger Templates ✨

Define trigger templates for user configuration:

```python
from claritty_sdk import trigger_template

@trigger_template(
    id="daily-scan",
    name="Daily Scan",
    template_type=TriggerType.SCHEDULE,
    workflow_id="my-workflow"
)
```

**Why Optional**: Platform provides default manual execution. Triggers add automation.

---

### 13. Custom API Endpoints ✨

Add app-specific endpoints beyond /health and /widget:

```python
@app.get("/api/stats")
async def get_stats(user_id: str = Depends(get_current_user)):
    # Custom endpoint for additional functionality
    pass
```

**Why Optional**: Widget endpoint covers most dashboard needs.

---

### 14. Frontend Customization ✨

Customize the React frontend beyond basic dashboard:

- Custom visualizations
- Interactive controls
- Real-time updates
- Mobile-responsive design

**Why Optional**: Platform can embed widget in its own UI. Full frontend is a bonus.

---

## Validation Checklist

Use this for pre-deployment verification:

### Backend

- [ ] `backend/main.py` exists
- [ ] `/health` endpoint returns 200 OK
- [ ] `/api/widget` endpoint returns valid JSON
- [ ] Widget supports both "small" and "large" sizes
- [ ] At least 1 agent defined in `backend/agents/`
- [ ] At least 1 workflow defined in `backend/workflows/`
- [ ] `backend/models.py` has database models
- [ ] `backend/Dockerfile` exists and builds
- [ ] All imports resolve (no missing dependencies)

### Frontend

- [ ] `frontend/` directory exists
- [ ] `frontend/Dockerfile` exists and builds
- [ ] Frontend connects to backend API
- [ ] Dashboard page displays widget data
- [ ] UI is responsive (mobile + desktop)

### Infrastructure

- [ ] `docker-compose.yml` exists
- [ ] `docker-compose up` succeeds
- [ ] PostgreSQL service starts and is healthy
- [ ] Backend service starts and passes health check
- [ ] Frontend service starts and serves UI
- [ ] All services connect properly (networking)

### Configuration

- [ ] `.env.example` exists and is complete
- [ ] `ANTHROPIC_API_KEY` is documented
- [ ] All custom env vars are documented
- [ ] No secrets committed to git (use .env.example only)

### Documentation

- [ ] `README.md` explains what the app does
- [ ] Installation instructions are clear
- [ ] Environment setup is documented
- [ ] Testing instructions provided

### Testing

- [ ] `docker-compose up` works locally
- [ ] Health check: `curl http://localhost:8000/health` succeeds
- [ ] Widget check: `curl http://localhost:8000/api/widget` succeeds
- [ ] Agents list: `curl http://localhost:8000/api/agents` shows agents
- [ ] Workflows list: `curl http://localhost:8000/api/workflows` shows workflows
- [ ] Validation script: `python scripts/validate-app.py` passes

---

## Platform Deployment Requirements

Additional requirements when deploying to Clarity Platform (handled automatically):

### Platform Provisions

✅ **Database** - PostgreSQL instance per app
✅ **Secrets** - JWT, session secrets, API keys
✅ **Networking** - Internal DNS, load balancer
✅ **SSL** - HTTPS certificate
✅ **Monitoring** - Health checks, logs, metrics
✅ **Scaling** - Auto-scaling based on load

### Platform Injects

The platform automatically injects these environment variables:

```bash
# Platform-managed (DO NOT set these)
DATABASE_URL=postgresql://...          # Provisioned database
CLARITY_APP_ID=app-xxxxx              # Your app's ID
CLARITY_PLATFORM_URL=https://...      # Platform URL
PORT=8000                              # Assigned port
REDIS_URL=redis://...                  # Shared Redis (optional)
JWT_SECRET=...                         # Auto-generated
SESSION_SECRET=...                     # Auto-generated
```

**You should NOT set these** - platform manages them automatically.

---

## Common Validation Failures

### ❌ "Health endpoint not found"

**Problem**: `/health` endpoint missing or not responding

**Fix**:
```python
# Add to backend/main.py
@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

### ❌ "Widget endpoint not found"

**Problem**: `/api/widget` endpoint missing

**Fix**: Implement widget endpoint (see Requirement #2 above)

### ❌ "No agents registered"

**Problem**: No agents found in `backend/agents/` or missing `@agent` decorator

**Fix**:
1. Ensure agents use `@agent` decorator
2. Place agents in `backend/agents/` directory
3. Restart backend to trigger auto-discovery

### ❌ "No workflows registered"

**Problem**: No workflows found or missing `@workflow` decorator

**Fix**:
1. Ensure workflows use `@workflow` decorator
2. Place workflows in `backend/workflows/` directory
3. Restart backend

### ❌ "Docker build failed"

**Problem**: Docker image fails to build

**Common causes**:
- Missing dependencies in `requirements.txt`
- Python version mismatch
- Invalid Dockerfile syntax

**Fix**:
```bash
# Check build logs
docker-compose build backend

# Test dependencies
pip install -r backend/requirements.txt
```

### ❌ "Database connection failed"

**Problem**: Backend can't connect to PostgreSQL

**Fix**:
1. Ensure PostgreSQL service is healthy: `docker-compose ps`
2. Check `DATABASE_URL` in `.env`
3. Verify `depends_on` in `docker-compose.yml`

### ❌ "ANTHROPIC_API_KEY not set"

**Problem**: Missing required API key

**Fix**:
1. Get API key from https://console.anthropic.com/
2. Add to `.env`: `ANTHROPIC_API_KEY=sk-ant-...`
3. Restart backend

---

## Automated Validation

### Run Validation Script

```bash
python scripts/validate-app.py
```

**Output (Success)**:
```
🔍 Validating Clarity Platform App...

✅ Health endpoint responding
✅ Widget endpoint found
✅ Agents registered: 3
   - data-fetcher
   - data-analyzer
   - action-executor
✅ Workflows registered: 1
   - main-workflow
✅ Docker builds successfully
✅ Database models defined: 2
✅ Environment variables documented
✅ Tests pass: 15/15

🎉 All requirements met! Ready to deploy to Clarity Platform.
```

**Output (Failure)**:
```
🔍 Validating Clarity Platform App...

✅ Health endpoint responding
❌ Widget endpoint not found
   → Add GET /api/widget endpoint to backend/main.py
✅ Agents registered: 3
❌ No workflows registered
   → Create at least 1 workflow in backend/workflows/
⚠️  Docker build warnings (non-fatal)
✅ Database models defined: 2
✅ Environment variables documented

❌ 2 critical issues found. Fix before deploying.
```

---

## GitHub CI Validation

When you push to GitHub, CI automatically runs validation:

```yaml
# .github/workflows/validate-app.yml
name: Validate App

on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Validate app requirements
        run: python scripts/validate-app.py
      - name: Build Docker containers
        run: docker-compose build
      - name: Run tests
        run: docker-compose run backend pytest
```

**CI Badge** (shows validation status):

[![Validation](https://github.com/youruser/your-app/workflows/Validate%20App/badge.svg)](https://github.com/youruser/your-app/actions)

---

## Need Help?

If your app fails validation:

1. **Run validation locally**: `python scripts/validate-app.py`
2. **Check error messages**: They provide specific fixes
3. **Review requirements**: This document covers all cases
4. **See examples**: Check CUSTOMIZATION_GUIDE.md for patterns
5. **Ask for help**: GitHub Issues or Clarity Platform support

---

## Summary: Pre-Deployment Checklist

Quick checklist before deploying:

```bash
# 1. Validation passes
python scripts/validate-app.py

# 2. Local testing works
docker-compose up
curl http://localhost:8000/health
curl http://localhost:8000/api/widget

# 3. Tests pass
docker-compose exec backend pytest

# 4. Environment documented
cat .env.example

# 5. Git ready
git status
git add .
git commit -m "Ready for deployment"
git push origin main

# 6. Deploy to Clarity Platform
# (via Clarity Marketplace UI)
```

**If all steps pass → Ready to deploy! 🚀**

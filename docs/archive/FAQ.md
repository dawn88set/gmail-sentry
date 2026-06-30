# Frequently Asked Questions (FAQ)

Common questions and troubleshooting guide based on real developer experiences building agentic apps.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Project Structure](#project-structure)
3. [Agents & Workflows](#agents--workflows)
4. [Database & Data](#database--data)
5. [Docker & Deployment](#docker--deployment)
6. [Configuration](#configuration)
7. [Testing & Validation](#testing--validation)
8. [Errors & Troubleshooting](#errors--troubleshooting)

---

## Getting Started

### Q: Where should I clone this repository?

**A**: Clone it **outside** your main project directory, as a standalone project.

❌ **Wrong**:
```bash
cd my-main-project/
git clone https://github.com/Clarittyai/agentic-app-seed.git
# Now it's nested inside your main project
```

✅ **Correct**:
```bash
cd ~/projects/
git clone https://github.com/Clarittyai/agentic-app-seed.git my-crypto-app
cd my-crypto-app
```

**Why**: The seed is a complete standalone app template, not a library or subproject.

---

### Q: Do I modify the seed template or build something separate?

**A**: **Modify the seed template directly**. It's designed to be customized for your specific use case.

The seed template is your starting point:
1. Clone it
2. Customize agents, workflows, models
3. Replace example email logic with your app logic
4. Deploy to Clarity Platform

See `CUSTOMIZATION_GUIDE.md` for step-by-step instructions.

---

### Q: What's the fastest way to get started?

**A**: Follow the 60-second quick start:

```bash
# 1. Clone & navigate
git clone https://github.com/Clarittyai/agentic-app-seed.git my-app
cd my-app

# 2. Configure
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# 3. Start
docker-compose up

# 4. Test
curl http://localhost:8000/health
curl http://localhost:8000/api/widget
```

Then read `DEVELOPER_GUIDE.md` for next steps.

---

## Project Structure

### Q: Do I need both backend AND frontend?

**A**: **Yes**, the Clarity Platform requires both.

- **Backend**: FastAPI + AI agents (required)
- **Frontend**: React dashboard (required)
- **Database**: PostgreSQL (required)

Even if your app is primarily backend-focused, you still need a minimal frontend to display the widget.

---

### Q: Can I use a different tech stack?

**A**: For now, the seed uses Python/FastAPI backend and React/TypeScript frontend. These are recommended for best Clarity Platform compatibility.

**Backend alternatives** (not officially supported yet):
- Node.js with Express
- Go with Gin

**Frontend alternatives**:
- Vue.js
- Svelte
- Plain HTML/JS

**Database**: PostgreSQL is required by Clarity Platform.

---

### Q: Where should my business logic go?

**A**: Organize by responsibility:

- **Agents** (`backend/agents/`) - Individual AI tasks
  - Data fetching
  - Analysis with Claude AI
  - Action execution

- **Workflows** (`backend/workflows/`) - Multi-step orchestration
  - Chain agents together
  - Handle complex business processes

- **Models** (`backend/models.py`) - Data persistence
  - Database schema
  - User data

**Example**:
```
Agent: RedditDiscoveryAgent → Scans Reddit
Agent: SentimentAnalyzer → Analyzes posts
Agent: RecommendationEngine → Generates signals
Workflow: DailyRedditScan → Orchestrates all 3 agents
```

---

## Agents & Workflows

### Q: How do I create a new agent?

**A**: Use the `@agent` decorator:

```python
from claritty_sdk import agent, BaseAgent, AgentResult, AgentContext

@agent(
    id="my-agent",
    name="My Agent",
    description="What it does",
    category="data",
    inputs={...},
    outputs={...}
)
class MyAgent(BaseAgent):
    async def execute(self, context: AgentContext) -> AgentResult:
        # Your logic here
        return AgentResult(success=True, data={...})
```

Save in `backend/agents/my_agent.py` and restart - it's auto-discovered!

---

### Q: My agent isn't showing up in /api/agents

**A**: Checklist:

1. ✅ Agent file is in `backend/agents/` directory
2. ✅ Class uses `@agent` decorator
3. ✅ Class inherits from `BaseAgent`
4. ✅ Backend has been restarted: `docker-compose restart backend`
5. ✅ No syntax errors in agent file

**Debug**:
```bash
# Check backend logs for errors
docker-compose logs backend | grep -i error

# List agents directory
ls -la backend/agents/

# Verify agent is valid Python
python -m py_compile backend/agents/my_agent.py
```

---

### Q: How do I pass data between agents in a workflow?

**A**: Use the workflow context:

```python
@workflow(id="my-workflow", ...)
async def my_workflow(context: WorkflowContext):
    # Agent 1: Fetch data
    fetcher_result = await fetcher_agent.execute(...)
    data = fetcher_result.data

    # Agent 2: Use data from Agent 1
    analyzer_result = await analyzer_agent.execute(
        AgentContext(input_data={"items": data["items"]})
    )

    # Store final results
    context.set_output("final_result", analyzer_result.data)
```

---

### Q: Should I use sequential or parallel workflow execution?

**A**: Depends on your use case:

**Sequential** (default):
```python
ExecutionMode.SEQUENTIAL
```
- Agents run one after another
- Agent B waits for Agent A to finish
- Use when Agent B needs Agent A's output

**Parallel** (future feature):
```python
ExecutionMode.PARALLEL
```
- Agents run concurrently
- Faster execution
- Use when agents are independent

For most workflows, start with SEQUENTIAL.

---

## Database & Data

### Q: How do I add a new database table?

**A**: Add a model to `backend/models.py`:

```python
class MyData(Base):
    __tablename__ = "my_data"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)  # Required!
    # Your fields...
    title = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
```

**Important**: Always include `user_id` for multi-tenancy!

Then restart: `docker-compose restart backend` (tables auto-create).

---

### Q: How do I query the database from an agent?

**A**: Database access is available in endpoints, not directly in agents. Instead, use the workflow context or pass database session:

```python
# In backend/main.py endpoint
@app.post("/api/my-endpoint")
async def my_endpoint(db: Session = Depends(get_db)):
    data = db.query(MyData).filter(
        MyData.user_id == user_id
    ).all()

    # Execute workflow with data
    result = await execute_workflow(...)
```

**For agents that need DB access**, create a service layer:

```python
# backend/services/data_service.py
class DataService:
    def __init__(self, db: Session):
        self.db = db

    def get_user_data(self, user_id: str):
        return self.db.query(MyData).filter(...).all()
```

---

### Q: How do I handle user-specific data (multi-tenancy)?

**A**: **Always filter by user_id**:

✅ **Correct**:
```python
data = db.query(MyData).filter(
    MyData.user_id == current_user_id
).all()
```

❌ **Wrong** (shows all users' data):
```python
data = db.query(MyData).all()
```

**In agents**, use `context.user_id`:
```python
async def execute(self, context: AgentContext):
    user_id = context.user_id
    # Use user_id for filtering
```

---

## Docker & Deployment

### Q: Docker containers won't start

**A**: Debug checklist:

```bash
# 1. Check .env file exists
ls -la .env

# 2. Check PostgreSQL started
docker-compose ps postgres

# 3. Check PostgreSQL logs
docker-compose logs postgres

# 4. Check backend logs
docker-compose logs backend

# 5. Rebuild containers
docker-compose down -v
docker-compose build --no-cache
docker-compose up
```

Common issues:
- Missing `.env` file → `cp .env.example .env`
- Port already in use → Change ports in `.env`
- Missing API key → Add `ANTHROPIC_API_KEY` to `.env`

---

### Q: "Port 8000 already in use" error

**A**: Either stop the conflicting service or change ports:

**Option 1**: Stop conflicting service:
```bash
# Find what's using port 8000
lsof -i :8000

# Kill it
kill -9 <PID>
```

**Option 2**: Change port in `.env`:
```bash
BACKEND_PORT=8080  # Use different port
```

Then restart: `docker-compose up`

---

### Q: How do I rebuild after code changes?

**A**: Depends on what changed:

**Agent/Workflow changes** (Python code):
```bash
docker-compose restart backend
```

**Dependency changes** (requirements.txt):
```bash
docker-compose build backend
docker-compose up -d
```

**Frontend changes** (React):
```bash
docker-compose restart frontend
```

**Everything** (nuclear option):
```bash
docker-compose down -v
docker-compose build
docker-compose up
```

---

## Configuration

### Q: What's the difference between .env and .env.platform?

**A**:

- **`.env`** - Your app-specific settings (you edit this)
  - AI operation mode
  - Custom API keys
  - Notification settings

- **`.env.platform`** - Platform infrastructure (Clarity manages this)
  - Database credentials
  - Redis URL
  - Security secrets
  - Port allocation

**In development**, only `.env` exists. In production, Clarity Platform injects `.env.platform`.

---

### Q: Which environment variables are required?

**A**: Only ONE is truly required:

```bash
ANTHROPIC_API_KEY=sk-ant-xxxxx
```

Everything else has smart defaults for local development:
- `DATABASE_URL` → auto-configured by Docker
- `PORT` → defaults to 8000
- `FRONTEND_URL` → defaults to http://localhost:3200

See `.env.example` for all available options.

---

### Q: How do I add a new configuration option?

**A**: Three steps:

1. **Add to backend/config.py**:
```python
class AppConfig(BaseModel):
    my_setting: str = Field('default', description="My setting")
```

2. **Add to .env.example**:
```bash
MY_SETTING=default_value
```

3. **Use in code**:
```python
from backend.config import get_app_config
config = get_app_config()
value = config.my_setting
```

---

## Testing & Validation

### Q: How do I validate my app before deploying?

**A**: Run the validation script:

```bash
python scripts/validate-app.py
```

This checks:
- ✅ Health endpoint
- ✅ Widget endpoint
- ✅ Agents registered
- ✅ Workflows registered
- ✅ Docker builds
- ✅ Environment variables

**Exit codes**:
- `0` = Ready to deploy
- `1` = Critical failures
- `2` = Warnings (can still deploy)

---

### Q: My validation passes locally but fails in CI

**A**: Common causes:

1. **Missing .env in CI** - GitHub Actions needs dummy values
   ```yaml
   - name: Create .env
     run: echo "ANTHROPIC_API_KEY=sk-test" >> .env
   ```

2. **Different port in CI** - Use `localhost:8000` consistently

3. **Timing issues** - Services need time to start
   ```bash
   docker-compose up -d
   sleep 30  # Wait for startup
   ```

4. **Database not ready** - Add health checks to docker-compose.yml

---

### Q: How do I write tests for my agents?

**A**: Use pytest with async:

```python
# backend/tests/test_my_agent.py
import pytest
from backend.agents.my_agent import MyAgent
from claritty_sdk import AgentContext

@pytest.mark.asyncio
async def test_my_agent():
    agent = MyAgent()
    context = AgentContext(
        user_id="test-user",
        input_data={"input": "test"},
        integrations={},
        metadata={},
        execution_id="test-1"
    )

    result = await agent.execute(context)

    assert result.success == True
    assert "expected_output" in result.data
```

Run with:
```bash
docker-compose exec backend pytest
```

---

## Errors & Troubleshooting

### Q: "ANTHROPIC_API_KEY not set" error

**Problem**: Agent fails with API key error

**Fix**:
```bash
# 1. Check .env file
cat .env | grep ANTHROPIC

# 2. Add key if missing
echo "ANTHROPIC_API_KEY=sk-ant-your-key" >> .env

# 3. Restart backend
docker-compose restart backend

# 4. Verify it's loaded
docker-compose exec backend printenv | grep ANTHROPIC
```

**Get API key**: https://console.anthropic.com/

---

### Q: "Agent execution failed" error

**Debug steps**:

```bash
# 1. Check agent logs
docker-compose logs backend | grep -i error

# 2. Test agent manually
curl -X POST http://localhost:8000/api/agents/my-agent/execute \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-user" \
  -d '{"test": "data"}'

# 3. Check agent code for exceptions
python -m py_compile backend/agents/my_agent.py

# 4. Test with minimal input
# Ensure agent handles missing/invalid input gracefully
```

Common causes:
- Missing required input
- Unhandled exceptions
- Invalid Anthropic API call
- Database connection issue

---

### Q: Widget endpoint returns empty data

**Check list**:

1. Is widget endpoint implemented?
   ```bash
   curl http://localhost:8000/api/widget?size=large
   ```

2. Is database populated with data?
   ```bash
   docker-compose exec postgres psql -U clarity_user -d clarity_agentic_app -c "SELECT COUNT(*) FROM your_table;"
   ```

3. Is user_id filtering correct?
   ```python
   # Make sure you're filtering by user_id
   data = db.query(Model).filter(
       Model.user_id == user_id  # This!
   ).all()
   ```

4. Check backend logs:
   ```bash
   docker-compose logs backend | tail -100
   ```

---

### Q: Frontend can't connect to backend (CORS error)

**Symptom**: Browser console shows CORS error

**Fix**:

1. **Check FRONTEND_URL in .env**:
   ```bash
   FRONTEND_URL=http://localhost:3200
   ```

2. **Verify CORS middleware in backend/main.py**:
   ```python
   app.add_middleware(
       CORSMiddleware,
       allow_origins=[FRONTEND_URL, "http://localhost:3000"],
       allow_credentials=True,
       allow_methods=["*"],
       allow_headers=["*"],
   )
   ```

3. **Restart backend**:
   ```bash
   docker-compose restart backend
   ```

---

### Q: Database connection refused

**Symptoms**:
```
sqlalchemy.exc.OperationalError: could not connect to server
```

**Fix**:

```bash
# 1. Check PostgreSQL is running
docker-compose ps postgres
# Should show "healthy" or "running"

# 2. Check PostgreSQL logs
docker-compose logs postgres

# 3. Verify DATABASE_URL
cat .env | grep DATABASE_URL

# 4. Test connection manually
docker-compose exec postgres psql -U clarity_user -d clarity_agentic_app -c "SELECT 1;"

# 5. Restart everything
docker-compose down -v
docker-compose up -d
```

---

### Q: Workflow gets stuck / never completes

**Debug**:

```bash
# 1. Check workflow logs
docker-compose logs backend | grep workflow

# 2. Check for agent failures
curl http://localhost:8000/api/workflows/my-workflow/execute \
  -X POST \
  -H "Authorization: Bearer test-user" \
  -H "Content-Type: application/json"

# 3. Look for exceptions
docker-compose logs backend | grep -i exception

# 4. Verify all agents exist
curl http://localhost:8000/api/agents
```

Common causes:
- Agent ID mismatch (agent not found)
- Agent throwing unhandled exception
- Infinite loop in workflow
- Missing await in async code

---

### Q: "No agents registered" in validation

**Troubleshoot**:

```bash
# 1. Verify agents exist
ls -la backend/agents/

# 2. Check for syntax errors
cd backend
python -m compileall agents/

# 3. Check agent uses @agent decorator
grep -r "@agent" backend/agents/

# 4. Check backend startup logs
docker-compose logs backend | grep "Registered"

# 5. Manually test discovery
docker-compose exec backend python -c "
from backend.infrastructure import discover_and_register_components
discover_and_register_components()
from claritty_sdk import AgentRegistry
print(AgentRegistry.list_agents())
"
```

---

## Need More Help?

### Resources

- **Developer Guide**: `DEVELOPER_GUIDE.md` - Complete technical reference
- **Customization Guide**: `CUSTOMIZATION_GUIDE.md` - Step-by-step customization
- **Requirements**: `REQUIREMENTS.md` - Platform requirements checklist
- **Architecture**: `ARCHITECTURE.md` - System design details

### Getting Support

1. **GitHub Issues**: https://github.com/Clarittyai/agentic-app-seed/issues
2. **Clarity Platform Docs**: https://docs.clarity.ai
3. **Community Discord**: [Link to Discord]
4. **Email Support**: support@clarity.ai

### Before Asking for Help

Please provide:
1. **What you're trying to do**: "I want to build X"
2. **What's happening**: Exact error message
3. **What you tried**: Steps you've taken
4. **Logs**: Relevant logs from `docker-compose logs`
5. **Environment**: OS, Docker version, Python version

**Example good question**:
> I'm trying to create a Reddit sentiment analyzer. When I start docker-compose, the backend crashes with "ModuleNotFoundError: No module named 'praw'". I added `praw==7.7.1` to requirements.txt and ran `docker-compose build backend` but still getting the error. Here are my logs: [paste logs]

---

**Still stuck? Ask on GitHub Issues - we're here to help!** 🚀

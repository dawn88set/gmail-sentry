# Architecture Documentation

This document provides a deep dive into the technical architecture of the Clarity Agentic App template.

## Understanding This Document

**New to Clarity?** Read [Understanding Clarity Platform](CLARITY_PLATFORM.md) first to understand:
- The Clarity ecosystem and marketplace
- What agentic apps are and why they exist
- How users interact with apps via widgets
- The deployment and hosting model

This document explains **how the architecture implements** the Clarity vision. It assumes you understand **why** things work this way.

---

## How This Architecture Fits the Clarity Ecosystem

### The Big Picture

Your agentic app lives within the Clarity Platform ecosystem:

```
Clarity Platform (The Marketplace)
    ↓
Your App (This Template)
    ↓
End Users (Via Widgets)
```

**Key Points**:
1. **Multi-Tenant by Design**: One deployment serves all users with complete data isolation
2. **Widget-First Interface**: Primary interaction is via widgets on the Clarity dashboard
3. **Platform-Managed Infrastructure**: Clarity handles hosting, scaling, monitoring
4. **Standardized Contracts**: Health endpoints, widget endpoints, authentication headers

### Architectural Principles Driven by Clarity

The architecture you see here is shaped by Clarity's requirements:

**Principle 1: User Autonomy**
- Users control trigger scheduling → DynamicTriggerManager with per-user configurations
- Users configure workflows → Template-based system with config_fields
- Users see personalized data → Multi-tenant database design with user_id filtering

**Principle 2: Widget-First UX**
- Widgets are primary interface → Dedicated `/api/widget` endpoint with size parameter
- Quick glance data → Small widget optimization (minimal data payload)
- Detailed interactions → Large widget with actionable data
- Advanced features → Full app (optional click-through from widget)

**Principle 3: Platform Integration**
- Clarity manages auth → X-User-ID header injection, no user management needed
- Clarity manages hosting → Docker containerization, health checks required
- Clarity manages scaling → Stateless backend, connection pooling
- Clarity manages monitoring → Health endpoint, execution logging

**Principle 4: Developer Experience**
- Focus on business logic → Auto-discovery eliminates boilerplate
- Fast iteration → Hot reload, zero-config development
- Clear separation → Infrastructure abstracted away from user code

---

## Table of Contents

1. [System Overview](#system-overview)
2. [SDK Architecture](#sdk-architecture)
3. [Backend Architecture](#backend-architecture)
4. [Frontend Architecture](#frontend-architecture)
5. [Database Design](#database-design)
6. [Auto-Discovery System](#auto-discovery-system)
7. [Trigger Management System](#trigger-management-system)
8. [Workflow Execution Engine](#workflow-execution-engine)
9. [Security Architecture](#security-architecture)
10. [Widget-First Design](#widget-first-design)

---

## System Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Clarity Platform                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Dashboard   │  │   Widgets    │  │  Marketplace │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                  │                  │               │
└─────────┼──────────────────┼──────────────────┼──────────────┘
          │                  │                  │
          │   Widget Data    │                  │
          │   & Full App     │                  │
          └──────────────────┴──────────────────┘
                             │
┌────────────────────────────┼────────────────────────────────┐
│         Your Agentic App   │                                 │
│                            ▼                                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              FastAPI Backend (Port 8000)               │  │
│  │  ┌──────────────────────────────────────────────────┐ │  │
│  │  │  API Layer (17 endpoints)                         │ │  │
│  │  │  - Agent discovery & execution                    │ │  │
│  │  │  - Workflow orchestration                         │ │  │
│  │  │  - Trigger management                             │ │  │
│  │  │  - Widget data                                    │ │  │
│  │  └──────────────────────────────────────────────────┘ │  │
│  │                                                          │  │
│  │  ┌──────────────────────────────────────────────────┐ │  │
│  │  │  Business Logic Layer                             │ │  │
│  │  │  ┌───────────┐  ┌──────────┐  ┌──────────────┐ │ │  │
│  │  │  │  Agents   │  │ Workflows │  │   Triggers   │ │ │  │
│  │  │  └───────────┘  └──────────┘  └──────────────┘ │ │  │
│  │  └──────────────────────────────────────────────────┘ │  │
│  │                                                          │  │
│  │  ┌──────────────────────────────────────────────────┐ │  │
│  │  │  Infrastructure Layer                             │ │  │
│  │  │  - Auto-discovery                                 │ │  │
│  │  │  - Health checks                                  │ │  │
│  │  │  - DynamicTriggerManager                          │ │  │
│  │  │  - WorkflowExecutor                               │ │  │
│  │  └──────────────────────────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────┘  │
│                             │                                │
│                             ▼                                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Clarity SDK (Python Package)             │  │
│  │  - Decorators (@agent, @workflow, @trigger_template) │  │
│  │  - Registries (AgentRegistry, WorkflowRegistry, etc.) │  │
│  │  - Executors (WorkflowExecutor, 4 execution modes)   │  │
│  │  - Context (AgentContext, WorkflowContext)           │  │
│  │  - Models (Pydantic validation)                      │  │
│  └──────────────────────────────────────────────────────┘  │
│                             │                                │
│                             ▼                                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           PostgreSQL Database                         │  │
│  │  - UserTriggerInstance                                │  │
│  │  - TriggerExecution                                   │  │
│  │  - WorkflowExecution                                  │  │
│  │  - UserIntegration                                    │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │          React Frontend (Port 3200)                   │  │
│  │  - Widget (small/large sizes)                         │  │
│  │  - Dashboard                                          │  │
│  │  - Trigger Manager                                    │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### Component Interaction Flow

1. **Startup Sequence**:
   ```
   1. Backend starts → loads config.py
   2. Database initialized → creates tables if needed
   3. Auto-discovery scans backend/agents, backend/workflows, backend/triggers
   4. Decorators register components into SDK registries
   5. DynamicTriggerManager loads user triggers from database
   6. APScheduler schedules jobs based on user configurations
   7. Health endpoint returns 200 OK → app is ready
   ```

2. **Trigger Execution Flow**:
   ```
   1. APScheduler fires job at configured time
   2. DynamicTriggerManager callback executes
   3. WorkflowExecutor.execute_workflow() called
   4. Agents execute in sequence/parallel/DAG based on execution_mode
   5. Results stored in WorkflowExecution table
   6. TriggerExecution record created
   7. UserTriggerInstance statistics updated (total_executions++)
   ```

---

## SDK Architecture

### Core Decorators

#### `@agent` Decorator

```python
# claritty_sdk/agent.py
def agent(**metadata):
    """
    Decorator that:
    1. Validates metadata against AgentMetadata schema
    2. Registers agent class in AgentRegistry
    3. Returns original class unmodified
    """
    def decorator(cls):
        # Validate with Pydantic
        agent_metadata = AgentMetadata(**metadata, agent_class=cls)
        # Register globally
        AgentRegistry.register_agent(agent_metadata)
        return cls
    return decorator
```

**Why this design?**
- Non-intrusive: Doesn't modify the original class
- Validation at decorator time: Catches errors early
- Global registry: Easy discovery and execution

#### `@workflow` Decorator

```python
# claritty_sdk/workflow.py
def workflow(**metadata):
    """
    Creates a WorkflowBuilder that collects @uses_agent decorators
    """
    def decorator(func):
        builder = WorkflowBuilder(**metadata, workflow_function=func)
        # Stores builder globally, collects steps from @uses_agent
        return builder
    return decorator
```

**Decorator Stacking**:
```python
@workflow(id="my-workflow")
@uses_agent("agent-1", output_key="step1")  # Executes bottom-up
@uses_agent("agent-2", input_from="step1", output_key="step2")
async def my_workflow(context):
    pass
```

The decorators execute bottom-up, so `@uses_agent` decorators accumulate steps on the `WorkflowBuilder`.

### Registry Pattern

```python
# claritty_sdk/registry.py
class AgentRegistry:
    _agents: Dict[str, AgentMetadata] = {}

    @classmethod
    def register_agent(cls, metadata: AgentMetadata):
        cls._agents[metadata.id] = metadata

    @classmethod
    def get_agent(cls, agent_id: str) -> Optional[Type[BaseAgent]]:
        return cls._agents.get(agent_id)?.agent_class
```

**Benefits**:
- Type-safe: Pydantic validation
- Thread-safe: Class methods with dict storage
- Queryable: List all agents, get by ID, filter by category

---

## Backend Architecture

### API Layer Structure

```
backend/main.py (745 lines)
├── Health & Widget Endpoints
│   ├── GET  /health
│   └── GET  /api/widget
├── Discovery Endpoints
│   ├── GET  /api/agents
│   ├── GET  /api/agents/{id}
│   ├── GET  /api/workflows
│   └── GET  /api/trigger-templates
├── Trigger Management
│   ├── GET    /api/my/triggers
│   ├── POST   /api/my/triggers
│   ├── PATCH  /api/my/triggers/{id}
│   └── DELETE /api/my/triggers/{id}
└── Execution Endpoints
    ├── POST /api/agents/{id}/execute
    ├── POST /api/workflows/{id}/execute
    └── GET  /api/workflows/executions/{id}
```

### Dependency Injection

FastAPI's dependency injection provides:

```python
# Get database session
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Get current user from headers
def get_current_user(
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None)
) -> str:
    # Priority 1: X-User-ID header (Clarity platform proxy)
    if x_user_id:
        return x_user_id
    # Priority 2: Bearer token (development/direct access)
    if authorization:
        return extract_user_from_token(authorization)
    raise HTTPException(status_code=401, detail="Authentication required")

# Use in endpoints
@app.get("/api/my/triggers")
async def list_user_triggers(
    user_id: str = Depends(get_current_user),  # Injected
    db: Session = Depends(get_db)  # Injected
):
    triggers = db.query(UserTriggerInstance).filter_by(user_id=user_id).all()
    return {"triggers": triggers}
```

---

## Frontend Architecture

### Component Hierarchy

```
frontend/src/
├── components/
│   ├── Layout.tsx                 # App shell with navigation
│   └── Widget.tsx                 # Two-size widget for marketplace
├── pages/
│   ├── Dashboard.tsx              # Agent/workflow monitoring
│   └── TriggerManager.tsx         # Trigger CRUD UI
├── lib/
│   ├── api.ts                     # Complete API client
│   └── utils.ts                   # Utility functions
└── App.tsx                        # Router + auth
```

### API Client Design

```typescript
// frontend/src/lib/api.ts
import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
});

// Interceptor: Add authentication headers
api.interceptors.request.use((config) => {
  // Priority 1: X-User-ID header (Clarity marketplace)
  const userId = localStorage.getItem('user_id');
  if (userId) {
    config.headers['X-User-ID'] = userId;
  }

  // Priority 2: Bearer token (development fallback)
  const token = localStorage.getItem('auth_token') || 'test-user';
  config.headers.Authorization = `Bearer ${token}`;

  return config;
});

// Type-safe API functions
export const getAgents = async (): Promise<Agent[]> => {
  const response = await api.get('/api/agents');
  return response.data.agents;
};

export const executeTrigger = async (
  triggerId: string,
  config: TriggerConfig
): Promise<TriggerInstance> => {
  const response = await api.post('/api/my/triggers', {
    template_id: triggerId,
    config
  });
  return response.data;
};
```

---

## Database Design

### Entity Relationship Diagram

```
┌────────────────────────┐
│  UserTriggerInstance   │
│  ────────────────────  │
│  id (PK)               │
│  user_id               │◄─────┐
│  template_id           │      │
│  name                  │      │
│  config (JSON)         │      │
│  enabled               │      │
│  total_executions      │      │
│  total_failures        │      │
│  last_triggered_at     │      │
└────────┬───────────────┘      │
         │                       │
         │ 1:N                   │
         ▼                       │
┌────────────────────────┐      │
│   TriggerExecution     │      │
│  ────────────────────  │      │
│  id (PK)               │      │
│  trigger_instance_id   │      │
│  workflow_execution_id │──┐   │
│  triggered_at          │  │   │
│  success               │  │   │
│  trigger_data (JSON)   │  │   │
└────────────────────────┘  │   │
                            │   │
         ┌──────────────────┘   │
         │ N:1                   │
         ▼                       │
┌────────────────────────┐      │
│  WorkflowExecution     │      │
│  ────────────────────  │      │
│  id (PK)               │      │
│  workflow_id           │      │
│  user_id               │──────┘
│  status                │
│  input_data (JSON)     │
│  output_data (JSON)    │
│  error_message         │
│  started_at            │
│  completed_at          │
│  duration_seconds      │
└────────────────────────┘

┌────────────────────────┐
│   UserIntegration      │
│  ────────────────────  │
│  id (PK)               │
│  user_id               │
│  service               │
│  credentials (JSON)    │ ◄── Encrypted at rest
│  is_active             │
└────────────────────────┘
```

### Indexing Strategy

```sql
-- Critical for query performance
CREATE INDEX idx_user_triggers_user_id ON user_trigger_instances(user_id);
CREATE INDEX idx_user_triggers_enabled ON user_trigger_instances(enabled);
CREATE INDEX idx_trigger_exec_trigger_id ON trigger_executions(trigger_instance_id);
CREATE INDEX idx_workflow_exec_user_id ON workflow_executions(user_id);
CREATE INDEX idx_workflow_exec_status ON workflow_executions(status);
CREATE INDEX idx_workflow_exec_started_at ON workflow_executions(started_at DESC);
```

---

## Auto-Discovery System

### How It Works

```python
# backend/infrastructure/discovery.py
def discover_and_register_components():
    """
    1. Scans backend/agents/, backend/workflows/, backend/triggers/
    2. Imports all .py files (except __init__.py and private files)
    3. Decorators execute on import → register components
    4. Returns counts for logging
    """

    backend_path = Path(__file__).parent.parent

    # Discover agents
    _discover_modules(backend_path / "agents", "backend.agents")

    # Discover workflows
    _discover_modules(backend_path / "workflows", "backend.workflows")

    # Discover triggers
    _discover_modules(backend_path / "triggers", "backend.triggers")
```

**Integration into Startup**:

```python
# backend/main.py
@app.on_event("startup")
async def startup_event():
    # Initialize database
    init_db()

    # Auto-discover and register all components
    from backend.infrastructure import discover_and_register_components
    discover_and_register_components()

    # Log registered components
    agents = AgentRegistry.list_agents()
    logger.info(f"✅ Registered {len(agents)} agents")
```

**Benefits**:
- Zero configuration: Just create files, they're auto-registered
- No manual __init__.py editing: Eliminates #1 DX pain point
- Error isolation: One bad module doesn't break entire startup
- Development velocity: Add new components without touching infrastructure

---

## Trigger Management System

### DynamicTriggerManager

```python
# claritty_sdk/trigger_manager.py
class DynamicTriggerManager:
    """
    Manages dynamic scheduling of user-configured triggers.

    Lifecycle:
    1. Start: Load all enabled triggers from database
    2. Register: Schedule each trigger with APScheduler
    3. Monitor: Handle trigger create/update/delete events
    4. Execute: Fire workflows at configured times
    5. Stop: Clean shutdown of scheduler
    """

    def __init__(self, db_session_factory, workflow_executor):
        self.scheduler = AsyncIOScheduler()
        self.db_factory = db_session_factory
        self.executor = workflow_executor
        self.active_jobs: Dict[str, Job] = {}

    async def start(self):
        """Load all enabled triggers and schedule them"""
        self.scheduler.start()
        db = self.db_factory()
        try:
            triggers = db.query(UserTriggerInstance).filter_by(enabled=True).all()
            for trigger in triggers:
                await self.register_trigger(
                    trigger.id,
                    trigger.user_id,
                    trigger.template_id,
                    trigger.config
                )
        finally:
            db.close()

    async def register_trigger(self, trigger_id, user_id, template_id, config):
        """Schedule a single trigger"""
        template = TriggerTemplateRegistry.get_template(template_id)

        if template.template_type == TriggerTemplateType.SCHEDULE_DAILY:
            time = config["time"]  # "09:00"
            timezone = config["timezone"]  # "America/New_York"

            job = self.scheduler.add_job(
                func=self._execute_trigger,
                trigger="cron",
                hour=int(time.split(":")[0]),
                minute=int(time.split(":")[1]),
                timezone=timezone,
                args=[trigger_id, user_id, template.workflow_id, config]
            )

            self.active_jobs[trigger_id] = job

    async def _execute_trigger(self, trigger_id, user_id, workflow_id, config):
        """Execute workflow when trigger fires"""
        result = await self.executor.execute_workflow(
            workflow_id=workflow_id,
            trigger_data=config,
            user_id=user_id
        )

        # Record execution in database
        # Update trigger statistics
        # ...
```

---

## Workflow Execution Engine

### Execution Modes

#### 1. Sequential Execution

```python
# Execute agents one at a time, passing outputs between steps
async def execute_sequential(workflow: WorkflowMetadata, context: WorkflowContext):
    for step in workflow.steps:
        agent_class = AgentRegistry.get_agent(step.agent_id)
        agent = agent_class()

        # Build agent input from previous outputs
        agent_input = {}
        if step.input_from:
            agent_input = context.outputs[step.input_from]

        # Execute agent
        result = await agent.execute(AgentContext(
            user_id=context.user_id,
            input_data=agent_input,
            integrations=context.integrations
        ))

        # Store output for next step
        context.outputs[step.output_key] = result.data
```

#### 2. Parallel Execution

```python
# Execute all agents simultaneously using asyncio.gather()
async def execute_parallel(workflow: WorkflowMetadata, context: WorkflowContext):
    tasks = []

    for step in workflow.steps:
        agent_class = AgentRegistry.get_agent(step.agent_id)
        agent = agent_class()

        tasks.append(agent.execute(AgentContext(
            user_id=context.user_id,
            input_data=context.trigger_data,
            integrations=context.integrations
        )))

    # Execute all agents concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Store all outputs
    for step, result in zip(workflow.steps, results):
        if isinstance(result, Exception):
            # Handle failure
            continue
        context.outputs[step.output_key] = result.data
```

#### 3. DAG Execution

```python
# Build dependency graph, execute agents when dependencies are met
async def execute_dag(workflow: WorkflowMetadata, context: WorkflowContext):
    # Build adjacency list
    graph = build_dependency_graph(workflow.steps)

    # Topological sort
    execution_order = topological_sort(graph)

    # Execute in dependency order
    for level in execution_order:
        # All steps in a level can run in parallel
        tasks = [execute_step(step, context) for step in level]
        await asyncio.gather(*tasks)
```

---

## Security Architecture

### Authentication

**Two-tier authentication**:

1. **Clarity Platform Proxy** (Production):
   ```
   User → Clarity Platform → X-User-ID header → Your App
   ```
   - Platform validates user session
   - Injects `X-User-ID` header
   - Your app trusts the header (running behind platform proxy)

2. **Bearer Token** (Development):
   ```
   User → Your App (Authorization: Bearer token)
   ```
   - For local development and testing
   - Implement JWT validation for production direct access

### Data Isolation

```python
# ✅ ALWAYS filter by user_id
triggers = db.query(UserTriggerInstance).filter(
    UserTriggerInstance.user_id == user_id
).all()

# ❌ NEVER query without user filter
triggers = db.query(UserTriggerInstance).all()  # Data leak!
```

### Credential Encryption

```python
# UserIntegration.credentials is JSON encrypted at rest
class UserIntegration(Base):
    credentials = Column(JSONB)  # Encrypted before storage

    def set_credentials(self, creds: dict):
        self.credentials = encrypt_json(creds)

    def get_credentials(self) -> dict:
        return decrypt_json(self.credentials)
```

---

## Widget-First Design

### The Fundamental Principle

Apps deployed to Clarity Marketplace are **widget-first**:

```
Traditional Web App:
User opens app URL → Full page loads

Widget-First App:
User sees widget on dashboard → Clicks for full app (optional)
```

### Implementation Requirements

**Backend must support 2 widget sizes**:

```python
@app.get("/api/widget")
async def get_widget_data(size: str = "large", user_id: str = Depends(get_current_user)):
    if size == "small":
        # Minimal data for quick glance
        return {
            "active_triggers": count_active_triggers(user_id),
            "success_rate": calculate_success_rate(user_id)
        }
    else:  # large
        # Detailed data with recent executions
        return {
            "active_triggers": count_active_triggers(user_id),
            "total_executions": count_executions(user_id),
            "success_rate": calculate_success_rate(user_id),
            "recent_executions": get_recent_executions(user_id, limit=5)
        }
```

**Frontend must render 2 widget sizes**:

```typescript
interface WidgetProps {
  size?: 'small' | 'large';
}

export default function Widget({ size = 'large' }: WidgetProps) {
  const { data } = useWidgetData(size);

  if (size === 'small') {
    return (
      <div className="w-[300px] h-[150px]">
        <div>Active: {data.active_triggers}</div>
        <div>Success: {data.success_rate}</div>
      </div>
    );
  }

  return (
    <div className="w-[600px] h-[400px]">
      {/* Full widget with charts, execution history, etc. */}
    </div>
  );
}
```

### Why Widget-First?

1. **Discovery**: Users browse marketplace, see widget previews
2. **Adoption**: Low barrier to entry - just add widget to dashboard
3. **Engagement**: Widget always visible, drives daily usage
4. **Conversion**: Users click for full app when they need advanced features

**Design Implications**:
- Widget must be useful standalone (not just a link to full app)
- Widget must update in real-time (polling or WebSocket)
- Widget must be visually appealing (drives adoption)
- Full app is for advanced features only

---

For complete usage examples, see [GUIDE.md](GUIDE.md)

For API reference, see [API.md](API.md)

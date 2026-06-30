# Customization Guide - Building Your Agentic App

Step-by-step guide to customize the seed template for your specific use case.

---

## Table of Contents

1. [Overview](#overview)
2. [Planning Your App](#planning-your-app)
3. [Step-by-Step Customization](#step-by-step-customization)
4. [Real-World Example: RedditSignals](#real-world-example-redditsignals)
5. [Validation & Testing](#validation--testing)
6. [Common Customization Patterns](#common-customization-patterns)

---

## Overview

The seed template comes with a **Smart Email Filter** example app. You'll replace this with your own application while keeping the infrastructure intact.

### What You'll Replace

✏️ **Must Customize**:
- Agents (`backend/agents/`)
- Workflows (`backend/workflows/`)
- Database models (`backend/models.py`)
- Widget endpoint logic (`backend/main.py`)
- Frontend UI (`frontend/src/`)

🔒 **Keep As-Is** (Infrastructure):
- Main.py structure (endpoints, startup, etc.)
- Configuration system (`backend/config.py`)
- Docker setup (`docker-compose.yml`, Dockerfiles)
- Database connection (`backend/database.py`)

---

## Planning Your App

### Step 1: Define Your Use Case

Ask yourself:

**What problem does my app solve?**
- Example: "Help crypto investors find trending coins on Reddit"

**What data does it process?**
- Example: "Reddit posts, mentions, sentiment"

**What actions does it take?**
- Example: "Analyze sentiment, generate buy/hold/avoid recommendations"

**Who are the users?**
- Example: "Crypto traders who want daily signals"

### Step 2: Design Your Agents

Identify **3-5 specialized agents** that work together:

**Example (Email Filter)**:
1. **EmailFetcherAgent** - Gets new emails from Gmail
2. **EmailAnalyzerAgent** - Analyzes importance using AI
3. **NotificationSenderAgent** - Sends alerts for important emails

**Example (Reddit Signals)**:
1. **RedditDiscoveryAgent** - Scans subreddits for coin mentions
2. **SmartSearchAgent** - Generates AI-powered search queries
3. **RecommendationEngineAgent** - Creates BUY/HOLD/AVOID signals

### Step 3: Design Your Workflow

Chain agents into a logical flow:

```
Trigger (e.g., daily at 9am)
  ↓
Agent 1: Fetch data
  ↓
Agent 2: Analyze data
  ↓
Agent 3: Take action
  ↓
Widget: Display results
```

### Step 4: Define Your Widget Data

What should users see in their dashboard?

**Small Widget** (quick glance):
- 1-3 key metrics
- Status indicator
- Last update time

**Large Widget** (detailed view):
- Multiple metrics
- Recent items/results
- Charts or visualizations
- Action buttons

---

## Step-by-Step Customization

### Phase 1: Backend - Agents

#### 1. Remove Example Agents

```bash
cd backend/agents
rm email_analyzer.py email_composer.py email_fetcher.py notification_sender.py task_analyzer.py
```

Keep `__init__.py` (required for module discovery).

#### 2. Create Your First Agent

Create `backend/agents/data_fetcher.py` (replace with your agent name):

```python
"""
Data Fetcher Agent
Fetches data from external source
"""

from claritty_sdk import agent, BaseAgent, AgentResult, AgentContext
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


@agent(
    id="data-fetcher",
    name="Data Fetcher",
    description="Fetches data from [YOUR SOURCE]",
    category="data",
    inputs={
        "query": {
            "type": "string",
            "description": "Search query or filter",
            "required": True
        },
        "limit": {
            "type": "integer",
            "description": "Maximum results to fetch",
            "required": False
        }
    },
    outputs={
        "data": {
            "type": "array",
            "description": "Fetched data items"
        },
        "count": {
            "type": "integer",
            "description": "Number of items fetched"
        }
    },
    integrations=[],  # Add if you need external APIs
    timeout=60
)
class DataFetcherAgent(BaseAgent):
    """
    Fetches data from [YOUR SOURCE].

    TODO: Describe what this agent does
    TODO: Document any prerequisites (API keys, etc.)
    """

    async def execute(self, context: AgentContext) -> AgentResult:
        """
        Fetch data based on query.
        """
        try:
            query = context.get_input("query")
            limit = context.get_input("limit", 100)

            context.log("info", f"Fetching data for query: {query}")

            # TODO: Implement your data fetching logic
            # Example:
            # data = await fetch_from_api(query, limit)

            # Placeholder data
            data = [
                {"id": 1, "title": "Example 1"},
                {"id": 2, "title": "Example 2"}
            ]

            context.log("info", f"Fetched {len(data)} items")

            return AgentResult(
                success=True,
                data={
                    "data": data,
                    "count": len(data)
                },
                metadata={
                    "agent_id": "data-fetcher",
                    "query": query
                }
            )

        except Exception as e:
            logger.error(f"Data fetch failed: {e}")
            return AgentResult(
                success=False,
                error=f"Fetch failed: {str(e)}"
            )
```

#### 3. Create Additional Agents

Repeat for each agent in your design:
- `backend/agents/data_analyzer.py`
- `backend/agents/action_executor.py`
- etc.

**Agent Naming Convention**:
- Use descriptive names: `reddit_discovery.py` not `agent1.py`
- One agent per file
- Agent ID should match filename: `reddit-discovery`

### Phase 2: Backend - Workflows

#### 1. Remove Example Workflows

```bash
cd backend/workflows
rm email_monitoring.py task_management.py
```

Keep `__init__.py`.

#### 2. Create Your Main Workflow

Create `backend/workflows/main_workflow.py`:

```python
"""
Main Workflow
Orchestrates agents to accomplish the app's goal
"""

from claritty_sdk import workflow, WorkflowContext, ExecutionMode
import logging

logger = logging.getLogger(__name__)


@workflow(
    id="main-workflow",
    name="Main Processing Workflow",
    description="Main workflow that processes data end-to-end",
    execution_mode=ExecutionMode.SEQUENTIAL
)
async def main_workflow(context: WorkflowContext):
    """
    Main workflow for [YOUR APP NAME].

    Steps:
    1. Fetch data (DataFetcherAgent)
    2. Analyze data (DataAnalyzerAgent)
    3. Take action (ActionExecutorAgent)
    4. Update widget data

    Triggered by:
    - Schedule (configured by user)
    - Manual execution
    - API call
    """
    context.log("info", "🚀 Starting main workflow")

    # Get configuration from trigger
    query = context.get_input("query", "default")

    # Step 1: Fetch data
    context.log("info", "Step 1: Fetching data...")

    from claritty_sdk import AgentRegistry, AgentContext as AC

    fetcher_agent_class = AgentRegistry.get_agent("data-fetcher")
    if not fetcher_agent_class:
        context.log("error", "DataFetcherAgent not found")
        return

    fetcher_agent = fetcher_agent_class()
    fetcher_context = AC(
        user_id=context.user_id,
        input_data={"query": query, "limit": 100},
        integrations=context.integrations,
        metadata=context.metadata,
        execution_id=f"{context.execution_id}_fetch"
    )

    fetch_result = await fetcher_agent.execute(fetcher_context)

    if not fetch_result.success:
        context.log("error", f"Failed to fetch data: {fetch_result.error}")
        return

    data = fetch_result.data.get("data", [])
    context.log("info", f"✅ Fetched {len(data)} items")

    # Step 2: Analyze data
    # TODO: Add your analysis agent
    context.log("info", "Step 2: Analyzing data...")
    # analysis_result = await analyze_agent.execute(...)

    # Step 3: Take action
    # TODO: Add your action agent
    context.log("info", "Step 3: Executing actions...")
    # action_result = await action_agent.execute(...)

    # Store results
    context.set_output("total_items", len(data))
    context.set_output("success", True)

    context.log("info", "✅ Workflow complete!")
```

### Phase 3: Backend - Database Models

#### 1. Update models.py

Edit `backend/models.py` to reflect your data:

```python
"""
Database models for [YOUR APP NAME]
"""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, JSON, Text
from datetime import datetime
import uuid
from backend.database import Base


# Remove example models (UserEmailCriteria, ProcessedEmail)
# Add your models:

class YourDataModel(Base):
    """
    Stores data specific to your app.

    TODO: Describe what this model stores
    """
    __tablename__ = "your_data"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)

    # Your fields
    title = Column(String, nullable=False)
    description = Column(Text)
    score = Column(Integer, default=0)
    data = Column(JSON)  # Store flexible JSON data

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<YourDataModel id={self.id} title={self.title}>"


class YourResult(Base):
    """
    Stores results/outputs from workflow executions.
    """
    __tablename__ = "your_results"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)

    # Results
    result_type = Column(String, index=True)  # "recommendation", "alert", etc.
    result_data = Column(JSON)
    confidence = Column(Integer)  # 0-100

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f"<YourResult id={self.id} type={self.result_type}>"


# Keep these models (required for platform):
# - UserTriggerInstance
# - TriggerExecution
# - UserIntegration
# - WorkflowExecution
```

### Phase 4: Backend - Widget Endpoint

#### 1. Update /api/widget in main.py

Edit `backend/main.py`, find the `get_widget_data` function (~line 107):

```python
@app.get("/api/widget")
async def get_widget_data(
    size: str = "large",
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    db: Session = Depends(get_db)
):
    """
    Widget data endpoint - REQUIRED by Clarity platform.
    """
    user_id = x_user_id if x_user_id else "test-user"

    # TODO: Replace with your app's data

    if size == "small":
        # Small widget: Quick glance metrics
        # Example for crypto signals:
        buy_count = db.query(models.YourResult).filter(
            models.YourResult.user_id == user_id,
            models.YourResult.result_type == "BUY"
        ).count()

        return {
            "buy_signals": buy_count,
            "status": "active",
            "last_update": "5 min ago"
        }

    else:  # large
        # Large widget: Detailed view
        recent_results = db.query(models.YourResult).filter(
            models.YourResult.user_id == user_id
        ).order_by(
            models.YourResult.created_at.desc()
        ).limit(5).all()

        return {
            "buy_signals": 3,
            "hold_signals": 12,
            "total_analyzed": 127,
            "recent_results": [
                {
                    "type": result.result_type,
                    "data": result.result_data,
                    "confidence": result.confidence
                }
                for result in recent_results
            ],
            "last_update": "5 min ago"
        }
```

### Phase 5: Frontend - UI Customization

#### 1. Update Dashboard Page

Edit `frontend/src/pages/Dashboard.tsx`:

```tsx
import { useEffect, useState } from 'react';
import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export default function Dashboard() {
  const [widgetData, setWidgetData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchWidgetData();
    // Refresh every 30 seconds
    const interval = setInterval(fetchWidgetData, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchWidgetData = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/widget?size=large`, {
        headers: {
          'X-User-ID': 'test-user'
        }
      });
      setWidgetData(response.data);
    } catch (error) {
      console.error('Failed to fetch widget data:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="p-8">Loading...</div>;
  }

  // TODO: Customize this UI for your app
  return (
    <div className="p-8">
      <h1 className="text-3xl font-bold mb-8">Your App Dashboard</h1>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        {/* Key Metrics */}
        <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow">
          <h3 className="text-sm text-gray-500 mb-2">Metric 1</h3>
          <p className="text-3xl font-bold">{widgetData?.buy_signals || 0}</p>
        </div>

        <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow">
          <h3 className="text-sm text-gray-500 mb-2">Metric 2</h3>
          <p className="text-3xl font-bold">{widgetData?.hold_signals || 0}</p>
        </div>

        <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow">
          <h3 className="text-sm text-gray-500 mb-2">Metric 3</h3>
          <p className="text-3xl font-bold">{widgetData?.total_analyzed || 0}</p>
        </div>
      </div>

      {/* Recent Results */}
      <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow">
        <h2 className="text-xl font-bold mb-4">Recent Results</h2>
        <div className="space-y-4">
          {widgetData?.recent_results?.map((result: any, index: number) => (
            <div key={index} className="border-b pb-4">
              <div className="flex justify-between">
                <span className="font-semibold">{result.type}</span>
                <span className="text-sm text-gray-500">
                  Confidence: {result.confidence}%
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
```

#### 2. Update Widget Page

Edit `frontend/src/pages/WidgetPage.tsx` for standalone widget display.

### Phase 6: Configuration

#### 1. Update .env.example

```bash
# ============================================================================
# REQUIRED: AI Configuration
# ============================================================================
ANTHROPIC_API_KEY=sk-ant-xxxxx

# ============================================================================
# OPTIONAL: Your App-Specific Settings
# ============================================================================

# TODO: Add your custom environment variables
# Example:
# REDDIT_CLIENT_ID=
# REDDIT_CLIENT_SECRET=
# SLACK_WEBHOOK_URL=
```

#### 2. Update app-config.json

Create/update `app-config.json` (defines user-configurable settings in Clarity Platform UI):

```json
{
  "app_id": "your-app-id",
  "name": "Your App Name",
  "description": "Brief description of what your app does",
  "category": "productivity",
  "config_fields": [
    {
      "key": "your_setting",
      "label": "Your Setting",
      "type": "text",
      "description": "Description of what this setting does",
      "required": false,
      "default": "default_value"
    }
  ]
}
```

---

## Real-World Example: RedditSignals

Let's walk through customizing the seed for a crypto Reddit signals app.

### Goal
Build an app that:
1. Scans Reddit for cryptocurrency mentions
2. Uses AI to analyze sentiment and find catalysts
3. Generates BUY/HOLD/AVOID recommendations
4. Displays signals in a dashboard widget

### Step 1: Agents Created

**`backend/agents/reddit_discovery.py`**
- Scans 6 crypto subreddits
- Counts mentions per coin
- Analyzes sentiment using Claude AI

**`backend/agents/smart_search.py`**
- Generates AI-powered search queries
- Searches Reddit for catalysts (upgrades, partnerships)
- Identifies risks (regulations, hacks)

**`backend/agents/recommendation_engine.py`**
- Combines discovery + search data
- Uses Claude AI to generate BUY/HOLD/AVOID
- Assigns confidence score (0-100)

### Step 2: Workflow Created

**`backend/workflows/daily_reddit_scan.py`**
```python
@workflow(id="daily-reddit-scan", ...)
async def daily_reddit_scan(context):
    # 1. Discovery: Scan subreddits
    discovery_data = await reddit_discovery_agent.execute(...)

    # 2. Search: Find catalysts for trending coins
    catalyst_data = await smart_search_agent.execute(...)

    # 3. Recommendations: Generate signals
    recommendations = await recommendation_engine.execute(...)

    # 4. Save to database
    for rec in recommendations:
        db.add(Recommendation(**rec))
```

### Step 3: Database Models

**`backend/models.py`**
```python
class RedditMention(Base):
    coin_symbol = Column(String)
    mention_count = Column(Integer)
    sentiment_score = Column(Float)

class Recommendation(Base):
    coin_symbol = Column(String)
    action = Column(String)  # BUY, HOLD, AVOID
    confidence = Column(Integer)
    reasoning = Column(Text)
```

### Step 4: Widget Endpoint

**`backend/main.py`**
```python
@app.get("/api/widget")
async def get_widget_data(...):
    if size == "small":
        return {
            "buy_signals": 3,
            "hold_signals": 12,
            "avoid_signals": 2
        }
    else:
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

### Step 5: Environment Variables

**`.env.example`**
```bash
ANTHROPIC_API_KEY=sk-ant-xxxxx
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
```

### Lessons Learned

❌ **Mistakes Made**:
1. Built in wrong directory initially (inside claritty-core)
2. Forgot to include frontend (built backend-only first)
3. Didn't understand seed should be customized, not replaced

✅ **What Worked**:
1. Using `@agent` and `@workflow` decorators (auto-discovery)
2. Following existing model patterns
3. Testing with docker-compose locally first

---

## Validation & Testing

### 1. Run Validation Script

```bash
python scripts/validate-app.py
```

Expected output:
```
🔍 Validating Clarity Platform App...

✅ Health endpoint responding
✅ Widget endpoint found
✅ Agents registered: 3
✅ Workflows registered: 1
✅ Docker builds successfully
✅ Database models defined
✅ Environment variables documented

🎉 All requirements met! Ready to deploy.
```

### 2. Test Locally

```bash
# Start all services
docker-compose up

# Test health
curl http://localhost:8000/health

# Test widget
curl http://localhost:8000/api/widget

# Test agent
curl -X POST http://localhost:8000/api/agents/your-agent-id/execute \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-user" \
  -d '{"your_input": "test"}'

# Test workflow
curl -X POST http://localhost:8000/api/workflows/your-workflow-id/execute \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-user"
```

### 3. GitHub CI Validation

Push to GitHub - CI will automatically:
- ✅ Build Docker containers
- ✅ Run validation script
- ✅ Test endpoints
- ✅ Run test suite

---

## Common Customization Patterns

### Pattern 1: Adding External API Integration

```python
@agent(
    id="api-fetcher",
    integrations=[{
        "service": "custom-api",
        "required": True,
        "auth_type": "api-key"
    }]
)
class APIFetcherAgent(BaseAgent):
    async def execute(self, context):
        api_key = context.get_integration("custom-api").get("api_key")
        # Use API key to fetch data
```

### Pattern 2: Scheduled Daily Execution

Users configure via Clarity Platform UI:
- Trigger type: Schedule
- Frequency: Daily
- Time: 09:00 AM
- Timezone: America/New_York

### Pattern 3: User-Specific Data

Always filter by `user_id`:
```python
user_data = db.query(YourModel).filter(
    YourModel.user_id == context.user_id
).all()
```

### Pattern 4: Real-Time Widget Updates

Widget automatically refreshes when data changes:
```python
# After workflow completes, data is saved
db.add(result)
db.commit()

# Widget endpoint fetches latest data
# Frontend polls every 30 seconds
```

---

## Next Steps

After customization:

1. ✅ Run validation: `python scripts/validate-app.py`
2. ✅ Test locally: `docker-compose up`
3. ✅ Push to GitHub
4. ✅ Deploy to Clarity Marketplace
5. ✅ Configure triggers in Clarity Platform UI
6. ✅ Monitor execution logs

**Need help?** See:
- `DEVELOPER_GUIDE.md` - Technical reference
- `ARCHITECTURE.md` - System design
- `FAQ.md` - Common questions
- GitHub Issues - Community support

---

**Happy building!** 🚀

# API Reference

Complete API documentation for the Clarity Agentic App backend.

## Base URL

```
http://localhost:8000  (Development)
https://your-app.clarity.ai  (Production)
```

## Authentication

All endpoints (except `/health`) require authentication via one of:

### Option 1: X-User-ID Header (Recommended for Clarity Platform)

```bash
curl -H "X-User-ID: user-123" http://localhost:8000/api/agents
```

### Option 2: Bearer Token (Development/Direct Access)

```bash
curl -H "Authorization: Bearer user-123" http://localhost:8000/api/agents
```

---

## Core Endpoints

### Health Check

Check if the application is running and healthy.

```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-02-18T10:30:00Z",
  "version": "1.0.0"
}
```

**Status Codes:**
- `200 OK` - Application is healthy
- `503 Service Unavailable` - Application is unhealthy (database down, etc.)

---

### Widget Data

Get data for Clarity dashboard widget (2 sizes).

```http
GET /api/widget?size={size}
```

**Parameters:**
- `size` (optional): `small` or `large` (default: `large`)

**Headers:**
- `X-User-ID` or `Authorization` (required)

**Response (size=small):**
```json
{
  "active_triggers": 5,
  "success_rate": "95%"
}
```

**Response (size=large):**
```json
{
  "active_triggers": 5,
  "total_executions": 42,
  "success_rate": 95.0,
  "recent_executions": [
    {
      "workflow_id": "task-review",
      "status": "completed",
      "started_at": "2026-02-18T10:30:00Z",
      "duration_seconds": 15
    },
    ...
  ]
}
```

---

## Discovery Endpoints

### List Agents

Get all registered agents with metadata.

```http
GET /api/agents
```

**Response:**
```json
{
  "agents": [
    {
      "id": "task-analyzer",
      "name": "Task Analyzer",
      "description": "Analyzes tasks and provides insights",
      "category": "productivity",
      "inputs": {
        "task_title": {"type": "string", "required": true},
        "task_description": {"type": "string", "required": true}
      },
      "outputs": {
        "priority": {"type": "string"},
        "estimated_time": {"type": "number"}
      },
      "integrations": []
    },
    ...
  ]
}
```

---

### Get Agent Details

Get detailed metadata for a specific agent.

```http
GET /api/agents/{agent_id}
```

**Parameters:**
- `agent_id` (path): Agent identifier

**Response:**
```json
{
  "id": "task-analyzer",
  "name": "Task Analyzer",
  "description": "Analyzes tasks and provides insights",
  "category": "productivity",
  "inputs": {
    "task_title": {
      "type": "string",
      "description": "Title of the task",
      "required": true
    },
    "task_description": {
      "type": "string",
      "description": "Detailed task description",
      "required": true
    }
  },
  "outputs": {
    "priority": {
      "type": "string",
      "description": "Priority level (low/medium/high/urgent)"
    },
    "estimated_time": {
      "type": "number",
      "description": "Estimated time in hours"
    }
  },
  "timeout": 30,
  "integrations": []
}
```

**Status Codes:**
- `200 OK` - Agent found
- `404 Not Found` - Agent doesn't exist

---

### List Workflows

Get all registered workflows.

```http
GET /api/workflows
```

**Response:**
```json
{
  "workflows": [
    {
      "id": "task-review-workflow",
      "name": "Task Review Workflow",
      "description": "Reviews tasks and sends summary",
      "execution_mode": "sequential",
      "steps": [
        {
          "agent_id": "task-analyzer",
          "output_key": "analysis"
        },
        {
          "agent_id": "email-composer",
          "output_key": "email"
        }
      ]
    },
    ...
  ]
}
```

---

### List Trigger Templates

Get all available trigger templates that users can instantiate.

```http
GET /api/trigger-templates
```

**Response:**
```json
{
  "templates": [
    {
      "id": "daily-task-review",
      "name": "Daily Task Review",
      "description": "Review tasks every day at your preferred time",
      "template_type": "schedule_daily",
      "workflow_id": "task-review-workflow",
      "category": "productivity",
      "config_fields": [
        {
          "key": "time",
          "label": "What time should this run?",
          "type": "time",
          "required": true,
          "default": "09:00"
        },
        {
          "key": "timezone",
          "label": "Your timezone",
          "type": "timezone",
          "required": true,
          "default": "America/New_York"
        }
      ],
      "max_instances_per_user": 5
    },
    ...
  ]
}
```

---

## Trigger Management Endpoints

### List User's Triggers

Get all trigger instances for the current user.

```http
GET /api/my/triggers
```

**Headers:**
- `X-User-ID` or `Authorization` (required)

**Response:**
```json
{
  "triggers": [
    {
      "id": "trigger-uuid",
      "template_id": "daily-task-review",
      "name": "My Morning Review",
      "config": {
        "time": "09:00",
        "timezone": "America/New_York"
      },
      "enabled": true,
      "created_at": "2026-02-01T00:00:00Z",
      "last_triggered_at": "2026-02-18T09:00:00Z",
      "total_executions": 42,
      "total_failures": 2
    },
    ...
  ]
}
```

---

### Create Trigger Instance

Create a new trigger instance from a template.

```http
POST /api/my/triggers
```

**Headers:**
- `X-User-ID` or `Authorization` (required)
- `Content-Type: application/json` (required)

**Request Body:**
```json
{
  "template_id": "daily-task-review",
  "name": "My Morning Review",
  "config": {
    "time": "09:00",
    "timezone": "America/New_York"
  }
}
```

**Response:**
```json
{
  "id": "trigger-uuid",
  "template_id": "daily-task-review",
  "name": "My Morning Review",
  "config": {
    "time": "09:00",
    "timezone": "America/New_York"
  },
  "enabled": true,
  "created_at": "2026-02-18T10:30:00Z"
}
```

**Status Codes:**
- `200 OK` - Trigger created successfully
- `400 Bad Request` - Invalid config or max instances exceeded
- `404 Not Found` - Template doesn't exist
- `401 Unauthorized` - Authentication required

---

### Update Trigger Instance

Update an existing trigger instance.

```http
PATCH /api/my/triggers/{trigger_id}
```

**Headers:**
- `X-User-ID` or `Authorization` (required)
- `Content-Type: application/json` (required)

**Parameters:**
- `trigger_id` (path): Trigger instance ID

**Request Body (all fields optional):**
```json
{
  "name": "Updated Name",
  "config": {
    "time": "10:00",
    "timezone": "America/Los_Angeles"
  },
  "enabled": false
}
```

**Response:**
```json
{
  "id": "trigger-uuid",
  "name": "Updated Name",
  "config": {
    "time": "10:00",
    "timezone": "America/Los_Angeles"
  },
  "enabled": false,
  "updated_at": "2026-02-18T10:35:00Z"
}
```

**Status Codes:**
- `200 OK` - Trigger updated successfully
- `404 Not Found` - Trigger doesn't exist or doesn't belong to user
- `401 Unauthorized` - Authentication required

---

### Delete Trigger Instance

Delete a trigger instance.

```http
DELETE /api/my/triggers/{trigger_id}
```

**Headers:**
- `X-User-ID` or `Authorization` (required)

**Parameters:**
- `trigger_id` (path): Trigger instance ID

**Response:**
```json
{
  "message": "Trigger deleted successfully"
}
```

**Status Codes:**
- `200 OK` - Trigger deleted successfully
- `404 Not Found` - Trigger doesn't exist or doesn't belong to user
- `401 Unauthorized` - Authentication required

---

## Execution Endpoints

### Execute Agent

Execute a single agent with provided input data.

```http
POST /api/agents/{agent_id}/execute
```

**Headers:**
- `X-User-ID` or `Authorization` (required)
- `Content-Type: application/json` (required)

**Parameters:**
- `agent_id` (path): Agent identifier

**Request Body:**
```json
{
  "task_title": "Prepare presentation",
  "task_description": "Create slides for quarterly review"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "priority": "high",
    "estimated_time": 2.5,
    "insights": "This is a strategic task requiring executive attention"
  },
  "error": null,
  "metadata": {
    "execution_time": 1.2
  }
}
```

**Status Codes:**
- `200 OK` - Agent executed successfully (check `success` field for result)
- `404 Not Found` - Agent doesn't exist
- `500 Internal Server Error` - Agent execution failed
- `401 Unauthorized` - Authentication required

---

### Execute Workflow

Execute a complete workflow immediately.

```http
POST /api/workflows/{workflow_id}/execute
```

**Headers:**
- `X-User-ID` or `Authorization` (required)
- `Content-Type: application/json` (required)

**Parameters:**
- `workflow_id` (path): Workflow identifier

**Request Body (optional):**
```json
{
  "input_data": "Optional workflow input"
}
```

**Response:**
```json
{
  "execution_id": "execution-uuid",
  "workflow_id": "task-review-workflow",
  "status": "completed",
  "success": true,
  "outputs": {
    "analysis": { /* agent 1 output */ },
    "email": { /* agent 2 output */ }
  },
  "error": null,
  "duration_seconds": 15
}
```

**Status Codes:**
- `200 OK` - Workflow executed (check `status` and `success` for result)
- `404 Not Found` - Workflow doesn't exist
- `500 Internal Server Error` - Workflow execution failed
- `401 Unauthorized` - Authentication required

---

### Get Workflow Execution

Get status and results of a workflow execution.

```http
GET /api/workflows/executions/{execution_id}
```

**Headers:**
- `X-User-ID` or `Authorization` (required)

**Parameters:**
- `execution_id` (path): Execution ID

**Response:**
```json
{
  "id": "execution-uuid",
  "workflow_id": "task-review-workflow",
  "status": "completed",
  "input_data": { /* workflow inputs */ },
  "output_data": { /* workflow outputs */ },
  "error_message": null,
  "started_at": "2026-02-18T10:30:00Z",
  "completed_at": "2026-02-18T10:30:15Z",
  "duration_seconds": 15
}
```

**Status Codes:**
- `200 OK` - Execution found
- `404 Not Found` - Execution doesn't exist or doesn't belong to user
- `401 Unauthorized` - Authentication required

---

## Interactive Documentation

FastAPI automatically generates interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
  - Try out API calls directly in the browser
  - See request/response schemas
  - Authentication testing

- **ReDoc**: http://localhost:8000/redoc
  - Beautiful alternative documentation format
  - Better for reading and sharing

---

## Rate Limiting

**Current**: No rate limiting (development)

**Production Recommendations**:
- 100 requests/minute per user for general endpoints
- 10 agent executions/minute per user
- 50 workflow executions/hour per user
- Implement using middleware (e.g., SlowAPI)

---

## Error Responses

All error responses follow this format:

```json
{
  "detail": "Human-readable error message"
}
```

**Common Status Codes**:
- `400 Bad Request` - Invalid input data
- `401 Unauthorized` - Missing or invalid authentication
- `403 Forbidden` - User doesn't have permission
- `404 Not Found` - Resource doesn't exist
- `422 Unprocessable Entity` - Validation error
- `500 Internal Server Error` - Server-side error

**Validation Error Example**:
```json
{
  "detail": [
    {
      "loc": ["body", "template_id"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

## WebSocket Support

**Status**: Not yet implemented

**Planned**:
- Real-time workflow execution updates
- Live trigger execution notifications
- Dashboard activity feed

---

## Versioning

**Current**: No API versioning (v1 assumed)

**Future**: API versioning will follow this pattern:
- `GET /v1/api/agents` - Version 1
- `GET /v2/api/agents` - Version 2 (breaking changes)

---

For complete usage examples, see [GUIDE.md](GUIDE.md)

For architecture details, see [ARCHITECTURE.md](ARCHITECTURE.md)

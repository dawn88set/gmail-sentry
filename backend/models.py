"""
Database models for the Clarity app.

Models:
- Task: the example app's domain entity (a simple to-do item)
- UserIntegration: user-connected integrations (OAuth/API keys) — optional
- WorkflowExecution: workflow execution history

Generated apps REPLACE `Task` with their own domain models. Keep
`UserIntegration` + `WorkflowExecution` (used by the SDK runtime + the optional
integrations layer). Every model that holds user data MUST have a `user_id`
column and every query MUST filter by it (multi-tenancy).

Note: trigger instances + their execution audit are owned by the Claritty
platform now (not the app); see /internal/* dispatch endpoints in main.py.
"""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, JSON, Text
from datetime import datetime
import uuid
from backend.database import Base


class Task(Base):
    """
    The seed's example domain entity: a simple, AI-prioritized to-do item.

    This is intentionally generic — replace it with your app's real models.
    It demonstrates the full pattern: user-scoped CRUD, an agent that enriches
    it (priority + suggested action), and a widget that summarizes it.
    """
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)  # multi-tenancy key

    title = Column(String, nullable=False)
    notes = Column(Text)

    # Set by the "prioritize-task" agent (Claude) on create; safe default so
    # the app works even when the LLM proxy isn't configured (local/CI).
    priority = Column(String, default="medium", index=True)  # low|medium|high|urgent
    suggested_action = Column(Text)  # one short AI-suggested next step

    done = Column(Boolean, default=False, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "notes": self.notes,
            "priority": self.priority,
            "suggested_action": self.suggested_action,
            "done": self.done,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<Task id={self.id} priority={self.priority} done={self.done}>"


class UserIntegration(Base):
    """
    User-connected integrations (OAuth, API keys). Optional — the default app
    needs none. Kept because the integrations layer + workflow runtime use it.
    """
    __tablename__ = "user_integrations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    service = Column(String, nullable=False, index=True)  # slack, google-sheets, etc
    auth_type = Column(String)  # oauth, api-key, basic
    credentials = Column(JSON)  # Encrypted credentials
    scopes = Column(JSON)  # OAuth scopes
    connected_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    is_active = Column(Boolean, default=True, index=True)

    def __repr__(self):
        return f"<UserIntegration user={self.user_id} service={self.service}>"


class WorkflowExecution(Base):
    """
    Workflow execution history. Records every workflow run with inputs,
    outputs, and timing (written by the workflow execute endpoint).
    """
    __tablename__ = "workflow_executions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id = Column(String, nullable=False, index=True)
    trigger_id = Column(String, index=True)
    user_id = Column(String, index=True)

    status = Column(String, index=True)  # pending, running, completed, failed
    input_data = Column(JSON)
    output_data = Column(JSON)
    error_message = Column(Text)

    started_at = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime)
    duration_seconds = Column(Integer)

    def __repr__(self):
        return f"<WorkflowExecution id={self.id} workflow={self.workflow_id} status={self.status}>"

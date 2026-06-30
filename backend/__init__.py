"""
Clarity Agentic App Backend

This package contains the FastAPI backend application with agents, workflows, and triggers.
All components are automatically registered on import.
"""

# Import submodules for registration
from backend import agents
from backend import workflows
from backend import triggers

__all__ = [
    "agents",
    "workflows",
    "triggers"
]

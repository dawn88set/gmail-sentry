"""
Backend Infrastructure

This package contains core infrastructure code that users should not need to modify.
All health checks, discovery, and platform integration logic lives here.
"""

from backend.infrastructure.discovery import discover_and_register_components
from backend.infrastructure.health import router as health_router

__all__ = ["discover_and_register_components", "health_router"]

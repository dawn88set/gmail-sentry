"""
Configuration loader for Clarity Agentic Apps

Loads configuration from two sources with clear separation:
1. .env.platform (platform-managed, high priority) - Infrastructure settings
2. .env (user-configured via Clarity Platform UI) - App-specific settings

The platform manages all infrastructure concerns (database, ports, security, AI keys).
Users only configure app-specific behavior through the Clarity Platform UI.
"""

import os
from typing import Any, Optional
from pydantic import BaseModel, Field, validator
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# Load platform config first (higher priority - overrides everything)
load_dotenv('.env.platform', override=True)
# Then load user config (lower priority - only for app-specific settings)
load_dotenv('.env', override=False)


class PlatformConfig(BaseModel):
    """
    Platform-managed configuration (read-only for app)

    These settings are automatically managed by Clarity Platform.
    Apps should NEVER write to .env.platform.
    """

    # ============================================================================
    # INFRASTRUCTURE
    # ============================================================================

    database_url: str = Field(..., description="PostgreSQL connection string")
    redis_url: Optional[str] = Field(None, description="Redis connection string")
    port: int = Field(8000, description="Server port (dynamically assigned)")
    host: str = Field('0.0.0.0', description="Server host")

    # ============================================================================
    # PLATFORM INTEGRATION
    # ============================================================================

    clarity_app_id: str = Field(..., description="Unique app identifier in platform")
    clarity_platform_url: str = Field(..., description="Clarity Platform URL")
    clarity_webhook_secret: Optional[str] = Field(None, description="Webhook validation secret")

    # ============================================================================
    # AI PROVIDER (model defaults only)
    # The seed holds NO provider API key. LLM access goes through the Claritty
    # platform proxy, authenticated by CLARITTY_AUTH_TOKEN + CLARITTY_PLATFORM_URL
    # which the platform injects at deploy (see claritty_sdk.llm.get_llm_client).
    # ============================================================================

    ai_model: str = Field('claude-3-5-sonnet-20241022', description="Default Claude model")
    ai_timeout_seconds: int = Field(60, description="AI API request timeout")
    ai_max_tokens: int = Field(4096, description="Maximum tokens per request")
    ai_temperature: float = Field(1.0, description="Default AI temperature")

    # ============================================================================
    # SECURITY
    # ============================================================================

    jwt_secret: str = Field(..., description="JWT token signing secret")
    session_secret: str = Field(..., description="Session cookie secret")

    # ============================================================================
    # CORS
    # ============================================================================

    frontend_url: str = Field(..., description="Frontend URL for CORS")
    cors_allowed_origins: str = Field(..., description="Comma-separated allowed origins")

    # ============================================================================
    # MONITORING & LOGGING
    # ============================================================================

    log_level: str = Field('INFO', description="Logging level")
    log_format: str = Field('json', description="Log format (json or text)")
    sentry_dsn: Optional[str] = Field(None, description="Sentry error tracking DSN")
    sentry_environment: str = Field('production', description="Sentry environment tag")

    # ============================================================================
    # RESOURCE LIMITS (Platform-enforced)
    # ============================================================================

    workflow_max_concurrent: int = Field(5, description="Max concurrent workflows")
    workflow_execution_timeout_seconds: int = Field(300, description="Workflow timeout")
    trigger_max_per_user: int = Field(10, description="Max triggers per user")
    database_pool_size: int = Field(20, description="Database connection pool size")

    # ============================================================================
    # COST MANAGEMENT (Platform-enforced)
    # ============================================================================

    ai_daily_token_budget: int = Field(1000000, description="Daily token budget")
    ai_monthly_token_budget: int = Field(30000000, description="Monthly token budget")
    ai_track_usage: bool = Field(True, description="Track AI usage per user")

    @validator('port')
    def validate_port(cls, v):
        if v < 1 or v > 65535:
            raise ValueError("port must be between 1 and 65535")
        return v

    @validator('log_level')
    def validate_log_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v.upper()

    class Config:
        env_prefix = ''  # No prefix, direct env var names


class AppConfig(BaseModel):
    """
    User-configured app-specific settings

    These settings are configured by users through the Clarity Platform UI.
    They control app behavior, not infrastructure.

    Values must match field definitions in app-config.json
    """

    # ============================================================================
    # AI CONFIGURATION (from app-config.json)
    # ============================================================================

    ai_operation_mode: str = Field(
        'balanced',
        description="AI operation mode: fast, balanced, or quality"
    )
    ai_response_temperature: int = Field(
        70,
        description="AI creativity level (0-100)"
    )

    # ============================================================================
    # WORKFLOW EXECUTION (from app-config.json)
    # ============================================================================

    workflow_retry_failed: bool = Field(
        True,
        description="Auto-retry failed workflows"
    )
    workflow_max_retries: int = Field(
        2,
        description="Maximum retry attempts"
    )
    workflow_parallel_limit: int = Field(
        3,
        description="Max parallel workflows per user"
    )

    # ============================================================================
    # NOTIFICATIONS (from app-config.json)
    # ============================================================================

    notify_on_workflow_complete: bool = Field(
        True,
        description="Notify when workflows complete"
    )
    notify_on_workflow_failure: bool = Field(
        True,
        description="Notify when workflows fail"
    )
    notification_email: Optional[str] = Field(
        None,
        description="Email for notifications"
    )

    # ============================================================================
    # EXTERNAL INTEGRATIONS (from app-config.json)
    # ============================================================================

    enable_slack_integration: bool = Field(
        False,
        description="Enable Slack notifications"
    )
    slack_webhook_url: Optional[str] = Field(
        None,
        description="Slack webhook URL"
    )

    # ============================================================================
    # ADVANCED SETTINGS (from app-config.json)
    # ============================================================================

    debug_mode: bool = Field(
        False,
        description="Enable verbose logging"
    )
    custom_metadata: Optional[dict] = Field(
        None,
        description="Custom metadata JSON"
    )

    @validator('ai_operation_mode')
    def validate_operation_mode(cls, v):
        valid_modes = ['fast', 'balanced', 'quality']
        if v not in valid_modes:
            raise ValueError(f"ai_operation_mode must be one of {valid_modes}")
        return v

    @validator('ai_response_temperature')
    def validate_temperature(cls, v):
        if v < 0 or v > 100:
            raise ValueError("ai_response_temperature must be between 0 and 100")
        return v

    @validator('workflow_max_retries')
    def validate_max_retries(cls, v):
        if v < 0 or v > 5:
            raise ValueError("workflow_max_retries must be between 0 and 5")
        return v

    @validator('workflow_parallel_limit')
    def validate_parallel_limit(cls, v):
        if v < 1 or v > 10:
            raise ValueError("workflow_parallel_limit must be between 1 and 10")
        return v

    @validator('notification_email')
    def validate_email(cls, v):
        if v and '@' not in v:
            raise ValueError("notification_email must be a valid email")
        return v

    @validator('slack_webhook_url')
    def validate_slack_webhook(cls, v):
        if v and not v.startswith('https://hooks.slack.com/'):
            raise ValueError("slack_webhook_url must be a valid Slack webhook")
        return v

    class Config:
        env_prefix = ''  # No prefix, matches app-config.json keys exactly


# ============================================================================
# GLOBAL CONFIGURATION INSTANCES
# ============================================================================

# Smart defaults for local development
DEFAULT_DATABASE_URL = 'postgresql://clarity_user:clarity_password@localhost:5432/clarity_agentic_app'
DEFAULT_JWT_SECRET = 'development-jwt-secret-change-in-production'
DEFAULT_SESSION_SECRET = 'development-session-secret-change-in-production'
DEFAULT_FRONTEND_URL = 'http://localhost:3200'
DEFAULT_CORS_ORIGINS = 'http://localhost:3200,http://localhost:3000'

try:
    platform_config = PlatformConfig(
        # Required with smart defaults
        database_url=os.getenv('DATABASE_URL', DEFAULT_DATABASE_URL),
        clarity_app_id=os.getenv('CLARITY_APP_ID', 'local-dev-app'),
        clarity_platform_url=os.getenv('CLARITY_PLATFORM_URL', 'http://localhost:4000'),
        jwt_secret=os.getenv('JWT_SECRET', DEFAULT_JWT_SECRET),
        session_secret=os.getenv('SESSION_SECRET', DEFAULT_SESSION_SECRET),
        frontend_url=os.getenv('FRONTEND_URL', DEFAULT_FRONTEND_URL),
        cors_allowed_origins=os.getenv('CORS_ALLOWED_ORIGINS', DEFAULT_CORS_ORIGINS),

        # Optional fields with defaults
        redis_url=os.getenv('REDIS_URL'),
        port=int(os.getenv('PORT', '8000')),
        host=os.getenv('HOST', '0.0.0.0'),
        ai_model=os.getenv('AI_MODEL', 'claude-3-5-sonnet-20241022'),
        ai_timeout_seconds=int(os.getenv('AI_TIMEOUT_SECONDS', '60')),
        ai_max_tokens=int(os.getenv('AI_MAX_TOKENS', '4096')),
        ai_temperature=float(os.getenv('AI_TEMPERATURE', '1.0')),
        log_level=os.getenv('LOG_LEVEL', 'INFO'),
        log_format=os.getenv('LOG_FORMAT', 'json'),
        sentry_dsn=os.getenv('SENTRY_DSN'),
        sentry_environment=os.getenv('SENTRY_ENVIRONMENT', 'development'),
        workflow_max_concurrent=int(os.getenv('WORKFLOW_MAX_CONCURRENT', '5')),
        workflow_execution_timeout_seconds=int(os.getenv('WORKFLOW_EXECUTION_TIMEOUT_SECONDS', '300')),
        trigger_max_per_user=int(os.getenv('TRIGGER_MAX_PER_USER', '10')),
        database_pool_size=int(os.getenv('DATABASE_POOL_SIZE', '20')),
        ai_daily_token_budget=int(os.getenv('AI_DAILY_TOKEN_BUDGET', '1000000')),
        ai_monthly_token_budget=int(os.getenv('AI_MONTHLY_TOKEN_BUDGET', '30000000')),
        ai_track_usage=os.getenv('AI_TRACK_USAGE', 'true').lower() == 'true',
    )
    logger.info("✅ Platform configuration loaded successfully")
except Exception as e:
    logger.error(f"❌ Failed to load platform configuration: {e}")
    raise

try:
    app_config = AppConfig(
        ai_operation_mode=os.getenv('AI_OPERATION_MODE', 'balanced'),
        ai_response_temperature=int(os.getenv('AI_RESPONSE_TEMPERATURE', '70')),
        workflow_retry_failed=os.getenv('WORKFLOW_RETRY_FAILED', 'true').lower() == 'true',
        workflow_max_retries=int(os.getenv('WORKFLOW_MAX_RETRIES', '2')),
        workflow_parallel_limit=int(os.getenv('WORKFLOW_PARALLEL_LIMIT', '3')),
        notify_on_workflow_complete=os.getenv('NOTIFY_ON_WORKFLOW_COMPLETE', 'true').lower() == 'true',
        notify_on_workflow_failure=os.getenv('NOTIFY_ON_WORKFLOW_FAILURE', 'true').lower() == 'true',
        notification_email=os.getenv('NOTIFICATION_EMAIL'),
        enable_slack_integration=os.getenv('ENABLE_SLACK_INTEGRATION', 'false').lower() == 'true',
        slack_webhook_url=os.getenv('SLACK_WEBHOOK_URL'),
        debug_mode=os.getenv('DEBUG_MODE', 'false').lower() == 'true',
        custom_metadata=None,  # TODO: Parse JSON if provided
    )
    logger.info("✅ App configuration loaded successfully")
except Exception as e:
    logger.warning(f"⚠️  Failed to load app configuration (using defaults): {e}")
    # Use defaults if app config fails to load
    app_config = AppConfig()


# ============================================================================
# PUBLIC API
# ============================================================================

def get_platform_config() -> PlatformConfig:
    """
    Get platform-managed configuration (infrastructure settings).

    Use this for:
    - Database connections
    - AI API keys
    - Security secrets
    - Resource limits

    Returns:
        PlatformConfig: Platform-managed settings
    """
    return platform_config


def get_app_config() -> AppConfig:
    """
    Get user-configured app settings (app behavior).

    Use this for:
    - AI operation preferences
    - Workflow behavior
    - Notification settings
    - Integration toggles

    Returns:
        AppConfig: User-configured settings
    """
    return app_config


def reload_app_config():
    """
    Reload app configuration (when user changes settings via Clarity Platform UI).

    Only reloads app-specific config, not platform config.
    Platform config is immutable during app lifetime.
    """
    global app_config

    try:
        # Reload .env file
        load_dotenv('.env', override=True)

        # Create new AppConfig instance
        app_config = AppConfig(
            ai_operation_mode=os.getenv('AI_OPERATION_MODE', 'balanced'),
            ai_response_temperature=int(os.getenv('AI_RESPONSE_TEMPERATURE', '70')),
            workflow_retry_failed=os.getenv('WORKFLOW_RETRY_FAILED', 'true').lower() == 'true',
            workflow_max_retries=int(os.getenv('WORKFLOW_MAX_RETRIES', '2')),
            workflow_parallel_limit=int(os.getenv('WORKFLOW_PARALLEL_LIMIT', '3')),
            notify_on_workflow_complete=os.getenv('NOTIFY_ON_WORKFLOW_COMPLETE', 'true').lower() == 'true',
            notify_on_workflow_failure=os.getenv('NOTIFY_ON_WORKFLOW_FAILURE', 'true').lower() == 'true',
            notification_email=os.getenv('NOTIFICATION_EMAIL'),
            enable_slack_integration=os.getenv('ENABLE_SLACK_INTEGRATION', 'false').lower() == 'true',
            slack_webhook_url=os.getenv('SLACK_WEBHOOK_URL'),
            debug_mode=os.getenv('DEBUG_MODE', 'false').lower() == 'true',
            custom_metadata=None,
        )

        logger.info("✅ App configuration reloaded successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to reload app configuration: {e}")
        return False


def get_ai_temperature_from_percentage(percentage: int) -> float:
    """
    Convert user-friendly percentage (0-100) to Claude API temperature (0.0-1.0).

    Args:
        percentage: User preference from 0-100

    Returns:
        float: Temperature for Claude API (0.0-1.0)
    """
    if percentage < 0 or percentage > 100:
        raise ValueError("percentage must be between 0 and 100")

    return percentage / 100.0


def get_model_from_operation_mode(mode: str) -> str:
    """
    Map user-friendly operation mode to Claude model.

    Args:
        mode: "fast", "balanced", or "quality"

    Returns:
        str: Claude model identifier
    """
    mode_to_model = {
        'fast': 'claude-3-haiku-20240307',
        'balanced': 'claude-3-5-sonnet-20241022',
        'quality': 'claude-3-opus-20240229',
    }

    return mode_to_model.get(mode, platform_config.ai_model)


# ============================================================================
# CONFIGURATION VALIDATION
# ============================================================================

def validate_configuration():
    """
    Validate that all required configuration is present and valid.

    Called on app startup to ensure proper configuration.

    Raises:
        ValueError: If configuration is invalid or missing required fields
    """
    errors = []
    warnings = []

    # No provider API key is required — LLM access is via the platform proxy
    # (CLARITTY_AUTH_TOKEN + CLARITTY_PLATFORM_URL, injected by the platform).

    # Warn about development defaults (not errors)
    if platform_config.jwt_secret == DEFAULT_JWT_SECRET:
        warnings.append("Using development JWT_SECRET - set a secure secret in production")
    if platform_config.session_secret == DEFAULT_SESSION_SECRET:
        warnings.append("Using development SESSION_SECRET - set a secure secret in production")
    if platform_config.clarity_app_id == 'local-dev-app':
        warnings.append("Using local development app ID - platform will assign real ID in production")

    # Validate app config ranges
    if app_config.ai_response_temperature < 0 or app_config.ai_response_temperature > 100:
        errors.append("AI_RESPONSE_TEMPERATURE must be between 0 and 100")
    if app_config.workflow_max_retries < 0:
        errors.append("WORKFLOW_MAX_RETRIES must be >= 0")

    # Log warnings (non-fatal)
    if warnings:
        logger.warning("Configuration warnings (safe for development):")
        for warning in warnings:
            logger.warning(f"  ⚠️  {warning}")

    # Check errors (fatal)
    if errors:
        error_message = "Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        logger.error(error_message)
        raise ValueError(error_message)

    logger.info("✅ Configuration validation passed")


# Validate on module import
try:
    validate_configuration()
except ValueError as e:
    logger.error(f"❌ Configuration validation failed: {e}")
    # Don't raise in production, allow app to start with defaults
    if os.getenv('ENV', 'production') == 'development':
        raise

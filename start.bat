@echo off
REM Clarity Agentic App - One-Command Startup Script (Windows)
REM This script handles all setup and startup steps automatically

setlocal enabledelayedexpansion

echo.
echo ==============================================================
echo   Clarity Agentic App - Starting...
echo ==============================================================
echo.

REM ============================================================================
REM STEP 1: Check Docker
REM ============================================================================

echo [1/4] Checking Docker...
echo.

where docker >nul 2>nul
if %errorlevel% neq 0 (
    echo ERROR: Docker is not installed
    echo Please install Docker Desktop from https://www.docker.com/products/docker-desktop
    pause
    exit /b 1
)

docker info >nul 2>nul
if %errorlevel% neq 0 (
    echo ERROR: Docker daemon is not running
    echo Please start Docker Desktop and try again
    pause
    exit /b 1
)

echo SUCCESS: Docker is running
echo.

REM ============================================================================
REM STEP 2: Check Environment Configuration
REM ============================================================================

echo [2/4] Checking environment configuration...
echo.

if not exist ".env" (
    echo WARNING: No .env file found - copying from .env.example
    copy .env.example .env >nul
    echo SUCCESS: Created .env file
    echo.
    echo IMPORTANT: You need to add your Anthropic API key
    echo    Edit .env and set ANTHROPIC_API_KEY=your-key-here
    echo    Get your key at: https://console.anthropic.com/
    echo.
    pause
)

REM Read .env file and check for API key
set "API_KEY_FOUND=0"
for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
    if "%%a"=="ANTHROPIC_API_KEY" (
        set "API_KEY=%%b"
        if not "!API_KEY!"=="" if not "!API_KEY!"=="sk-ant-xxxxx" (
            set "API_KEY_FOUND=1"
        )
    )
)

if !API_KEY_FOUND!==0 (
    echo ERROR: ANTHROPIC_API_KEY is not configured
    echo.
    echo Please edit .env and add your Anthropic API key:
    echo   ANTHROPIC_API_KEY=your-actual-key-here
    echo.
    echo Get your key at: https://console.anthropic.com/
    pause
    exit /b 1
)

echo SUCCESS: Environment configured
echo.

REM ============================================================================
REM STEP 3: Start Services
REM ============================================================================

echo [3/4] Starting Docker services...
echo.

docker-compose up -d
if %errorlevel% neq 0 (
    echo ERROR: Failed to start services
    pause
    exit /b 1
)

echo SUCCESS: Services started
echo.

REM ============================================================================
REM STEP 4: Wait for Services to be Healthy
REM ============================================================================

echo [4/4] Waiting for services to be ready...
echo.

REM Wait for PostgreSQL
echo Waiting for PostgreSQL...
set /a max_attempts=30
set /a attempt=0

:wait_postgres
docker-compose exec -T postgres pg_isready -U clarity_user -d clarity_agentic_app >nul 2>nul
if %errorlevel% equ 0 goto postgres_ready
set /a attempt+=1
if !attempt! geq !max_attempts! (
    echo ERROR: PostgreSQL failed to start
    echo Check logs with: docker-compose logs postgres
    pause
    exit /b 1
)
timeout /t 1 /nobreak >nul
goto wait_postgres

:postgres_ready
echo SUCCESS: PostgreSQL is ready
echo.

REM Wait for Backend
echo Waiting for Backend...
set /a attempt=0

:wait_backend
curl -s http://localhost:8000/health >nul 2>nul
if %errorlevel% equ 0 goto backend_ready
set /a attempt+=1
if !attempt! geq !max_attempts! (
    echo ERROR: Backend failed to start
    echo Check logs with: docker-compose logs backend
    pause
    exit /b 1
)
timeout /t 1 /nobreak >nul
goto wait_backend

:backend_ready
echo SUCCESS: Backend is ready
echo.

REM Wait for Frontend
echo Waiting for Frontend...
set /a attempt=0

:wait_frontend
curl -s http://localhost:3200 >nul 2>nul
if %errorlevel% equ 0 goto frontend_ready
set /a attempt+=1
if !attempt! geq !max_attempts! (
    echo ERROR: Frontend failed to start
    echo Check logs with: docker-compose logs frontend
    pause
    exit /b 1
)
timeout /t 1 /nobreak >nul
goto wait_frontend

:frontend_ready
echo SUCCESS: Frontend is ready
echo.

REM ============================================================================
REM SUCCESS - Show Information
REM ============================================================================

echo ==============================================================
echo.
echo   SUCCESS: Clarity Agentic App is running!
echo.
echo ==============================================================
echo.
echo ACCESS YOUR APP:
echo.
echo   Frontend (UI):        http://localhost:3200
echo   Backend (API):        http://localhost:8000
echo   API Documentation:    http://localhost:8000/docs
echo.
echo USEFUL COMMANDS:
echo.
echo   View logs:            docker-compose logs -f
echo   Stop services:        docker-compose down
echo   Restart services:     docker-compose restart
echo.
echo DOCUMENTATION:
echo.
echo   README.md                      Complete guide and architecture
echo   CLAUDE.md                      Developer guide (for AI assistants)
echo   SUBMISSION_REQUIREMENTS.md     Marketplace submission checklist
echo.
echo Happy coding!
echo.
pause

#!/usr/bin/env python3
"""
Clarity Platform App Validator

Validates that an agentic app meets all Clarity Platform requirements
before deployment. Run this locally before pushing to production.

Usage:
    python scripts/validate-app.py

Exit codes:
    0 = All requirements met
    1 = Critical requirements failed
    2 = Recommended requirements failed (warnings only)
"""

import sys
import os
import requests
import subprocess
import json
from pathlib import Path
from typing import List, Tuple, Dict, Any

# ANSI color codes for pretty output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
BOLD = '\033[1m'
RESET = '\033[0m'


class ValidationResult:
    """Stores validation check results"""

    def __init__(self):
        self.critical_passed = []
        self.critical_failed = []
        self.recommended_passed = []
        self.recommended_failed = []
        self.warnings = []

    def add_critical_pass(self, message: str):
        self.critical_passed.append(message)

    def add_critical_fail(self, message: str, fix: str = None):
        self.critical_failed.append((message, fix))

    def add_recommended_pass(self, message: str):
        self.recommended_passed.append(message)

    def add_recommended_fail(self, message: str, fix: str = None):
        self.recommended_failed.append((message, fix))

    def add_warning(self, message: str):
        self.warnings.append(message)

    def has_critical_failures(self) -> bool:
        return len(self.critical_failed) > 0

    def has_recommended_failures(self) -> bool:
        return len(self.recommended_failed) > 0


class AppValidator:
    """Validates Clarity Platform app requirements"""

    def __init__(self, base_dir: Path = None):
        self.base_dir = base_dir or Path.cwd()
        self.backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")
        self.result = ValidationResult()

    def validate_all(self) -> ValidationResult:
        """Run all validation checks"""
        print(f"{BLUE}{BOLD}🔍 Validating Clarity Platform App...{RESET}\n")

        # Critical requirements
        print(f"{BOLD}Critical Requirements:{RESET}")
        self.check_health_endpoint()
        self.check_widget_endpoint()
        self.check_agents_registered()
        self.check_workflows_registered()
        self.check_docker_configuration()
        self.check_environment_variables()

        # Recommended requirements
        print(f"\n{BOLD}Recommended Requirements:{RESET}")
        self.check_database_models()
        self.check_tests()
        self.check_documentation()

        # Summary
        self.print_summary()

        return self.result

    def check_health_endpoint(self):
        """Check /health endpoint exists and returns 200"""
        try:
            response = requests.get(f"{self.backend_url}/health", timeout=5)
            if response.status_code == 200:
                self.result.add_critical_pass("Health endpoint responding")
                print(f"  {GREEN}✅ Health endpoint responding{RESET}")
            else:
                self.result.add_critical_fail(
                    "Health endpoint returned non-200 status",
                    "Ensure GET /health endpoint returns 200 OK in backend/main.py"
                )
                print(f"  {RED}❌ Health endpoint returned {response.status_code}{RESET}")
        except requests.exceptions.RequestException as e:
            self.result.add_critical_fail(
                "Health endpoint not accessible",
                "Start the backend with 'docker-compose up' and ensure /health endpoint exists"
            )
            print(f"  {RED}❌ Health endpoint not accessible{RESET}")
            print(f"     Error: {str(e)}")

    def check_widget_endpoint(self):
        """Check /api/widget endpoint exists and returns valid data"""
        try:
            # Test small widget
            response_small = requests.get(
                f"{self.backend_url}/api/widget?size=small",
                headers={"X-User-ID": "test-user"},
                timeout=5
            )

            # Test large widget
            response_large = requests.get(
                f"{self.backend_url}/api/widget?size=large",
                headers={"X-User-ID": "test-user"},
                timeout=5
            )

            if response_small.status_code == 200 and response_large.status_code == 200:
                # Verify JSON response
                small_data = response_small.json()
                large_data = response_large.json()

                if isinstance(small_data, dict) and isinstance(large_data, dict):
                    self.result.add_critical_pass("Widget endpoint found and returning valid data")
                    print(f"  {GREEN}✅ Widget endpoint found (small & large){RESET}")
                else:
                    self.result.add_critical_fail(
                        "Widget endpoint not returning valid JSON",
                        "Ensure /api/widget returns JSON dict, not string or array"
                    )
                    print(f"  {RED}❌ Widget endpoint not returning valid JSON{RESET}")
            else:
                self.result.add_critical_fail(
                    "Widget endpoint not responding correctly",
                    "Implement GET /api/widget endpoint in backend/main.py (see DEVELOPER_GUIDE.md)"
                )
                print(f"  {RED}❌ Widget endpoint not found{RESET}")

        except requests.exceptions.RequestException as e:
            self.result.add_critical_fail(
                "Widget endpoint not accessible",
                "Implement GET /api/widget endpoint in backend/main.py"
            )
            print(f"  {RED}❌ Widget endpoint not accessible{RESET}")
        except json.JSONDecodeError:
            self.result.add_critical_fail(
                "Widget endpoint not returning JSON",
                "Ensure /api/widget returns valid JSON"
            )
            print(f"  {RED}❌ Widget endpoint not returning JSON{RESET}")

    def check_agents_registered(self):
        """Check at least 1 agent is registered"""
        try:
            response = requests.get(f"{self.backend_url}/api/agents", timeout=5)
            if response.status_code == 200:
                data = response.json()
                agents = data.get("agents", [])

                if len(agents) > 0:
                    self.result.add_critical_pass(f"Agents registered: {len(agents)}")
                    print(f"  {GREEN}✅ Agents registered: {len(agents)}{RESET}")
                    for agent in agents[:5]:  # Show first 5
                        print(f"     - {agent.get('id')} ({agent.get('name')})")
                    if len(agents) > 5:
                        print(f"     ... and {len(agents) - 5} more")
                else:
                    self.result.add_critical_fail(
                        "No agents registered",
                        "Create at least 1 agent in backend/agents/ using @agent decorator"
                    )
                    print(f"  {RED}❌ No agents registered{RESET}")
            else:
                self.result.add_critical_fail(
                    "Agents endpoint not responding",
                    "Check backend/main.py includes agent discovery"
                )
                print(f"  {RED}❌ Agents endpoint returned {response.status_code}{RESET}")

        except requests.exceptions.RequestException:
            self.result.add_critical_fail(
                "Cannot access agents endpoint",
                "Start backend and ensure /api/agents endpoint exists"
            )
            print(f"  {RED}❌ Cannot access agents endpoint{RESET}")

    def check_workflows_registered(self):
        """Check at least 1 workflow is registered"""
        try:
            response = requests.get(f"{self.backend_url}/api/workflows", timeout=5)
            if response.status_code == 200:
                data = response.json()
                workflows = data.get("workflows", [])

                if len(workflows) > 0:
                    self.result.add_critical_pass(f"Workflows registered: {len(workflows)}")
                    print(f"  {GREEN}✅ Workflows registered: {len(workflows)}{RESET}")
                    for workflow in workflows[:5]:
                        print(f"     - {workflow.get('id')} ({workflow.get('name')})")
                    if len(workflows) > 5:
                        print(f"     ... and {len(workflows) - 5} more")
                else:
                    self.result.add_critical_fail(
                        "No workflows registered",
                        "Create at least 1 workflow in backend/workflows/ using @workflow decorator"
                    )
                    print(f"  {RED}❌ No workflows registered{RESET}")
            else:
                self.result.add_critical_fail(
                    "Workflows endpoint not responding",
                    "Check backend/main.py includes workflow discovery"
                )
                print(f"  {RED}❌ Workflows endpoint returned {response.status_code}{RESET}")

        except requests.exceptions.RequestException:
            self.result.add_critical_fail(
                "Cannot access workflows endpoint",
                "Start backend and ensure /api/workflows endpoint exists"
            )
            print(f"  {RED}❌ Cannot access workflows endpoint{RESET}")

    def check_docker_configuration(self):
        """Check Docker configuration is valid"""
        docker_compose_file = self.base_dir / "docker-compose.yml"

        if not docker_compose_file.exists():
            self.result.add_critical_fail(
                "docker-compose.yml not found",
                "Create docker-compose.yml in project root"
            )
            print(f"  {RED}❌ docker-compose.yml not found{RESET}")
            return

        # The seed builds a SINGLE multi-stage Dockerfile at the project root
        # (frontend build stage + Python backend, served by nginx+supervisord).
        # Older apps used separate backend/ + frontend/ Dockerfiles — accept either.
        root_dockerfile = self.base_dir / "Dockerfile"
        backend_dockerfile = self.base_dir / "backend" / "Dockerfile"
        frontend_dockerfile = self.base_dir / "frontend" / "Dockerfile"

        has_root = root_dockerfile.exists()
        has_split = backend_dockerfile.exists() and frontend_dockerfile.exists()

        if not has_root and not has_split:
            self.result.add_critical_fail(
                "No Dockerfile found",
                "Add a root Dockerfile (single multi-stage build) or "
                "backend/Dockerfile + frontend/Dockerfile",
            )
            print(f"  {RED}❌ No Dockerfile found (root, or backend+frontend){RESET}")
            return

        # Try building (optional, can be slow)
        # For now, just check files exist
        self.result.add_critical_pass("Docker configuration found")
        print(f"  {GREEN}✅ Docker configuration found{RESET}")

        # Optionally, try building
        if os.getenv("VALIDATE_DOCKER_BUILD") == "true":
            print(f"     Building Docker images (this may take a while)...")
            try:
                result = subprocess.run(
                    ["docker-compose", "build"],
                    cwd=self.base_dir,
                    capture_output=True,
                    timeout=300
                )
                if result.returncode == 0:
                    print(f"     {GREEN}✅ Docker build successful{RESET}")
                else:
                    self.result.add_warning("Docker build failed (non-critical)")
                    print(f"     {YELLOW}⚠️  Docker build had warnings{RESET}")
            except subprocess.TimeoutExpired:
                self.result.add_warning("Docker build timed out")
                print(f"     {YELLOW}⚠️  Docker build timed out{RESET}")
            except Exception as e:
                self.result.add_warning(f"Could not test Docker build: {str(e)}")
                print(f"     {YELLOW}⚠️  Could not test Docker build{RESET}")

    def check_environment_variables(self):
        """Check .env.example documents all required variables"""
        env_example_file = self.base_dir / ".env.example"

        if not env_example_file.exists():
            self.result.add_critical_fail(
                ".env.example not found",
                "Create .env.example documenting all required environment variables"
            )
            print(f"  {RED}❌ .env.example not found{RESET}")
            return

        # Read file
        env_content = env_example_file.read_text()

        # No provider API keys are required — AI runs through the platform LLM
        # proxy (CLARITTY_AUTH_TOKEN + CLARITTY_PLATFORM_URL, injected at deploy).
        required_vars = []
        missing_vars = []

        for var in required_vars:
            if var not in env_content:
                missing_vars.append(var)

        if missing_vars:
            self.result.add_critical_fail(
                f"Missing required env vars in .env.example: {', '.join(missing_vars)}",
                "Add required environment variables to .env.example"
            )
            print(f"  {RED}❌ Missing required env vars: {', '.join(missing_vars)}{RESET}")
        else:
            self.result.add_critical_pass("Environment variables documented")
            print(f"  {GREEN}✅ Environment variables documented{RESET}")

    def check_database_models(self):
        """Check database models are defined"""
        models_file = self.base_dir / "backend" / "models.py"

        if not models_file.exists():
            self.result.add_recommended_fail(
                "backend/models.py not found",
                "Create database models in backend/models.py"
            )
            print(f"  {YELLOW}⚠️  backend/models.py not found{RESET}")
            return

        # Read models file
        models_content = models_file.read_text()

        # Check for at least one model
        if "class " in models_content and "Base" in models_content:
            # Count models (rough estimate)
            model_count = models_content.count("class ") - models_content.count("class Meta")
            self.result.add_recommended_pass(f"Database models defined: ~{model_count}")
            print(f"  {GREEN}✅ Database models defined: ~{model_count}{RESET}")
        else:
            self.result.add_recommended_fail(
                "No database models found in backend/models.py",
                "Define SQLAlchemy models for your app's data"
            )
            print(f"  {YELLOW}⚠️  No database models found{RESET}")

    def check_tests(self):
        """Check if tests exist and can run"""
        tests_dir = self.base_dir / "backend" / "tests"

        if not tests_dir.exists():
            self.result.add_recommended_fail(
                "backend/tests/ directory not found",
                "Create tests in backend/tests/ directory"
            )
            print(f"  {YELLOW}⚠️  No tests directory found{RESET}")
            return

        # Count test files
        test_files = list(tests_dir.glob("test_*.py"))

        if len(test_files) == 0:
            self.result.add_recommended_fail(
                "No test files found",
                "Create test files (test_*.py) in backend/tests/"
            )
            print(f"  {YELLOW}⚠️  No test files found{RESET}")
        else:
            self.result.add_recommended_pass(f"Test files found: {len(test_files)}")
            print(f"  {GREEN}✅ Test files found: {len(test_files)}{RESET}")

            # Optionally run tests
            if os.getenv("RUN_TESTS") == "true":
                print(f"     Running tests...")
                try:
                    result = subprocess.run(
                        ["docker-compose", "exec", "-T", "backend", "pytest"],
                        cwd=self.base_dir,
                        capture_output=True,
                        timeout=60
                    )
                    if result.returncode == 0:
                        print(f"     {GREEN}✅ Tests passed{RESET}")
                    else:
                        print(f"     {YELLOW}⚠️  Some tests failed{RESET}")
                except Exception as e:
                    print(f"     {YELLOW}⚠️  Could not run tests: {str(e)}{RESET}")

    def check_documentation(self):
        """Check if README and other docs exist"""
        readme_file = self.base_dir / "README.md"

        if not readme_file.exists():
            self.result.add_recommended_fail(
                "README.md not found",
                "Create README.md explaining what your app does"
            )
            print(f"  {YELLOW}⚠️  README.md not found{RESET}")
        else:
            readme_content = readme_file.read_text()
            if len(readme_content) < 100:
                self.result.add_recommended_fail(
                    "README.md is too short",
                    "Add more documentation about your app"
                )
                print(f"  {YELLOW}⚠️  README.md is very short{RESET}")
            else:
                self.result.add_recommended_pass("Documentation found")
                print(f"  {GREEN}✅ Documentation found{RESET}")

    def print_summary(self):
        """Print validation summary"""
        print(f"\n{BOLD}{'='*60}{RESET}")
        print(f"{BOLD}Validation Summary{RESET}")
        print(f"{BOLD}{'='*60}{RESET}\n")

        # Critical requirements
        print(f"{BOLD}Critical Requirements:{RESET}")
        print(f"  {GREEN}✅ Passed: {len(self.result.critical_passed)}{RESET}")
        if self.result.critical_failed:
            print(f"  {RED}❌ Failed: {len(self.result.critical_failed)}{RESET}")
            for message, fix in self.result.critical_failed:
                print(f"     - {message}")
                if fix:
                    print(f"       {BLUE}Fix: {fix}{RESET}")

        # Recommended requirements
        print(f"\n{BOLD}Recommended Requirements:{RESET}")
        print(f"  {GREEN}✅ Passed: {len(self.result.recommended_passed)}{RESET}")
        if self.result.recommended_failed:
            print(f"  {YELLOW}⚠️  Failed: {len(self.result.recommended_failed)}{RESET}")
            for message, fix in self.result.recommended_failed:
                print(f"     - {message}")
                if fix:
                    print(f"       {BLUE}Suggestion: {fix}{RESET}")

        # Warnings
        if self.result.warnings:
            print(f"\n{BOLD}Warnings:{RESET}")
            for warning in self.result.warnings:
                print(f"  {YELLOW}⚠️  {warning}{RESET}")

        # Final verdict
        print(f"\n{BOLD}{'='*60}{RESET}")
        if self.result.has_critical_failures():
            print(f"{RED}{BOLD}❌ VALIDATION FAILED{RESET}")
            print(f"{RED}Fix critical issues before deploying to Clarity Platform.{RESET}")
            print(f"\n{BLUE}See REQUIREMENTS.md for details on each requirement.{RESET}")
        elif self.result.has_recommended_failures():
            print(f"{YELLOW}{BOLD}⚠️  VALIDATION PASSED WITH WARNINGS{RESET}")
            print(f"{YELLOW}App meets critical requirements but has recommendations.{RESET}")
            print(f"{GREEN}You can deploy, but consider addressing warnings.{RESET}")
        else:
            print(f"{GREEN}{BOLD}🎉 ALL REQUIREMENTS MET!{RESET}")
            print(f"{GREEN}Your app is ready to deploy to Clarity Platform!{RESET}")

        print(f"{BOLD}{'='*60}{RESET}\n")


def main():
    """Main entry point"""
    # Change to project root (parent of scripts/)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    # Parse arguments
    import argparse
    parser = argparse.ArgumentParser(description="Validate Clarity Platform app requirements")
    parser.add_argument("--build", action="store_true", help="Also test Docker build (slow)")
    parser.add_argument("--test", action="store_true", help="Also run test suite")
    args = parser.parse_args()

    # Set environment variables for optional checks
    if args.build:
        os.environ["VALIDATE_DOCKER_BUILD"] = "true"
    if args.test:
        os.environ["RUN_TESTS"] = "true"

    # Run validation
    validator = AppValidator(base_dir=project_root)
    result = validator.validate_all()

    # Exit with appropriate code
    if result.has_critical_failures():
        sys.exit(1)
    elif result.has_recommended_failures():
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()

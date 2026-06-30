#!/usr/bin/env bash
#
# Local "run now" for the app's intelligence.
#
# There is NO local scheduler — SCHEDULE triggers only fire on the Claritty
# platform (it POSTs /internal/run-due-triggers). This script is the LOCAL manual
# trigger: it calls POST /api/workflows/<id>/execute, which runs through the SAME
# execution path (the v2 manifest WorkflowEngine) the platform uses for scheduled
# runs — so a local run never diverges from how the app is managed when hosted.
#
# Usage:
#   scripts/run-now.sh <workflow-id> [base-url] [user-id]
#   scripts/run-now.sh lead-digest
#
# Intelligence behavior locally:
#   - With the LLM proxy configured (CLARITTY_PLATFORM_URL + CLARITTY_AUTH_TOKEN),
#     the REAL agent runs. Add CLARITTY_FAKE_CREDS_GMAIL='{"access_token":"..."}'
#     (etc.) to exercise integrations without OAuth.
#   - Without the proxy, the agent's fallback(ctx) runs (a no-AI, schema-valid
#     result) so the value path is still exercised. The fallback NEVER runs on the
#     platform, so it does not affect hosted behavior.
set -euo pipefail

WF="${1:?usage: run-now.sh <workflow-id> [base-url] [user-id]}"
BASE="${2:-http://127.0.0.1:8000}"
USER_ID="${3:-dev-user}"

curl -sS -X POST "$BASE/api/workflows/$WF/execute" \
  -H "Content-Type: application/json" \
  -H "X-User-ID: $USER_ID" \
  -d "{\"user_id\":\"$USER_ID\"}" | python3 -m json.tool

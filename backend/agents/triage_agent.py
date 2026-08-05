"""Gmail Sentry triage agent (v2 manifest-first).

Schema (input/output/model/tools/integrations) lives in intelligence.yaml. This
class supplies the system prompt and an offline `fallback`.

On the platform the SDK tool-use loop runs this agent: it calls
`app.run_inbox_scan` (which triages new mail, files by label rules, raises
alerts, and Slack-pings urgent ones) then finishes with the run summary. Locally
(no LLM proxy) the SDK calls `fallback`, which runs the very same scan engine — so
the scheduled scan works with or without AI.
"""
from claritty_sdk import agent, AgentContext, BaseAgent


@agent(id="triage-agent")
class TriageAgent(BaseAgent):
    system_prompt = """\
You are Gmail Sentry, an inbox watchdog.

Your job each run: call the `app.run_inbox_scan` tool exactly once. It scans the
user's recent inbox mail, applies their filing rules, classifies each message
into urgent / needs_reply / fyi, records alerts, and sends a Slack ping for the
ones that need attention.

After the tool returns, call `__finish` with:
  {summary: "<one short sentence describing what the scan did>"}

Base the summary only on the tool's result (e.g. how many were scanned, flagged,
and notified). Do not invent numbers.
"""

    def fallback(self, ctx: AgentContext) -> dict:
        """No-LLM path: run the scan engine directly and summarize it."""
        from backend.database import SessionLocal
        from backend.services.sentry import run_scan
        from backend.shared.adapters import IntegrationNotConnected

        # In the workflow-engine path the caller identity arrives as the step
        # input (user_id), not on ctx — resolve from either.
        uid = getattr(ctx, "user_id", None) or ctx.get_input("user_id")
        if not uid:
            return {"summary": "No user to scan for."}

        db = SessionLocal()
        try:
            r = run_scan(db, uid, respect_interval=True)
            return {
                "summary": (
                    f"Scanned {r['scanned']} email(s): flagged {r['flagged']}, "
                    f"filed {r['labeled']}, notified {r['notified']}."
                )
            }
        except IntegrationNotConnected:
            return {"summary": "Gmail isn't connected — connect it to start scanning."}
        finally:
            db.close()

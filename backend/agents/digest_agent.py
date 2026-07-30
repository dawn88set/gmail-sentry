"""Gmail Sentry digest agent (v2 manifest-first).

Schema (input/output/model/tools/integrations) lives in intelligence.yaml. This
class supplies the system prompt and an offline `fallback`.

On the platform the SDK tool-use loop runs this agent: it calls `app.send_digest`
(which builds the grouped inbox report and fans it out to every configured
channel) then finishes with a one-line summary. Locally (no LLM proxy) the SDK
calls `fallback`, which runs the very same digest directly — so the scheduled
report works with or without AI.
"""
from claritty_sdk import agent, AgentContext, BaseAgent


@agent(id="digest-agent")
class DigestAgent(BaseAgent):
    system_prompt = """\
You are Gmail Sentry's daily reporter.

Your job each run: call the `app.send_digest` tool exactly once. It gathers the
user's still-open alerts, groups them into urgent / to-reply, and sends one report
to every channel the user configured. When the inbox is calm it sends nothing.

After the tool returns, call `__finish` with:
  {summary: "<one short sentence describing what was sent>"}

Base the summary only on the tool's result (whether it sent, and to which
channels). Do not invent anything.
"""

    def fallback(self, ctx: AgentContext) -> dict:
        """No-LLM path: build + send the digest directly and summarize it."""
        from backend.database import SessionLocal
        from backend.services.digest import run_digest

        uid = getattr(ctx, "user_id", None) or ctx.get_input("user_id")
        if not uid:
            return {"summary": "No user to report for."}

        db = SessionLocal()
        try:
            r = run_digest(db, uid)
            if not r.get("sent"):
                return {"summary": "Inbox is calm — no report needed."}
            ok = [c["channel"] for c in r.get("channels", []) if c.get("ok")]
            return {"summary": f"Sent your inbox report to {', '.join(ok) or 'no channels'}."}
        finally:
            db.close()

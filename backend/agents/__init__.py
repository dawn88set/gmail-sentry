"""
Agents Package (v2 manifest-first)

Agents are DECLARED in intelligence.yaml#agents (schema lives there). An agent is a
system PROMPT, not an execute() method — the SDK's tool-use loop runs it.

Preferred: a zero-Python custom agent — set promptFile in intelligence.yaml and write
the prompt at backend/custom/agents/<id>/prompt.md (no file here at all).

Only when you need a before/after hook or an offline fallback, add a handler
class here and point intelligence.yaml `handler:` at it:

    from claritty_sdk import agent, AgentContext, BaseAgent

    @agent(id="my-agent")                 # id ONLY; schema is in intelligence.yaml
    class MyAgent(BaseAgent):
        system_prompt = "...call tools by id, then __finish with the output..."
        def fallback(self, ctx: AgentContext) -> dict:
            return {...}                   # no-LLM local path

NEVER define execute()/return AgentResult — the v2 runtime rejects that at boot.
Files here are auto-discovered on startup.
"""

# No imports needed - auto-discovery handles it!
__all__ = []

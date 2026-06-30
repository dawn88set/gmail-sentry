"""
Simple example demonstrating the Clarity SDK (v2, manifest-first)

This example shows:
1. Binding an agent class to an `app.yaml#agents[id=...]` entry with `@agent`
2. Binding a tool function with `@tool`
3. Where workflows + triggers live now (intelligence.yaml, NOT decorators)

In v2 the manifest (`intelligence.yaml` / `app.yaml`) is the single source of
truth for schema, model, tools, integrations, workflows, and triggers. Python
only carries behavior: an agent's `system_prompt` (the runtime drives the
Anthropic tool-use loop) and tool functions. There is no `execute()` method, no
`AgentResult`, and no decorator registry — the runtime loads handlers from the
manifest's `handler:` fields.
"""

from claritty_sdk import agent, tool, BaseAgent, ToolCtx


# ============================================
# 1. Bind an agent (behavior = a system prompt)
# ============================================
# The manifest declares this agent's id/model/tools/input/output:
#
#   agents:
#     - id: hello-world
#       source: custom
#       handler: tests.examples.simple_agent_example:HelloWorldAgent
#       tools: [format.greeting]
#       input:  { name: { type: string, required: true } }
#       output: { greeting: { type: string, required: true } }
#
@agent(id="hello-world")
class HelloWorldAgent(BaseAgent):
    system_prompt = (
        "You greet the user. Call format.greeting with their name to build a "
        "nicely formatted greeting, then call __finish with {greeting: <the "
        "formatted text>}."
    )

    def fallback(self, ctx) -> dict:
        """No-LLM local path: build the greeting directly."""
        name = (ctx.get_input("name") if hasattr(ctx, "get_input") else None) or "World"
        return {"greeting": f"🎉 Hello, {name}! 🎉"}


# ============================================
# 2. Bind a tool (a plain function)
# ============================================
@tool(id="format.greeting")
def format_greeting(input: dict, ctx: ToolCtx) -> dict:
    name = input.get("name", "World")
    return {"greeting": f"🎉 Hello, {name}! 🎉"}


# ============================================
# 3. Workflows + triggers live in the manifest
# ============================================
# Instead of @workflow / @trigger_template decorators, declare them in
# intelligence.yaml:
#
#   workflows:
#     - id: greeting-workflow
#       inputs: { name: { type: string, required: true } }
#       steps:
#         - id: greet
#           agent: hello-world
#           input: { name: "${input.name}" }
#       outputs: { greeting: "${steps.greet.output.greeting}" }
#
#   triggers:
#     - id: daily-greeting
#       type: SCHEDULE
#       workflow: greeting-workflow
#       supportedSchedules: [DAILY]
#       configFields:
#         - { key: time, type: time, required: true, default: "09:00" }
#         - { key: timezone, type: timezone, required: true }

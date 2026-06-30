"""Example agent — v2 (manifest-first) shape.

Compare to the v1 file this replaces: that one carried the full schema
in the ``@agent(...)`` kwargs and implemented ``async def execute(self,
context) -> AgentResult`` that hand-rolled an LLM call and a
``json.loads``.

In v2 the decorator is a pure binder: id only. The schema (input,
output, model, tools, integrations, timeout) lives in
``intelligence.yaml#agents``. The class supplies ``system_prompt`` (or a
Markdown prompt loaded by the catalog renderer) and optional
``before(ctx)`` / ``after(ctx, output)`` hooks; the SDK's
``claritty_sdk.runtime.tool_loop.run_agent`` drives the Anthropic
tool-use loop and validates the final output against the manifest's
``output:`` schema before returning it.
"""

from claritty_sdk import agent, AgentContext, BaseAgent


@agent(id="example-agent")
class ExampleAgent(BaseAgent):
    system_prompt = """\
You are a friendly greeting bot.

When invoked, you receive `{name: string}`. Call the `app.echo` tool
with a greeting message, then call `__finish` with
`{greeting: <the greeting>}`. Do not invent extra fields.
"""

    def fallback(self, ctx: AgentContext) -> dict:
        """Deterministic, no-AI result used when the LLM proxy is unconfigured.

        The SDK calls this (instead of running the model) when neither
        CLARITTY_PLATFORM_URL nor CLARITTY_LLM_PROXY_URL/CLARITTY_AUTH_TOKEN is
        set — the usual local-dev case — so the app still works end-to-end
        without AI. It MUST return a dict matching the agent's `output:` schema
        in intelligence.yaml (here `{greeting: string}`). Every generated agent whose work
        needs the model should ship one of these.
        """
        name = (ctx.get_input("name") or "there").strip() or "there"
        return {"greeting": f"Hello, {name}! 👋"}

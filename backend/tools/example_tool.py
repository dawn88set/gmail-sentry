"""Example tool — the v2 standalone-tool shape.

Compare to v1: agents in v1 had no concept of tools; they imported
provider client modules directly. In v2, tools are first-class:
manifest-declared with input/output schemas, decorated with `@tool(id)`,
invoked by the agent's tool-use loop (and by workflow steps with
`tool:` directly).

This tool just echoes its `message` argument back as `reply`. The
v2 workflow engine validates the input against the manifest schema
*before* calling this function, and validates the return shape against
the output schema *after*.
"""

from typing import Any, Dict

from claritty_sdk import tool, ToolCtx


@tool(id="app.echo")
def echo(input: Dict[str, Any], ctx: ToolCtx) -> Dict[str, Any]:
    return {"reply": str(input.get("message", ""))}

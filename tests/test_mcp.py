import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_real_stdio_roundtrip(tmp_path):
    async def run():
        env = dict(os.environ, PROCESS_PLANNING_WORKSPACE=str(tmp_path / "workspace"))
        params = StdioServerParameters(command=sys.executable, args=["-m", "process_planning.server"], env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                tools = {t.name: t for t in (await client.list_tools()).tools}
                assert len(tools) == 12
                assert tools["template_get"].annotations.readOnlyHint
                assert tools["template_edit"].annotations.destructiveHint
                assert tools["inspect"].annotations.readOnlyHint
                assert tools["change_apply"].annotations.destructiveHint
                result = await client.call_tool("workspace_initialize", {})
                assert not result.isError
                revision = json.loads(result.content[0].text)["revision"]
                result = await client.call_tool("change_apply", {"expected_revision": revision, "label": "Add section over MCP", "changes": [{"op": "mkdir", "path": "factory/equipment/turning"}]})
                assert not result.isError
                result = await client.call_tool("catalog_list", {"path": "factory/equipment"})
                assert json.loads(result.content[0].text)["entries"] == [{"path": "factory/equipment/turning", "type": "directory"}]
                result = await client.call_tool("change_apply", {"expected_revision": revision, "label": "Stale edit", "changes": [{"op": "mkdir", "path": "factory/equipment/milling"}]})
                assert result.isError
                assert "revision_conflict" in result.content[0].text
                result = await client.call_tool("template_get", {})
                original = json.loads(result.content[0].text)
                result = await client.call_tool("template_edit", {"expected_revision": original["revision"], "html": "<h1>My factory</h1><table>$rows</table>", "label": "Customize over MCP"})
                assert not result.isError
                result = await client.call_tool("template_get", {})
                assert json.loads(result.content[0].text)["html"].startswith("<h1>My factory")
                result = await client.call_tool("template_edit", {"expected_revision": original["revision"], "html": "$rows"})
                assert result.isError
                assert "revision_conflict" in result.content[0].text
    async def bounded():
        await asyncio.wait_for(run(), timeout=45)
    asyncio.run(bounded())

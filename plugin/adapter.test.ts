import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import type { BbPluginApi } from "@get-bb/plugin-sdk";
import plugin from "./server.js";
import { MiniCappBridge } from "./mcp-client.js";
import sources from "./runtime.json";

test("plugin registers 12 tools and routes to the chat execution host", async () => {
  const tools: any[] = [];
  let dispatched: any;
  const fake = {
    agents: { registerTool: (tool: any) => tools.push(tool) },
    hosts: { experimental_client: () => ({ call: async (...args: any[]) => { dispatched = args; return { content: [] }; } }) },
    sdk: { threads: { get: async () => ({ environmentId: "env" }) }, environments: { get: async () => ({ hostId: "host-1" }) } },
  } as unknown as BbPluginApi;
  plugin(fake);
  assert.equal(tools.length, 12);
  const signal = new AbortController().signal;
  await tools.find(t => t.name === "mini_capp__template_get").execute({}, { threadId: "chat", signal });
  assert.equal(dispatched[2].hostId, "host-1");
  assert.equal(dispatched[2].signal, signal);
  assert.deepEqual(dispatched[1], { name: "template_get", arguments: {} });
});

test("packaged runtime starts through the actual Node MCP bridge", { timeout: 120000 }, async () => {
  const root = await mkdtemp(join(tmpdir(), "mini-capp-adapter-"));
  for (const [path, content] of Object.entries(sources)) {
    const target = join(root, "runtime", path);
    await mkdir(dirname(target), { recursive: true });
    await writeFile(target, content);
  }
  const bridge = new MiniCappBridge(join(root, "runtime"), join(root, "workspace"));
  try {
    const result = await bridge.call("workspace_initialize", {}, new AbortController().signal);
    assert.notEqual(result.isError, true);
    assert.match(JSON.parse(result.content[0].text).revision, /^[0-9a-f]{40}$/);
    const template = await bridge.call("template_get", {}, new AbortController().signal);
    assert.equal(JSON.parse(template.content[0].text).source, "builtin");
  } finally { await bridge.close(); }
});

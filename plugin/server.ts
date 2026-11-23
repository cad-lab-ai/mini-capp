import type { BbPluginApi } from "@get-bb/plugin-sdk";
import { z } from "zod";
import { miniCappContract } from "./contract.js";
import definitions from "./tools.json";

export default function miniCappPlugin(bb: BbPluginApi) {
  const host = bb.hosts.experimental_client({ contract: miniCappContract });
  for (const tool of definitions) {
    bb.agents.registerTool({
      name: `mini_capp__${tool.name}`,
      description: tool.description ?? tool.name,
      parameters: tool.inputSchema,
      async execute(input, ctx) {
        const thread = await bb.sdk.threads.get({ threadId: ctx.threadId });
        if (!thread.environmentId) throw new Error("The chat has no execution environment");
        const environment = await bb.sdk.environments.get({ environmentId: thread.environmentId });
        return host.call("callTool", { name: tool.name, arguments: z.record(z.string(), z.unknown()).parse(input) },
          { hostId: environment.hostId, signal: ctx.signal, timeoutMs: 120000 });
      },
    });
  }
}

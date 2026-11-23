import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { experimental_defineHostEntry } from "@get-bb/plugin-sdk/host";
import { miniCappContract } from "./contract.js";
import { MiniCappBridge } from "./mcp-client.js";
import sources from "./runtime.json";

let bridge: Promise<MiniCappBridge> | undefined;
export default experimental_defineHostEntry({
  contract: miniCappContract,
  handlers: {
    async callTool(input, ctx) {
      bridge ??= (async () => {
        const root = ctx.experimental_paths.dataDir;
        const runtime = join(root, "runtime");
        for (const [path, content] of Object.entries(sources)) {
          const target = join(runtime, path);
          await mkdir(dirname(target), { recursive: true });
          await writeFile(target, content, "utf8");
        }
        return new MiniCappBridge(runtime, join(root, "workspace"));
      })().catch((error: unknown) => { bridge = undefined; throw error; });
      return (await bridge).call(input.name, input.arguments, ctx.signal);
    },
  },
  dispose: async () => { await (await bridge)?.close(); },
});

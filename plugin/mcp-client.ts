import type { Transport } from "@modelcontextprotocol/sdk/shared/transport.js";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { resultSchema } from "./contract.js";

export class MiniCappBridge {
  constructor(
    private readonly runtimePath: string,
    private readonly workspacePath: string,
    private readonly transportFactory?: () => Transport,
  ) {}

  private connection: Promise<Client> | undefined;
  private client: Client | undefined;
  private transport: Transport | undefined;

  private connect(): Promise<Client> {
    if (this.connection) return this.connection;
    const transport =
      this.transportFactory?.() ??
      new StdioClientTransport({
        command: "uv",
        args: ["run", "--project", this.runtimePath, "--frozen", "--no-dev", "mini-capp"],
        stderr: "inherit",
        env: { ...Object.fromEntries(
          Object.entries(process.env).filter(
            (entry): entry is [string, string] => entry[1] !== undefined,
          ),
        ), MINI_CAPP_WORKSPACE: this.workspacePath },
      });
    const client = new Client({ name: "mini-capp", version: "0.1.0" });
    this.client = client;
    this.transport = transport;
    client.onclose = () => {
      this.connection = undefined;
    };
    this.connection = client
      .connect(transport)
      .then(() => client)
      .catch(async (error: unknown) => {
        this.connection = undefined;
        await transport.close().catch(() => {});
        throw error;
      });
    return this.connection;
  }

  async call(name: string, args: Record<string, unknown>, signal: AbortSignal) {
    signal.throwIfAborted();
    const client = await this.connect();
    signal.throwIfAborted();
    const result = await client.callTool({ name, arguments: args }, undefined, {
      signal,
      timeout: 30 * 60 * 1000,
    });
    return resultSchema.parse(result);
  }

  async close() {
    this.connection = undefined;
    await this.client?.close();
    await this.transport?.close();
  }
}

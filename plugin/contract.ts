import { defineRpcContract } from "@get-bb/plugin-sdk";
import { z } from "zod";

export const resultSchema = z.object({
  content: z.array(z.object({ type: z.literal("text"), text: z.string() })),
  isError: z.boolean().optional(),
});
export const miniCappContract = defineRpcContract({
  callTool: {
    input: z.object({ name: z.string(), arguments: z.record(z.string(), z.unknown()) }),
    output: resultSchema,
  },
});

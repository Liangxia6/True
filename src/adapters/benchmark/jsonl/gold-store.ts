import { createReadStream } from "node:fs";
import path from "node:path";
import { createInterface } from "node:readline";

import { GoldRecordSchema, type GoldRecord } from "../../../schemas/contracts.js";

export class JsonlGoldStore {
  private cache: Map<string, GoldRecord> | null = null;

  constructor(private readonly benchmarkRoot: string) {}

  async get(taskId: string): Promise<GoldRecord> {
    if (!this.cache) await this.load();
    const gold = this.cache!.get(taskId);
    if (!gold) throw new Error(`Gold not found for task: ${taskId}`);
    return gold;
  }

  private async load(): Promise<void> {
    const filePath = path.join(this.benchmarkRoot, "gold.jsonl");
    const lines = createInterface({
      input: createReadStream(filePath, { encoding: "utf8" }),
      crlfDelay: Infinity,
    });
    const records = new Map<string, GoldRecord>();
    let lineNumber = 0;
    for await (const line of lines) {
      lineNumber += 1;
      if (!line.trim()) continue;
      try {
        const record = GoldRecordSchema.parse(JSON.parse(line) as unknown);
        records.set(record.task_id, record);
      } catch (error) {
        throw new Error(`Invalid gold at ${filePath}:${lineNumber}`, { cause: error });
      }
    }
    this.cache = records;
  }
}

import { readFile } from "node:fs/promises";
import path from "node:path";

import { parse } from "yaml";

import { JudgeProfileSchema, type JudgeProfile } from "../../../schemas/contracts.js";
import { hashObject } from "../../utils/hash.js";

export async function loadJudgeProfile(filePath: string): Promise<{
  profile: JudgeProfile;
  profileHash: string;
  sourcePath: string;
}> {
  const sourcePath = path.resolve(filePath);
  const profile = JudgeProfileSchema.parse(parse(await readFile(sourcePath, "utf8")) as unknown);
  return { profile, profileHash: hashObject(profile), sourcePath };
}

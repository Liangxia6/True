import assert from "node:assert/strict";
import test from "node:test";

import {
  fallbackAnswerFromMainText,
  normalizeText,
  sanitizePathSegment,
} from "../../../src/adapters/sut/web/doubao/text.js";

test("normalizeText normalizes line endings and whitespace", () => {
  assert.equal(normalizeText(" a  \r\n\r\n\r\n b \n"), "a\n\nb");
});

test("sanitizePathSegment keeps Chinese and safe punctuation", () => {
  assert.equal(sanitizePathSegment("豆包 task/01?"), "豆包_task_01");
});

test("fallbackAnswerFromMainText removes prompt, baseline and UI noise", () => {
  const baseline = "豆包\n新对话\n深入研究\n有什么我能帮你的吗？";
  const prompt = "请研究这个问题";
  const final = `${baseline}\n${prompt}\n新\n这是研究结果。\n来源一`;
  assert.equal(
    fallbackAnswerFromMainText(final, prompt, baseline),
    "这是研究结果。\n来源一",
  );
});

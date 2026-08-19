import assert from "node:assert/strict";
import test from "node:test";

import {
  DoubaoBatchAdapter,
  doubaoOptionsFromManifest,
} from "../../../src/adapters/sut/web/doubao/facade.js";

test("Doubao batch facade declares serial research capabilities", async () => {
  const options = doubaoOptionsFromManifest({
    sutId: "doubao.web.deep-research",
    headless: false,
    options: { profile_dir: ".trueeval/profiles/test-doubao" },
  });
  const spec = await new DoubaoBatchAdapter(options).spec();
  assert.equal(spec.channel, "web");
  assert.equal(spec.capabilities.short_fact, true);
  assert.equal(spec.capabilities.long_form, true);
  assert.equal(spec.concurrency.max_workers, 1);
});

test("Doubao batch options reject invalid polling values", () => {
  assert.throws(
    () =>
      doubaoOptionsFromManifest({
        sutId: "doubao.web.deep-research",
        headless: false,
        options: { poll_interval_ms: 0 },
      }),
    /positive number/,
  );
});

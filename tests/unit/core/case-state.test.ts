import assert from "node:assert/strict";
import test from "node:test";

import { assertTransition, canTransition } from "../../../src/core/state/case-state.js";

test("case state accepts the normal execution path", () => {
  assert.equal(canTransition("CREATED", "QUEUED"), true);
  assert.equal(canTransition("SUBMITTED", "RUNNING"), true);
  assert.equal(canTransition("SCORED", "DONE"), true);
  assert.equal(canTransition("DONE", "GRADING"), true);
});

test("case state rejects skipping submission confirmation", () => {
  assert.equal(canTransition("SUBMITTING", "RUNNING"), false);
  assert.throws(() => assertTransition("SUBMITTING", "RUNNING"), /Invalid case transition/);
});

test("a visually verified existing conversation can recover an unconfirmed submission", () => {
  assert.equal(canTransition("SUBMISSION_UNCONFIRMED", "SUBMITTED"), true);
});

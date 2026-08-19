import assert from "node:assert/strict";
import { test } from "node:test";

import { calculateCitationCalibration } from "../../../src/core/grading/citation-calibration.js";

test("Citation Judge calibration requires both sample size and agreement", () => {
  const small = calculateCitationCalibration(Array.from({ length: 10 }, () => ({ expected: "supported", predicted: "supported" })));
  assert.equal(small.eligible_for_official_metrics, false);
  const calibrated = calculateCitationCalibration(Array.from({ length: 30 }, (_, index) => ({ expected: index % 2 ? "supported" : "contradicted", predicted: index % 2 ? "supported" : "contradicted" })));
  assert.equal(calibrated.cohen_kappa, 1);
  assert.equal(calibrated.eligible_for_official_metrics, true);
});

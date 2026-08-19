let source = "";
for await (const chunk of process.stdin) source += chunk;
const request = JSON.parse(source);
if (request.required_upstream_commit !== "121d4c34050d0e3b0ee441c52c4467cf58ab941e") process.exit(2);
process.stdout.write(JSON.stringify({
  schema_version: "trueeval.deepresearch_official_verdict.v0.1",
  upstream_commit: request.required_upstream_commit,
  quality_score: 7.5,
  quality_dimensions: { Coverage: 8, Insight: 7, "Instruction-following": 8, Clarity: 7 },
  fact_ratio: 0.8,
  right_count: 8,
  wrong_count: 1,
  unknown_count: 1,
  raw: { fixture: true },
}));

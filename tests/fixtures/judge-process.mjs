let input = "";
for await (const chunk of process.stdin) input += chunk;
const request = JSON.parse(input);
let text;
if (request.prompt.user.includes("output_schema")) {
  const payload = JSON.parse(request.prompt.user);
  text = JSON.stringify({
    schema_version: "trueeval.citation_verdict.v0.1",
    claim_id: payload.output_schema.claim_id,
    citation_id: payload.output_schema.citation_id,
    verdict: "supported",
    score: 1,
    confidence: 0.95,
    evidence_spans: [],
    rationale: "Fixture evidence supports the fixture claim.",
    flags: [],
  });
} else {
  text = "最终答案: fixture\n解释: 与参考答案一致。\n结论: 正确";
}
process.stdout.write(JSON.stringify({ text, actual_model: "fixture-judge-v1", usage: { input_tokens: 10, output_tokens: 10 } }));

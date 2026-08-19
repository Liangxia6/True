let source = "";
for await (const chunk of process.stdin) source += chunk;
const request = JSON.parse(source);
process.stdout.write(`${JSON.stringify({ event: "submission_confirmed", detail: { external_session_id: `fixture-${request.identity.caseId}` } })}\n`);
process.stdout.write(`${JSON.stringify({ event: "result", answer: `Agent answer for: ${request.task.input.prompt}`, citations: [], search_calls: 1 })}\n`);

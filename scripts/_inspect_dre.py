import json
import sqlite3
from pathlib import Path

RID = "01a01941-3fb0-7682-97b7-22e894e897f5"
con = sqlite3.connect("runs/.state.sqlite")
con.row_factory = sqlite3.Row
print("=== tasks ===")
for row in con.execute(
    "SELECT task_id, status, last_error_json FROM task_runs WHERE run_id=? ORDER BY task_id",
    (RID,),
):
    err = row["last_error_json"] or ""
    print(row["task_id"], row["status"], err[:240])

print("=== scores ===")
for row in con.execute(
    "SELECT task_id, grader_id, payload_json FROM score_records WHERE run_id=? ORDER BY task_id, grader_id",
    (RID,),
):
    payload = json.loads(row["payload_json"])
    print(
        row["task_id"][-6:],
        row["grader_id"],
        payload.get("status"),
        payload.get("raw_value"),
        payload.get("normalized_value"),
        (payload.get("rationale") or payload.get("error") or "")[:180],
    )

summary = Path(f"runs/{RID}/summary.json")
if summary.exists():
    print("=== summary ===")
    print(summary.read_text(encoding="utf-8")[:1500])

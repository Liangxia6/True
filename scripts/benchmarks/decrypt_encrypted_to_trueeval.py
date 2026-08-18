"""Decrypt official encrypted tables and write TrueEval V0.1 files.

Uses the upstream decrypt algorithms only:
  - BrowseComp-ZH: SHA256(canary) XOR + base64  (official browsecomp-zh-decrypt.py)
  - xbench-DeepSearch: canary XOR + base64      (official xbench_evals.py)

Does not rewrite prompts, invent answer aliases, or put gold into tasks.jsonl.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXTRACTION_VERSION = "extractor.deepresearch.v0.2"
EXTRACTED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

TASK_REQUIRED = {
    "schema_version",
    "task_id",
    "benchmark_id",
    "upstream_task_id",
    "split",
    "task_family",
    "input",
    "expected_output",
    "constraints",
    "provenance",
    "tags",
}
TASK_FORBIDDEN = {
    "reference_answer",
    "acceptable_answers",
    "unacceptable_answers",
    "claims",
    "official_grader_payload",
    "judge_prompt",
    "reference_steps",
    "canary",
}


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def xor_decrypt_key(data: bytes, key: str) -> str:
    key_bytes = key.encode("utf-8")
    n = len(key_bytes)
    return bytes(data[i] ^ key_bytes[i % n] for i in range(len(data))).decode("utf-8")


def browsecomp_decrypt_cell(ciphertext_b64: str, password: str) -> str:
    encrypted = base64.b64decode(ciphertext_b64)
    hasher = hashlib.sha256()
    hasher.update(password.encode())
    key = hasher.digest()
    key = key * (len(encrypted) // len(key)) + key[: len(encrypted) % len(key)]
    return bytes(a ^ b for a, b in zip(encrypted, key)).decode("utf-8")


def pad_id(raw: str | int, width: int = 6) -> str:
    text = str(raw).strip()
    return text.zfill(width) if text.isdigit() else text


def extract_as_of(prompt: str) -> str | None:
    if not prompt:
        return None
    m = re.search(r"as of (\d{4}-\d{2}-\d{2})", prompt, flags=re.I)
    if m:
        return m.group(1)
    m = re.search(r"截至\s*(\d{4})年(\d{1,2})月(\d{1,2})日", prompt)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", prompt)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    dates = re.findall(r"(20\d{2}-\d{2}-\d{2})", prompt)
    if dates:
        return max(dates)
    return None


def make_task(
    *,
    benchmark_id: str,
    split: str,
    upstream_task_id: str,
    prompt: str,
    source_file: str,
    source_row: int,
    source_hash: str,
    tags: list[str],
    as_of: str | None,
) -> dict:
    return {
        "schema_version": "trueeval.research_task.v0.1",
        "task_id": f"{benchmark_id}.{split}.{pad_id(upstream_task_id)}",
        "benchmark_id": benchmark_id,
        "upstream_task_id": str(upstream_task_id),
        "split": split,
        "task_family": "multi_hop_research",
        "input": {
            "prompt": prompt,
            "language": "zh-CN",
            "as_of": as_of,
            "attachments": [],
        },
        "expected_output": {
            "answer_form": "short_text",
            "citation_required": False,
            "structured_fields": [],
        },
        "constraints": {
            "internet_required": True,
            "timeout_seconds": 900,
            "max_search_calls": None,
            "allowed_tools": ["web_search", "browser"],
            "forbidden_domains": [],
            "required_domains": [],
        },
        "provenance": {
            "source_file": source_file,
            "source_row": source_row,
            "source_hash": source_hash,
            "extraction_version": EXTRACTION_VERSION,
            "extracted_at": EXTRACTED_AT,
        },
        "tags": tags,
    }


def make_gold(
    *,
    task_id: str,
    answer: str,
    as_of: str | None,
    source_file: str,
    source_row: int,
    source_hash: str,
    payload: dict,
) -> dict:
    return {
        "schema_version": "trueeval.research_gold.v0.1",
        "task_id": task_id,
        "answer_type": "short_text",
        "reference_answer": answer,
        "acceptable_answers": [],
        "unacceptable_answers": [],
        "claims": [],
        "temporal_scope": {
            "valid_as_of": as_of,
            "valid_from": None,
            "valid_until": None,
        },
        "official_grader_payload": payload,
        "provenance": {
            "source_file": source_file,
            "source_row": source_row,
            "source_hash": source_hash,
        },
    }


def decrypt_browsecomp() -> tuple[int, int]:
    import pandas as pd

    bench = ROOT / "benchmarks" / "browsecomp-zh"
    xlsx = bench / "upstream" / "browsecomp-zh-encrypted.xlsx"
    if not xlsx.exists():
        raise FileNotFoundError(xlsx)
    df = pd.read_excel(xlsx)
    if "canary" not in df.columns:
        raise ValueError("BrowseComp-ZH missing canary")

    originals = []
    tasks = []
    golds = []
    for i, row in df.iterrows():
        password = str(row["canary"])
        topic = browsecomp_decrypt_cell(str(row["Topic"]), password)
        question = browsecomp_decrypt_cell(str(row["Question"]), password)
        answer = browsecomp_decrypt_cell(str(row["Answer"]), password)
        if not question.strip() or not answer.strip():
            raise ValueError(f"BrowseComp-ZH row {i} decrypted empty")
        encrypted_q = str(row["Question"])
        upstream_id = str(int(i) + 1)
        source_row = int(i) + 2
        source_hash = sha256_text(encrypted_q)
        as_of = extract_as_of(question)
        originals.append(
            {
                "id": int(upstream_id),
                "Topic": topic,
                "Question": question,
                "Answer": answer,
            }
        )
        task = make_task(
            benchmark_id="browsecomp-zh",
            split="test",
            upstream_task_id=upstream_id,
            prompt=question,
            source_file="data/browsecomp-zh-encrypted.xlsx",
            source_row=source_row,
            source_hash=source_hash,
            tags=["multi-hop", "native-zh", "encrypted-upstream", "not-formal-public-leaderboard"],
            as_of=as_of,
        )
        gold = make_gold(
            task_id=task["task_id"],
            answer=answer,
            as_of=as_of,
            source_file="data/browsecomp-zh-encrypted.xlsx",
            source_row=source_row,
            source_hash=source_hash,
            payload={
                "topic": topic,
                "judge_prompt_id": "browsecomp_zh.JUDGE_PROMPT_CN",
                "judge_model_official": "gpt-4o",
            },
        )
        tasks.append(task)
        golds.append(gold)

    write_jsonl(bench / "local" / "decrypted_original.jsonl", originals)
    write_jsonl(bench / "tasks.jsonl", tasks)
    write_jsonl(bench / "gold.jsonl", golds)
    validate_pair(bench / "tasks.jsonl", bench / "gold.jsonl")
    as_of_n = sum(1 for t in tasks if t["input"]["as_of"])
    print(f"browsecomp-zh: {len(tasks)} tasks, as_of filled {as_of_n}")
    return len(tasks), as_of_n


def decrypt_xbench_file(csv_path: Path, split: str, source_file: str) -> tuple[list[dict], list[dict], list[dict]]:
    originals = []
    tasks = []
    golds = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for source_row, row in enumerate(reader, start=2):
            key = row["canary"]
            prompt = xor_decrypt_key(base64.b64decode(row["prompt"]), key)
            answer = xor_decrypt_key(base64.b64decode(row["answer"]), key)
            steps = None
            raw_steps = (row.get("reference_steps") or "").strip()
            if raw_steps:
                try:
                    steps = xor_decrypt_key(base64.b64decode(raw_steps), key)
                except Exception:
                    steps = None
            upstream_id = str(row.get("id") or "").strip()
            if not upstream_id:
                raise ValueError(f"{csv_path.name} row {source_row} missing official id")
            if not prompt.strip() or not answer.strip():
                raise ValueError(f"{csv_path.name} id={upstream_id} decrypted empty")
            source_hash = sha256_text(row["prompt"])
            as_of = extract_as_of(prompt)
            tags = ["multi-hop", "native-zh", "encrypted-upstream"]
            if split == "2510":
                tags.append("not-first-round-mvp")
            originals.append(
                {
                    "id": upstream_id,
                    "split": split,
                    "prompt": prompt,
                    "answer": answer,
                    "reference_steps": steps,
                    "type": row.get("type") or "问答题",
                }
            )
            task = make_task(
                benchmark_id="xbench-deepsearch",
                split=split,
                upstream_task_id=upstream_id,
                prompt=prompt,
                source_file=source_file,
                source_row=source_row,
                source_hash=source_hash,
                tags=tags,
                as_of=as_of,
            )
            payload = {
                "type": row.get("type") or "问答题",
                "judge_prompt_id": "xbench.LLM_JUDGE_PROMPT",
                "exact_match_first": True,
                "official_answer_format": "最终答案:[短答案]",
            }
            if steps:
                payload["reference_steps"] = steps
            gold = make_gold(
                task_id=task["task_id"],
                answer=answer,
                as_of=as_of,
                source_file=source_file,
                source_row=source_row,
                source_hash=source_hash,
                payload=payload,
            )
            tasks.append(task)
            golds.append(gold)
    return originals, tasks, golds


def decrypt_xbench() -> tuple[int, int]:
    bench = ROOT / "benchmarks" / "xbench-deepsearch"
    files = [
        ("2505", bench / "upstream" / "DeepSearch-2505.csv", "data/DeepSearch-2505.csv"),
        ("2510", bench / "upstream" / "DeepSearch-2510.csv", "data/DeepSearch-2510.csv"),
    ]
    originals: list[dict] = []
    tasks: list[dict] = []
    golds: list[dict] = []
    for split, path, rel in files:
        if not path.exists():
            raise FileNotFoundError(path)
        o, t, g = decrypt_xbench_file(path, split, rel)
        originals.extend(o)
        tasks.extend(t)
        golds.extend(g)
        print(f"  xbench {split}: {len(t)}")
    write_jsonl(bench / "local" / "decrypted_original.jsonl", originals)
    write_jsonl(bench / "tasks.jsonl", tasks)
    write_jsonl(bench / "gold.jsonl", golds)
    validate_pair(bench / "tasks.jsonl", bench / "gold.jsonl")
    as_of_n = sum(1 for t in tasks if t["input"]["as_of"])
    print(f"xbench-deepsearch: {len(tasks)} tasks, as_of filled {as_of_n}")
    return len(tasks), as_of_n


def validate_pair(tasks_path: Path, golds_path: Path) -> None:
    tasks = [json.loads(line) for line in tasks_path.read_text(encoding="utf-8").splitlines() if line]
    golds = [json.loads(line) for line in golds_path.read_text(encoding="utf-8").splitlines() if line]
    if len(tasks) != len(golds):
        raise AssertionError(f"count mismatch {tasks_path}")
    task_ids = [t["task_id"] for t in tasks]
    gold_ids = [g["task_id"] for g in golds]
    if task_ids != gold_ids:
        raise AssertionError(f"task_id order mismatch {tasks_path}")
    if len(set(task_ids)) != len(task_ids):
        raise AssertionError(f"duplicate task_id {tasks_path}")
    for i, (task, gold) in enumerate(zip(tasks, golds), start=1):
        missing = TASK_REQUIRED - set(task)
        if missing:
            raise AssertionError(f"{tasks_path}:{i} missing {missing}")
        leaked = TASK_FORBIDDEN.intersection(task)
        if leaked:
            raise AssertionError(f"{tasks_path}:{i} leaked {leaked}")
        prompt = task["input"]["prompt"]
        if not isinstance(prompt, str) or not prompt.strip():
            raise AssertionError(f"{tasks_path}:{i} empty prompt")
        answer = gold.get("reference_answer")
        if not isinstance(answer, str) or not answer.strip():
            raise AssertionError(f"{golds_path}:{i} empty gold")
        if answer in prompt and len(answer) >= 8:
            raise AssertionError(f"{tasks_path}:{i} gold text leaked into prompt")
        blob = json.dumps(task, ensure_ascii=False)
        for bad in ("JUDGE_PROMPT", "extracted_final_answer", "reference_steps"):
            if bad in blob:
                raise AssertionError(f"{tasks_path}:{i} contains {bad}")


def main() -> None:
    bc_n, bc_asof = decrypt_browsecomp()
    xb_n, xb_asof = decrypt_xbench()
    report = {
        "extracted_at": EXTRACTED_AT,
        "extraction_version": EXTRACTION_VERSION,
        "browsecomp-zh": {"tasks": bc_n, "as_of_filled": bc_asof},
        "xbench-deepsearch": {"tasks": xb_n, "as_of_filled": xb_asof},
        "outputs": {
            "trueeval": [
                "benchmarks/browsecomp-zh/tasks.jsonl",
                "benchmarks/browsecomp-zh/gold.jsonl",
                "benchmarks/xbench-deepsearch/tasks.jsonl",
                "benchmarks/xbench-deepsearch/gold.jsonl",
            ],
            "decrypted_originals_local_only": [
                "benchmarks/browsecomp-zh/local/decrypted_original.jsonl",
                "benchmarks/xbench-deepsearch/local/decrypted_original.jsonl",
            ],
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

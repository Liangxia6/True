"""Download the three official Deep Research sources and convert them to TrueEval V0.1.

Sources (from docs/research/deepresearch-benchmarks/05):
  - BrowseComp-ZH          short-fact
  - xbench-DeepSearch      short-fact (2505 MVP; 2510 not first-round MVP)
  - DeepResearchEval       long-form (English upstream, not the Chinese formal set)

Constraints applied:
  - Pin full commit SHA, never "main" / "latest"
  - Keep official IDs; never invent aliases
  - Split tasks.jsonl and gold.jsonl
  - Keep official graders; do not rewrite them as a new LLM Judge
  - Record license, file hashes, source path, split
  - Do not publish decrypted plaintext of encrypted benchmarks
"""

from __future__ import annotations

import base64
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = ROOT / "benchmarks"
EXTRACTION_VERSION = "extractor.deepresearch.v0.1"
EXTRACTED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

BROWSECOMP = {
    "benchmark_id": "browsecomp-zh",
    "owner": "PALIN2018",
    "repo": "BrowseComp-ZH",
    "commit": "86abe635e7deef89ec00c68ff1c2588f0e2f2099",
    "license": "MIT (GitHub README); Hugging Face card also lists apache-2.0; academic research only",
    "homepage": "https://github.com/PALIN2018/BrowseComp-ZH",
}

XBENCH = {
    "benchmark_id": "xbench-deepsearch",
    "owner": "xbench-ai",
    "repo": "xbench-evals",
    "commit": "17c562192cc7e62215bfb98b65e9f8806fb95504",
    "license": "MIT",
    "homepage": "https://xbench.org/#/agi/aisearch",
}

DRE = {
    "benchmark_id": "deepresearcheval",
    "owner": "Infinity-AILab",
    "repo": "DeepResearchEval",
    "commit": "121d4c34050d0e3b0ee441c52c4467cf58ab941e",
    "license": "Apache-2.0",
    "homepage": "https://infinity-ailab.github.io/deep_research_eval/",
}

USER_AGENT = "TrueEval-dataset-ingest/0.1 (research; +https://github.com/)"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace("\r\n", "\n"), encoding="utf-8")


def download(urls: list[str], dest: Path, min_bytes: int = 32) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            if len(data) < min_bytes:
                errors.append(f"{url} -> too small ({len(data)} bytes)")
                continue
            dest.write_bytes(data)
            print(f"  downloaded {dest.name} ({len(data)} bytes) from {url}")
            return url
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{url} -> {exc}")
    raise RuntimeError("All download mirrors failed for " + str(dest) + "\n" + "\n".join(errors))


def gh_urls(owner: str, repo: str, commit: str, relpath: str) -> list[str]:
    return [
        f"https://cdn.jsdelivr.net/gh/{owner}/{repo}@{commit}/{relpath}",
        f"https://cdn.jsdmirror.com/gh/{owner}/{repo}@{commit}/{relpath}",
        f"https://raw.gitmirror.com/{owner}/{repo}/{commit}/{relpath}",
        f"https://ghfast.top/https://raw.githubusercontent.com/{owner}/{repo}/{commit}/{relpath}",
        f"https://mirror.ghproxy.com/https://raw.githubusercontent.com/{owner}/{repo}/{commit}/{relpath}",
        f"https://raw.githubusercontent.com/{owner}/{repo}/{commit}/{relpath}",
    ]


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
    if text.isdigit():
        return text.zfill(width)
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text)


def detect_language(text: str, fallback: str) -> str:
    if fallback:
        return fallback
    return "zh-CN" if re.search(r"[\u4e00-\u9fff]", text) else "en"


def extract_as_of(prompt: str) -> str | None:
    m = re.search(r"as of (\d{4}-\d{2}-\d{2})", prompt, flags=re.I)
    if m:
        return m.group(1)
    dates = re.findall(r"(20\d{2}-\d{2}-\d{2})", prompt)
    if dates:
        return max(dates)
    months = {
        "january": "01",
        "february": "02",
        "march": "03",
        "april": "04",
        "may": "05",
        "june": "06",
        "july": "07",
        "august": "08",
        "september": "09",
        "october": "10",
        "november": "11",
        "december": "12",
    }
    month_hits = re.findall(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
        prompt,
        flags=re.I,
    )
    if month_hits:
        year_month = [f"{year}-{months[month.lower()]}" for month, year in month_hits]
        return max(year_month)
    return None


def dump_yaml(data: dict, path: Path) -> None:
    try:
        import yaml  # type: ignore
    except ImportError:
        yaml = None
    if yaml is not None:
        write_text(path, yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
        return
    # Minimal fallback so ingest still works without PyYAML.
    def emit(obj, indent=0) -> str:
        sp = "  " * indent
        if isinstance(obj, dict):
            lines = []
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    lines.append(f"{sp}{k}:")
                    lines.append(emit(v, indent + 1))
                elif v is None:
                    lines.append(f"{sp}{k}: null")
                elif isinstance(v, bool):
                    lines.append(f"{sp}{k}: {'true' if v else 'false'}")
                elif isinstance(v, (int, float)):
                    lines.append(f"{sp}{k}: {v}")
                else:
                    text = str(v).replace("\\", "\\\\").replace('"', '\\"')
                    lines.append(f'{sp}{k}: "{text}"')
            return "\n".join(lines)
        if isinstance(obj, list):
            lines = []
            for item in obj:
                if isinstance(item, (dict, list)):
                    lines.append(f"{sp}-")
                    lines.append(emit(item, indent + 1))
                elif item is None:
                    lines.append(f"{sp}- null")
                else:
                    text = str(item).replace("\\", "\\\\").replace('"', '\\"')
                    lines.append(f'{sp}- "{text}"')
            return "\n".join(lines)
        return f"{sp}{obj}"

    write_text(path, emit(data) + "\n")


def short_fact_task(
    *,
    benchmark_id: str,
    split: str,
    upstream_task_id: str,
    prompt: str,
    language: str,
    source_file: str,
    source_row: int,
    source_hash: str,
    tags: list[str],
    as_of: str | None = None,
    citation_required: bool = False,
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
            "language": language,
            "as_of": as_of,
            "attachments": [],
        },
        "expected_output": {
            "answer_form": "short_text",
            "citation_required": citation_required,
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
        },
        "tags": tags,
    }


def short_fact_gold(
    *,
    task_id: str,
    answer: str,
    source_file: str,
    source_row: int,
    source_hash: str,
    extra_payload: dict,
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
            "valid_as_of": None,
            "valid_from": None,
            "valid_until": None,
        },
        "official_grader_payload": extra_payload,
        "provenance": {
            "source_file": source_file,
            "source_row": source_row,
            "source_hash": source_hash,
        },
    }


def write_sf_rubric(path: Path, benchmark_id: str, adapter: str, extra_metrics: list[dict] | None = None) -> None:
    metrics = [
        {
            "metric_id": "official.answer_accuracy",
            "namespace": "official",
            "role": "score",
            "method": "upstream_executable",
            "adapter": adapter,
            "inputs": ["prediction.final_answer", "gold.reference_answer", "gold.official_grader_payload"],
            "range": [0.0, 1.0],
            "weight": 1.0,
            "missing_policy": "error",
        },
        {
            "metric_id": "trueeval.citation_correctness",
            "namespace": "trueeval",
            "role": "diagnostic",
            "method": "claim_citation_entailment",
            "inputs": ["prediction.claims", "prediction.citations", "artifacts.search_results"],
            "range": [0.0, 1.0],
            "weight": 0.0,
            "missing_policy": "not_observable",
        },
        {
            "metric_id": "trueeval.citation_completeness",
            "namespace": "trueeval",
            "role": "diagnostic",
            "method": "weighted_claim_coverage",
            "inputs": ["prediction.claims", "prediction.citations"],
            "range": [0.0, 1.0],
            "weight": 0.0,
            "missing_policy": "not_observable",
        },
        {
            "metric_id": "trueeval.source_quality",
            "namespace": "trueeval",
            "role": "diagnostic",
            "method": "source_quality_rubric",
            "inputs": ["prediction.citations"],
            "range": [0.0, 1.0],
            "weight": 0.0,
            "missing_policy": "not_observable",
        },
        {
            "metric_id": "trueeval.temporal_validity",
            "namespace": "trueeval",
            "role": "gate",
            "applies_when": "task.input.as_of != null",
            "method": "evidence_date_check",
            "inputs": ["task.input.as_of", "prediction.claims", "prediction.citations"],
            "threshold": 1.0,
            "missing_policy": "fail",
        },
    ]
    if extra_metrics:
        metrics.extend(extra_metrics)
    dump_yaml(
        {
            "schema_version": "trueeval.research_rubric.v0.1",
            "rubric_id": f"{benchmark_id}.default.v1",
            "benchmark_id": benchmark_id,
            "gates": [
                {
                    "metric_id": "trueeval.execution_success",
                    "condition": "status == completed",
                    "on_fail": "exclude_as_system_failure",
                }
            ],
            "metrics": metrics,
            "aggregation": {
                "official_primary": "official.answer_accuracy",
                "trueeval_composite": None,
                "leaderboard_metric": "official.answer_accuracy",
                "system_failures": "report_separately",
                "confidence_interval": {"method": "bootstrap", "samples": 10000, "confidence": 0.95},
            },
        },
        path,
    )


def ingest_browsecomp() -> dict:
    meta = BROWSECOMP
    out = BENCH_ROOT / meta["benchmark_id"]
    upstream = out / "upstream"
    (out / "adapters").mkdir(parents=True, exist_ok=True)
    print("== browsecomp-zh")
    xlsx = upstream / "browsecomp-zh-encrypted.xlsx"
    decrypt_py = upstream / "browsecomp-zh-decrypt.py"
    prompt_py = upstream / "official_prompt.py"
    ece_py = upstream / "run_acc_calibration_error.py"
    src_xlsx = download(gh_urls(meta["owner"], meta["repo"], meta["commit"], "data/browsecomp-zh-encrypted.xlsx"), xlsx, 1000)
    src_dec = download(gh_urls(meta["owner"], meta["repo"], meta["commit"], "data/browsecomp-zh-decrypt.py"), decrypt_py)
    src_prompt = download(gh_urls(meta["owner"], meta["repo"], meta["commit"], "prompt.py"), prompt_py)
    src_ece = download(gh_urls(meta["owner"], meta["repo"], meta["commit"], "run_acc_calibration_error.py"), ece_py)

    try:
        import pandas as pd
    except ImportError:
        os.system(f"{sys.executable} -m pip install pandas openpyxl")
        import pandas as pd

    df = pd.read_excel(xlsx)
    if "canary" not in df.columns:
        raise ValueError("BrowseComp-ZH missing canary column")
    columns = [str(c) for c in df.columns]
    print("  columns:", columns)

    tasks: list[dict] = []
    golds: list[dict] = []
    id_col = next((c for c in df.columns if str(c).lower() in {"id", "qid", "question_id", "idx"}), None)

    for i, row in df.iterrows():
        password = str(row["canary"])
        decrypted = {}
        for col in df.columns:
            value = row[col]
            if col == "canary" or pd.isna(value):
                continue
            text = str(value)
            if col in {"Topic", "Question", "Answer"} or (isinstance(value, str) and len(text) > 20):
                try:
                    decrypted[str(col)] = browsecomp_decrypt_cell(text, password)
                except Exception:
                    decrypted[str(col)] = text
            else:
                decrypted[str(col)] = text

        question = decrypted.get("Question") or decrypted.get("question")
        answer = decrypted.get("Answer") or decrypted.get("answer")
        topic = decrypted.get("Topic") or decrypted.get("topic") or ""
        if not question or not answer:
            raise ValueError(f"BrowseComp-ZH row {i} missing question/answer after decrypt")

        if id_col is not None and not pd.isna(row[id_col]):
            upstream_id = str(int(row[id_col])) if str(row[id_col]).replace(".0", "").isdigit() else str(row[id_col])
        else:
            # Official workbook has no id column; use 1-based official file order.
            upstream_id = str(int(i) + 1)

        source_hash = sha256_text(str(row["Question"]))
        source_row = int(i) + 2  # Excel header is row 1
        task = short_fact_task(
            benchmark_id=meta["benchmark_id"],
            split="test",
            upstream_task_id=upstream_id,
            prompt=question,
            language="zh-CN",
            source_file="data/browsecomp-zh-encrypted.xlsx",
            source_row=source_row,
            source_hash=source_hash,
            tags=["multi-hop", "native-zh", "encrypted-upstream", "not-formal-public-leaderboard"],
        )
        extra = {k: v for k, v in decrypted.items() if k not in {"Question", "Answer", "question", "answer"}}
        gold = short_fact_gold(
            task_id=task["task_id"],
            answer=answer,
            source_file="data/browsecomp-zh-encrypted.xlsx",
            source_row=source_row,
            source_hash=source_hash,
            extra_payload={
                "topic": topic,
                "judge_prompt_id": "browsecomp_zh.JUDGE_PROMPT_CN",
                "judge_model_official": "gpt-4o",
                "upstream_fields": extra,
            },
        )
        tasks.append(task)
        golds.append(gold)

    write_jsonl(out / "tasks.jsonl", tasks)
    write_jsonl(out / "gold.jsonl", golds)
    dump_yaml(
        {
            "schema_version": "trueeval.research_benchmark.v0.1",
            "benchmark_id": meta["benchmark_id"],
            "name": "BrowseComp-ZH",
            "benchmark_version": meta["commit"],
            "domain": "research",
            "task_family": "multi_hop_research",
            "track": "short_fact",
            "formal_public_leaderboard": False,
            "notes": "05 standard: do not use the full 289-item static set as the formal public Chinese leaderboard.",
            "upstream": {
                "repo_url": meta["homepage"],
                "commit_sha": meta["commit"],
                "dataset_path": "data/browsecomp-zh-encrypted.xlsx",
                "evaluator_path": "prompt.py + run.py + run_acc_calibration_error.py",
                "license": meta["license"],
                "homepage": "https://arxiv.org/abs/2504.19314",
            },
            "splits": [
                {
                    "name": "test",
                    "public_questions": False,
                    "public_gold": False,
                    "task_count": len(tasks),
                }
            ],
            "default_execution": {
                "mode": "submission",
                "timeout_seconds": 900,
                "max_attempts": 1,
                "internet_required": True,
                "allowed_tools": ["web_search", "browser"],
                "output_contract": "research_answer.v0.1",
            },
            "official_metrics": ["official.answer_accuracy"],
            "trueeval_metrics": [
                "trueeval.citation_correctness",
                "trueeval.citation_completeness",
                "trueeval.source_quality",
                "trueeval.temporal_validity",
            ],
            "observation_only": ["official.ece", "trueeval.latency", "trueeval.cost"],
        },
        out / "benchmark.yaml",
    )
    write_sf_rubric(
        out / "rubric.yaml",
        meta["benchmark_id"],
        "adapters/official_grader.py",
        extra_metrics=[
            {
                "metric_id": "official.ece",
                "namespace": "official",
                "role": "diagnostic",
                "method": "upstream_executable",
                "adapter": "adapters/official_ece.py",
                "inputs": ["prediction.confidence", "gold.official_grader_payload"],
                "range": [0.0, 1.0],
                "weight": 0.0,
                "missing_policy": "not_observable",
            }
        ],
    )
    lock = {
        "schema_version": "trueeval.upstream_lock.v0.1",
        "benchmark_id": meta["benchmark_id"],
        "extracted_at": EXTRACTED_AT,
        "extraction_version": EXTRACTION_VERSION,
        "upstream": {
            "repo_url": meta["homepage"],
            "commit_sha": meta["commit"],
            "license": meta["license"],
        },
        "files": [
            {"path": "data/browsecomp-zh-encrypted.xlsx", "sha256": sha256_file(xlsx), "download_url": src_xlsx},
            {"path": "data/browsecomp-zh-decrypt.py", "sha256": sha256_file(decrypt_py), "download_url": src_dec},
            {"path": "prompt.py", "sha256": sha256_file(prompt_py), "download_url": src_prompt},
            {"path": "run_acc_calibration_error.py", "sha256": sha256_file(ece_py), "download_url": src_ece},
        ],
        "task_count": len(tasks),
        "plaintext_policy": "decrypted tasks.jsonl and gold.jsonl are local-only; do not upload",
    }
    dump_yaml(lock, out / "upstream.lock.yaml")
    shutil.copy2(prompt_py, out / "adapters" / "official_prompt.py")
    shutil.copy2(ece_py, out / "adapters" / "official_ece.py")
    return lock


def ingest_xbench() -> dict:
    meta = XBENCH
    out = BENCH_ROOT / meta["benchmark_id"]
    upstream = out / "upstream"
    (out / "adapters").mkdir(parents=True, exist_ok=True)
    print("== xbench-deepsearch")
    files = {
        "2505": "data/DeepSearch-2505.csv",
        "2510": "data/DeepSearch-2510.csv",
    }
    downloaded = {}
    for split, rel in files.items():
        dest = upstream / Path(rel).name
        url = download(gh_urls(meta["owner"], meta["repo"], meta["commit"], rel), dest, 1000)
        downloaded[split] = (dest, url, rel)

    grader = upstream / "eval_grader.py"
    evaller = upstream / "xbench_evals.py"
    license_p = upstream / "LICENSE"
    src_grader = download(gh_urls(meta["owner"], meta["repo"], meta["commit"], "eval_grader.py"), grader)
    src_eval = download(gh_urls(meta["owner"], meta["repo"], meta["commit"], "xbench_evals.py"), evaller)
    src_lic = download(gh_urls(meta["owner"], meta["repo"], meta["commit"], "LICENSE"), license_p)
    lm = upstream / "language_models.py"
    src_lm = download(gh_urls(meta["owner"], meta["repo"], meta["commit"], "language_models.py"), lm)

    tasks: list[dict] = []
    golds: list[dict] = []
    split_counts = {}
    for split, (path, _url, rel) in downloaded.items():
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for source_row, row in enumerate(reader, start=2):
                key = row["canary"]
                prompt = xor_decrypt_key(base64.b64decode(row["prompt"]), key)
                answer = xor_decrypt_key(base64.b64decode(row["answer"]), key)
                upstream_id = str(row.get("id") or "").strip()
                if not upstream_id:
                    raise ValueError(f"xbench {split} row {source_row} missing official id")
                source_hash = sha256_text(row["prompt"])
                tags = ["multi-hop", "native-zh", "encrypted-upstream"]
                if split == "2510":
                    tags.append("not-first-round-mvp")
                task = short_fact_task(
                    benchmark_id=meta["benchmark_id"],
                    split=split,
                    upstream_task_id=upstream_id,
                    prompt=prompt,
                    language=detect_language(prompt, "zh-CN"),
                    source_file=rel,
                    source_row=source_row,
                    source_hash=source_hash,
                    tags=tags,
                    citation_required=False,
                )
                gold = short_fact_gold(
                    task_id=task["task_id"],
                    answer=answer,
                    source_file=rel,
                    source_row=source_row,
                    source_hash=source_hash,
                    extra_payload={
                        "type": row.get("type") or "问答题",
                        "judge_prompt_id": "xbench.LLM_JUDGE_PROMPT",
                        "exact_match_first": True,
                        "official_answer_format": "最终答案:[短答案]",
                    },
                )
                tasks.append(task)
                golds.append(gold)
        split_counts[split] = sum(1 for t in tasks if t["split"] == split)

    write_jsonl(out / "tasks.jsonl", tasks)
    write_jsonl(out / "gold.jsonl", golds)
    dump_yaml(
        {
            "schema_version": "trueeval.research_benchmark.v0.1",
            "benchmark_id": meta["benchmark_id"],
            "name": "xbench-DeepSearch",
            "benchmark_version": meta["commit"],
            "domain": "research",
            "task_family": "multi_hop_research",
            "track": "short_fact",
            "upstream": {
                "repo_url": "https://github.com/xbench-ai/xbench-evals",
                "commit_sha": meta["commit"],
                "dataset_path": "data/DeepSearch-2505.csv + data/DeepSearch-2510.csv",
                "evaluator_path": "eval_grader.py",
                "license": meta["license"],
                "homepage": meta["homepage"],
            },
            "splits": [
                {
                    "name": "2505",
                    "public_questions": False,
                    "public_gold": False,
                    "task_count": split_counts.get("2505", 0),
                    "mvp": True,
                },
                {
                    "name": "2510",
                    "public_questions": False,
                    "public_gold": False,
                    "task_count": split_counts.get("2510", 0),
                    "mvp": False,
                    "notes": "05 standard: 2510 multimodal / dynamic interaction is out of first-round MVP.",
                },
            ],
            "default_execution": {
                "mode": "submission",
                "timeout_seconds": 900,
                "max_attempts": 1,
                "internet_required": True,
                "allowed_tools": ["web_search", "browser"],
                "output_contract": "research_answer.v0.1",
            },
            "official_metrics": ["official.answer_accuracy"],
            "trueeval_metrics": [
                "trueeval.citation_correctness",
                "trueeval.citation_completeness",
                "trueeval.source_quality",
                "trueeval.temporal_validity",
            ],
            "observation_only": ["trueeval.latency", "trueeval.cost"],
            "contamination_policy": "Do not upload decrypted plaintext. Official request in xbench-evals README.",
        },
        out / "benchmark.yaml",
    )
    write_sf_rubric(out / "rubric.yaml", meta["benchmark_id"], "adapters/official_grader.py")
    lock = {
        "schema_version": "trueeval.upstream_lock.v0.1",
        "benchmark_id": meta["benchmark_id"],
        "extracted_at": EXTRACTED_AT,
        "extraction_version": EXTRACTION_VERSION,
        "upstream": {
            "repo_url": "https://github.com/xbench-ai/xbench-evals",
            "commit_sha": meta["commit"],
            "license": meta["license"],
        },
        "files": [
            {
                "path": rel,
                "sha256": sha256_file(path),
                "download_url": url,
            }
            for split, (path, url, rel) in downloaded.items()
        ]
        + [
            {"path": "eval_grader.py", "sha256": sha256_file(grader), "download_url": src_grader},
            {"path": "xbench_evals.py", "sha256": sha256_file(evaller), "download_url": src_eval},
            {"path": "LICENSE", "sha256": sha256_file(license_p), "download_url": src_lic},
            {"path": "language_models.py", "sha256": sha256_file(lm), "download_url": src_lm},
        ],
        "task_count": len(tasks),
        "split_counts": split_counts,
        "plaintext_policy": "decrypted tasks.jsonl and gold.jsonl are local-only; do not upload",
    }
    dump_yaml(lock, out / "upstream.lock.yaml")
    shutil.copy2(grader, out / "adapters" / "official_grader.py")
    shutil.copy2(evaller, out / "adapters" / "xbench_evals.py")
    shutil.copy2(lm, out / "adapters" / "language_models.py")
    return lock


def ingest_deepresearcheval() -> dict:
    meta = DRE
    out = BENCH_ROOT / meta["benchmark_id"]
    upstream = out / "upstream"
    (out / "adapters").mkdir(parents=True, exist_ok=True)
    print("== deepresearcheval")
    v1 = upstream / "query.jsonl"
    v2 = upstream / "query_2601_en.jsonl"
    license_p = upstream / "LICENSE"
    example = upstream / "example_pointwise_usage.py"
    src_v1 = download(gh_urls(meta["owner"], meta["repo"], meta["commit"], "data/input_queries/query.jsonl"), v1)
    src_v2 = download(
        gh_urls(meta["owner"], meta["repo"], meta["commit"], "data/input_queries/query_2601_en.jsonl"), v2
    )
    src_lic = download(gh_urls(meta["owner"], meta["repo"], meta["commit"], "LICENSE"), license_p)
    src_ex = download(
        gh_urls(meta["owner"], meta["repo"], meta["commit"], "point_quality/example_pointwise_usage.py"), example
    )

    splits = {
        "v1": (v1, "data/input_queries/query.jsonl", False),
        "v2_2601": (v2, "data/input_queries/query_2601_en.jsonl", True),
    }
    tasks: list[dict] = []
    golds: list[dict] = []
    split_counts = {}
    for split, (path, rel, dynamic) in splits.items():
        count = 0
        with path.open("r", encoding="utf-8") as f:
            for source_row, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                upstream_id = row.get("id")
                if upstream_id is None:
                    raise ValueError(f"DeepResearchEval {split} line {source_row} missing official id")
                prompt = row["prompt"]
                as_of = extract_as_of(prompt)
                if dynamic and as_of is None:
                    as_of = "2026-02-11"
                source_hash = sha256_text(line)
                task = {
                    "schema_version": "trueeval.research_task.v0.1",
                    "task_id": f"{meta['benchmark_id']}.{split}.{pad_id(upstream_id)}",
                    "benchmark_id": meta["benchmark_id"],
                    "upstream_task_id": str(upstream_id),
                    "split": split,
                    "task_family": "report_research",
                    "input": {
                        "prompt": prompt,
                        "language": row.get("language") or "en",
                        "as_of": as_of,
                        "attachments": [],
                    },
                    "expected_output": {
                        "answer_form": "report",
                        "citation_required": False,
                        "structured_fields": [],
                    },
                    "constraints": {
                        "internet_required": True,
                        "timeout_seconds": 1800,
                        "max_search_calls": None,
                        "allowed_tools": ["web_search", "browser"],
                        "forbidden_domains": [],
                        "required_domains": [],
                    },
                    "provenance": {
                        "source_file": rel,
                        "source_row": source_row,
                        "source_hash": source_hash,
                        "extraction_version": EXTRACTION_VERSION,
                    },
                    "tags": [
                        "long-form",
                        "english-upstream",
                        "not-chinese-formal-set",
                        row.get("topic", "unknown").lower().replace(" ", "-"),
                    ],
                }
                gold = {
                    "schema_version": "trueeval.research_gold.v0.1",
                    "task_id": task["task_id"],
                    "answer_type": "report",
                    "reference_answer": None,
                    "acceptable_answers": [],
                    "unacceptable_answers": [],
                    "claims": [],
                    "temporal_scope": {
                        "valid_as_of": as_of,
                        "valid_from": None,
                        "valid_until": None,
                    },
                    "official_grader_payload": {
                        "id": row.get("id"),
                        "topic": row.get("topic"),
                        "language": row.get("language"),
                        "quality_module": "point_quality",
                        "fact_module": "factual_eval",
                        "general_dimensions": ["Coverage", "Insight", "Instruction-following", "Clarity"],
                        "task_dimensions_policy": "generate_with_official_point_quality_and_freeze",
                        "do_not_invent_claims": True,
                    },
                    "provenance": {
                        "source_file": rel,
                        "source_row": source_row,
                        "source_hash": source_hash,
                    },
                }
                tasks.append(task)
                golds.append(gold)
                count += 1
        split_counts[split] = count

    write_jsonl(out / "tasks.jsonl", tasks)
    write_jsonl(out / "gold.jsonl", golds)
    dump_yaml(
        {
            "schema_version": "trueeval.research_benchmark.v0.1",
            "benchmark_id": meta["benchmark_id"],
            "name": "DeepResearchEval",
            "benchmark_version": meta["commit"],
            "domain": "research",
            "task_family": "report_research",
            "track": "long_form",
            "formal_cn_leaderboard": False,
            "notes": "05 standard: the official English 100-item set is not the Chinese formal long-form set. Quality and fact scores must stay separate.",
            "upstream": {
                "repo_url": "https://github.com/Infinity-AILab/DeepResearchEval",
                "commit_sha": meta["commit"],
                "dataset_path": "data/input_queries/query.jsonl",
                "evaluator_path": "point_quality/ + factual_eval/",
                "license": meta["license"],
                "homepage": meta["homepage"],
            },
            "splits": [
                {
                    "name": "v1",
                    "public_questions": True,
                    "public_gold": False,
                    "task_count": split_counts.get("v1", 0),
                    "notes": "Paper 100-task English set.",
                },
                {
                    "name": "v2_2601",
                    "public_questions": True,
                    "public_gold": False,
                    "task_count": split_counts.get("v2_2601", 0),
                    "notes": "2026-02-11 v2 queries; dynamic; require as_of.",
                },
            ],
            "default_execution": {
                "mode": "submission",
                "timeout_seconds": 1800,
                "max_attempts": 1,
                "internet_required": True,
                "allowed_tools": ["web_search", "browser"],
                "output_contract": "research_answer.v0.1",
            },
            "official_metrics": ["official.quality_score", "official.fact_ratio"],
            "trueeval_metrics": [
                "trueeval.citation_correctness",
                "trueeval.citation_completeness",
                "trueeval.source_quality",
                "trueeval.temporal_validity",
            ],
        },
        out / "benchmark.yaml",
    )
    dump_yaml(
        {
            "schema_version": "trueeval.research_rubric.v0.1",
            "rubric_id": "deepresearcheval.default.v1",
            "benchmark_id": meta["benchmark_id"],
            "gates": [
                {
                    "metric_id": "trueeval.execution_success",
                    "condition": "status == completed",
                    "on_fail": "exclude_as_system_failure",
                }
            ],
            "metrics": [
                {
                    "metric_id": "official.quality_score",
                    "namespace": "official",
                    "role": "score",
                    "method": "upstream_executable",
                    "adapter": "adapters/official_quality.py",
                    "inputs": ["prediction.final_answer", "gold.official_grader_payload"],
                    "range": [0.0, 10.0],
                    "weight": 1.0,
                    "missing_policy": "error",
                    "notes": "Report general dimensions and task dimensions separately. Do not fuse with fact_ratio.",
                },
                {
                    "metric_id": "official.fact_ratio",
                    "namespace": "official",
                    "role": "score",
                    "method": "upstream_executable",
                    "adapter": "adapters/official_factcheck.py",
                    "inputs": ["prediction.final_answer", "gold.official_grader_payload"],
                    "range": [0.0, 1.0],
                    "weight": 0.0,
                    "missing_policy": "not_observable",
                    "notes": "Parallel fact board only. Unknown is neither FAIL nor PASS.",
                },
                {
                    "metric_id": "trueeval.citation_correctness",
                    "namespace": "trueeval",
                    "role": "diagnostic",
                    "method": "claim_citation_entailment",
                    "inputs": ["prediction.claims", "prediction.citations", "artifacts.search_results"],
                    "range": [0.0, 1.0],
                    "weight": 0.0,
                    "missing_policy": "not_observable",
                },
                {
                    "metric_id": "trueeval.citation_completeness",
                    "namespace": "trueeval",
                    "role": "diagnostic",
                    "method": "weighted_claim_coverage",
                    "inputs": ["prediction.claims", "prediction.citations"],
                    "range": [0.0, 1.0],
                    "weight": 0.0,
                    "missing_policy": "not_observable",
                },
                {
                    "metric_id": "trueeval.source_quality",
                    "namespace": "trueeval",
                    "role": "diagnostic",
                    "method": "source_quality_rubric",
                    "inputs": ["prediction.citations"],
                    "range": [0.0, 1.0],
                    "weight": 0.0,
                    "missing_policy": "not_observable",
                },
                {
                    "metric_id": "trueeval.temporal_validity",
                    "namespace": "trueeval",
                    "role": "gate",
                    "applies_when": "task.input.as_of != null",
                    "method": "evidence_date_check",
                    "inputs": ["task.input.as_of", "prediction.claims", "prediction.citations"],
                    "threshold": 1.0,
                    "missing_policy": "fail",
                },
            ],
            "aggregation": {
                "official_primary": "official.quality_score",
                "trueeval_composite": None,
                "leaderboard_metric": None,
                "leaderboard_policy": "quality board and fact board stay separate",
                "system_failures": "report_separately",
                "confidence_interval": {"method": "bootstrap", "samples": 10000, "confidence": 0.95},
            },
        },
        out / "rubric.yaml",
    )
    lock = {
        "schema_version": "trueeval.upstream_lock.v0.1",
        "benchmark_id": meta["benchmark_id"],
        "extracted_at": EXTRACTED_AT,
        "extraction_version": EXTRACTION_VERSION,
        "upstream": {
            "repo_url": "https://github.com/Infinity-AILab/DeepResearchEval",
            "commit_sha": meta["commit"],
            "license": meta["license"],
        },
        "files": [
            {"path": "data/input_queries/query.jsonl", "sha256": sha256_file(v1), "download_url": src_v1},
            {"path": "data/input_queries/query_2601_en.jsonl", "sha256": sha256_file(v2), "download_url": src_v2},
            {"path": "LICENSE", "sha256": sha256_file(license_p), "download_url": src_lic},
            {
                "path": "point_quality/example_pointwise_usage.py",
                "sha256": sha256_file(example),
                "download_url": src_ex,
            },
        ],
        "task_count": len(tasks),
        "split_counts": split_counts,
        "gold_policy": "No official short gold. Keep official quality/fact graders; do not invent claims.",
    }
    dump_yaml(lock, out / "upstream.lock.yaml")
    shutil.copy2(example, out / "adapters" / "official_quality_example.py")
    return lock


def assert_no_leak(tasks_path: Path, golds_path: Path) -> None:
    forbidden = {
        "reference_answer",
        "acceptable_answers",
        "claims",
        "official_grader_payload",
        "judge_prompt",
    }
    with tasks_path.open(encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            row = json.loads(line)
            leaked = forbidden.intersection(row)
            if leaked:
                raise AssertionError(f"{tasks_path} line {i} leaked gold fields: {leaked}")
            blob = json.dumps(row, ensure_ascii=False)
            if "reference_answer" in blob:
                raise AssertionError(f"{tasks_path} line {i} contains reference_answer text")
    gold_ids = []
    with golds_path.open(encoding="utf-8") as f:
        for line in f:
            gold_ids.append(json.loads(line)["task_id"])
    task_ids = []
    with tasks_path.open(encoding="utf-8") as f:
        for line in f:
            task_ids.append(json.loads(line)["task_id"])
    if task_ids != gold_ids:
        raise AssertionError(f"task_id mismatch between {tasks_path} and {golds_path}")
    if len(set(task_ids)) != len(task_ids):
        raise AssertionError(f"duplicate task_id in {tasks_path}")


def main() -> None:
    BENCH_ROOT.mkdir(parents=True, exist_ok=True)
    locks = {
        "browsecomp-zh": ingest_browsecomp(),
        "xbench-deepsearch": ingest_xbench(),
        "deepresearcheval": ingest_deepresearcheval(),
    }
    for name in locks:
        assert_no_leak(BENCH_ROOT / name / "tasks.jsonl", BENCH_ROOT / name / "gold.jsonl")
    summary = {
        "extracted_at": EXTRACTED_AT,
        "extraction_version": EXTRACTION_VERSION,
        "benchmarks": {
            name: {
                "commit_sha": lock["upstream"]["commit_sha"],
                "task_count": lock["task_count"],
                "split_counts": lock.get("split_counts"),
            }
            for name, lock in locks.items()
        },
    }
    dump_yaml(summary, BENCH_ROOT / "INGEST_SUMMARY.yaml")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

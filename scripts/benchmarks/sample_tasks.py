"""Draw a reproducible task sample for smoke runs.

Writes task_id only. Plaintext prompts of BrowseComp-ZH and xbench must not
leave benchmarks/<name>/tasks.jsonl, so the runner resolves prompts at run time.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_GROUPS = [
    ("browsecomp-zh", "test"),
    ("xbench-deepsearch", "2505"),
    ("deepresearcheval", "v1"),
]


def load_task_ids(benchmark_id: str, split: str) -> list[str]:
    path = ROOT / "benchmarks" / benchmark_id / "tasks.jsonl"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} 不存在；受保护数据集需先执行 "
            "scripts/benchmarks/decrypt_encrypted_to_trueeval.py"
        )
    ids = [
        row["task_id"]
        for row in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line)
        if row["split"] == split
    ]
    if not ids:
        raise ValueError(f"{benchmark_id} 没有 split={split} 的题目")
    return ids


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-benchmark", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260819)
    parser.add_argument("--name", default="doubao-smoke")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    groups = []
    for benchmark_id, split in DEFAULT_GROUPS:
        ids = sorted(load_task_ids(benchmark_id, split))
        if len(ids) < args.per_benchmark:
            raise ValueError(f"{benchmark_id}/{split} 只有 {len(ids)} 题，不足 {args.per_benchmark} 题")
        picked = random.Random(f"{args.seed}:{benchmark_id}:{split}").sample(ids, args.per_benchmark)
        groups.append(
            {
                "benchmark_id": benchmark_id,
                "split": split,
                "population": len(ids),
                "task_ids": sorted(picked),
            }
        )

    sample = {
        "schema_version": "trueeval.task_sample.v0.1",
        "sample_id": f"{args.name}-{args.per_benchmark * len(groups)}",
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "seed": args.seed,
        "per_benchmark": args.per_benchmark,
        "groups": groups,
    }

    out = Path(args.out) if args.out else ROOT / "benchmarks" / "samples" / f"{sample['sample_id']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(sample, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    total = sum(len(g["task_ids"]) for g in groups)
    print(f"{out.relative_to(ROOT)}: {total} tasks")
    for g in groups:
        print(f"  {g['benchmark_id']}/{g['split']}: {len(g['task_ids'])} / {g['population']}")


if __name__ == "__main__":
    main()

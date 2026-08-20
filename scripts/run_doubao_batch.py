"""Run a sampled task set against the Doubao web adapter, one task at a time.

The adapter drives a single persistent Chrome profile, so runs must stay
sequential. Prompts are resolved from tasks.jsonl at run time and written to a
per-task file, so no plaintext prompt ever reaches the command line or the log.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "src" / "cli" / "doubao.ts"
SUCCESS_STATUSES = {"completed", "probe_completed"}


def profile_holders(profile_dir: Path) -> list[int]:
    if sys.platform != "win32":
        return []
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name='msedge.exe' or Name='chrome.exe'\" | "
        f"Where-Object {{ $_.CommandLine -like '*{profile_dir}*' }} | "
        "ForEach-Object { $_.ProcessId }"
    )
    done = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
    )
    return [int(line) for line in done.stdout.split() if line.strip().isdigit()]


def release_profile_lock(profile_dir: Path, timeout_seconds: int = 20) -> int:
    """Free the browser profile's singleton lock before launching.

    Edge relaunches itself as a detached instance after Playwright closes the
    persistent context. That stale instance owns the user-data-dir lock, so the
    next launch hands control to it and exits with code 21 before any page
    opens. Matching is confined to this one automation profile path, so regular
    browser windows on the default profile are never touched.
    """
    holders = profile_holders(profile_dir)
    if not holders:
        return 0
    if sys.platform == "win32":
        args = [arg for pid in holders for arg in ("/PID", str(pid))]
        subprocess.run(["taskkill", "/F", *args], capture_output=True, text=True)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not profile_holders(profile_dir):
            break
        time.sleep(1)
    time.sleep(3)
    return len(holders)


def load_prompts(benchmark_id: str) -> dict[str, str]:
    path = ROOT / "benchmarks" / benchmark_id / "tasks.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"{path} 不存在；受保护数据集需先解密生成")
    prompts = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        prompts[row["task_id"]] = row["input"]["prompt"]
    return prompts


def plan_from_sample(sample_path: Path) -> list[dict]:
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    plan = []
    for group in sample["groups"]:
        prompts = load_prompts(group["benchmark_id"])
        for task_id in group["task_ids"]:
            if task_id not in prompts:
                raise KeyError(f"{task_id} 不在 {group['benchmark_id']}/tasks.jsonl 中")
            plan.append(
                {
                    "task_id": task_id,
                    "benchmark_id": group["benchmark_id"],
                    "split": group["split"],
                    "prompt": prompts[task_id],
                }
            )
    return plan


def find_result(run_root: Path, task_id: str) -> dict | None:
    safe = task_id.replace("/", "-")
    candidates = sorted(
        (p for p in run_root.glob(f"{safe}-*/result.json")),
        key=lambda p: p.stat().st_mtime,
    )
    if not candidates:
        return None
    return json.loads(candidates[-1].read_text(encoding="utf-8"))


def run_task(item: dict, run_root: Path, args: argparse.Namespace, first: bool) -> dict:
    freed = release_profile_lock(Path(args.profile_dir))
    if freed:
        print(f"已释放 {freed} 个占用浏览器 Profile 的残留进程", flush=True)
    task_dir = run_root / "prompts"
    task_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = task_dir / f"{item['task_id'].replace('/', '-')}.txt"
    prompt_file.write_text(item["prompt"], encoding="utf-8")

    cmd = [
        "node",
        "--import",
        "tsx",
        str(CLI),
        "--prompt-file",
        str(prompt_file),
        "--task-id",
        item["task_id"],
        "--artifacts-dir",
        str(run_root),
        "--timeout-seconds",
        str(args.timeout_seconds),
        "--login-timeout-seconds",
        str(args.login_timeout_seconds if first else 120),
        "--browser-channel",
        args.browser_channel,
        "--profile-dir",
        str(args.profile_dir),
    ]
    if args.chat_mode:
        cmd.append("--chat-mode")

    started = datetime.now(timezone.utc)
    print(f"\n=== {item['task_id']} ({item['benchmark_id']}/{item['split']}) 开始 {started:%H:%M:%S} ===", flush=True)
    completed = subprocess.run(cmd, cwd=ROOT)
    result = find_result(run_root, item["task_id"])
    status = result["status"] if result else "no_result_file"
    latency = result["usage"]["latency_ms"] if result else None
    error = result.get("error") if result else None
    print(
        f"=== {item['task_id']} 结束 status={status} "
        f"exit={completed.returncode} 用时={round((latency or 0) / 60000, 1)}min ===",
        flush=True,
    )
    return {
        "task_id": item["task_id"],
        "benchmark_id": item["benchmark_id"],
        "split": item["split"],
        "status": status,
        "exit_code": completed.returncode,
        "latency_ms": latency,
        "answer_chars": len(result["final_answer"] or "") if result else 0,
        "citations": len(result["citations"]) if result else 0,
        "result_dir": result["artifacts"]["result_dir"] if result else None,
        "error": error,
        "started_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", default="benchmarks/samples/doubao-smoke-15.json")
    parser.add_argument("--run-root", default=None, help="默认 artifacts/doubao-batch/<sample_id>-<时间戳>")
    parser.add_argument("--timeout-seconds", type=int, default=2700)
    parser.add_argument("--login-timeout-seconds", type=int, default=600)
    parser.add_argument("--browser-channel", default="msedge", help="本机只装了 Edge 时用 msedge")
    parser.add_argument("--profile-dir", default=str(ROOT / ".trueeval" / "profiles" / "doubao"))
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 题，用于冒烟验证")
    parser.add_argument("--only", default=None, help="只跑指定 benchmark_id")
    parser.add_argument("--chat-mode", action="store_true", help="用普通对话代替深入研究")
    parser.add_argument(
        "--max-consecutive-failures",
        type=int,
        default=2,
        help="连续失败达到该次数即中止；登录或 UI 失效时继续跑只会浪费时间",
    )
    args = parser.parse_args()

    sample_path = Path(args.sample)
    if not sample_path.is_absolute():
        sample_path = ROOT / sample_path
    plan = plan_from_sample(sample_path)
    if args.only:
        plan = [item for item in plan if item["benchmark_id"] == args.only]
    if args.limit:
        plan = plan[: args.limit]
    if not plan:
        raise SystemExit("没有待运行的题目")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    sample_id = json.loads(sample_path.read_text(encoding="utf-8"))["sample_id"]
    run_root = Path(args.run_root) if args.run_root else ROOT / "artifacts" / "doubao-batch" / f"{sample_id}-{stamp}"
    if not run_root.is_absolute():
        run_root = ROOT / run_root
    run_root.mkdir(parents=True, exist_ok=True)

    print(f"批次目录：{run_root}")
    print(f"待运行 {len(plan)} 题，串行执行，单题上限 {args.timeout_seconds} 秒")

    records: list[dict] = []
    consecutive = 0
    aborted = None
    for index, item in enumerate(plan):
        record = run_task(item, run_root, args, first=index == 0)
        records.append(record)
        summary_path = run_root / "summary.json"
        summary_path.write_text(
            json.dumps(
                {
                    "sample_id": sample_id,
                    "run_root": str(run_root),
                    "planned": len(plan),
                    "records": records,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if record["status"] in SUCCESS_STATUSES:
            consecutive = 0
            continue
        consecutive += 1
        if consecutive >= args.max_consecutive_failures:
            aborted = f"连续 {consecutive} 题失败，已中止；修复后可重跑剩余题目"
            print(f"\n{aborted}", flush=True)
            break

    ok = sum(1 for r in records if r["status"] in SUCCESS_STATUSES)
    print(f"\n完成 {ok}/{len(records)} 题成功，计划 {len(plan)} 题。汇总：{run_root / 'summary.json'}")
    if aborted:
        sys.exit(2)
    if ok != len(plan):
        sys.exit(1)


if __name__ == "__main__":
    main()

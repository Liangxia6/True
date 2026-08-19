#!/usr/bin/env python3
"""Fetch the exact official DeepResearchEval source locked by TrueEval."""

import argparse
import pathlib
import subprocess

REPO = "https://github.com/Infinity-AILab/DeepResearchEval.git"
COMMIT = "121d4c34050d0e3b0ee441c52c4467cf58ab941e"


def run(*args: str, cwd: pathlib.Path | None = None) -> str:
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=".trueeval/upstream/deepresearcheval")
    args = parser.parse_args()
    output = pathlib.Path(args.output).resolve()
    if not output.exists():
        output.parent.mkdir(parents=True, exist_ok=True)
        subprocess.check_call(["git", "clone", "--filter=blob:none", REPO, str(output)])
    remote = run("git", "remote", "get-url", "origin", cwd=output)
    if remote not in (REPO, REPO.removesuffix(".git")):
        raise RuntimeError(f"Unexpected origin: {remote}")
    subprocess.check_call(["git", "fetch", "origin", COMMIT], cwd=output)
    subprocess.check_call(["git", "checkout", "--detach", COMMIT], cwd=output)
    actual = run("git", "rev-parse", "HEAD", cwd=output)
    if actual != COMMIT:
        raise RuntimeError(f"Commit verification failed: {actual}")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

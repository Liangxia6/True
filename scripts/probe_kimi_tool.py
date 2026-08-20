"""Probe kimi-k2.6 multi-round behavior + proxy/timeout diagnosis."""

import os
import traceback
from pathlib import Path

import httpx


def load_dotenv(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_dotenv()

API_KEY = os.environ["MOONSHOT_API_KEY"]
BASE = "https://api.moonshot.ai/v1/chat/completions"
WEB_SEARCH_TOOL = {"type": "builtin_function", "function": {"name": "$web_search"}}

PROMPT = (
    "From January 2023 to June 2025, how have semiconductor export restrictions "
    "affected state media's broadcast technology, surveillance capacity, and "
    "international narrative control in China and Russia? Write a full report."
)


def make_client(trust_env: bool) -> httpx.Client:
    return httpx.Client(trust_env=trust_env, timeout=600)


def chat(client, messages, use_tools):
    payload = {"model": "kimi-k2.6", "messages": messages, "thinking": {"type": "disabled"}}
    if use_tools:
        payload["tools"] = [WEB_SEARCH_TOOL]
    r = client.post(BASE, json=payload, headers={"Authorization": f"Bearer {API_KEY}"})
    r.raise_for_status()
    return r.json()


def run(trust_env: bool, max_rounds=6):
    print(f"\n########## trust_env={trust_env} ##########")
    client = make_client(trust_env)
    messages = [{"role": "user", "content": PROMPT}]
    import time as _t

    for i in range(max_rounds):
        allow_tools = i < max_rounds - 1
        t0 = _t.time()
        try:
            body = chat(client, messages, allow_tools)
        except Exception as exc:  # noqa: BLE001
            dt = _t.time() - t0
            print(f"[round {i}] EXC after {dt:.1f}s: {type(exc).__module__}.{type(exc).__name__}: {exc}")
            traceback.print_exc()
            return
        dt = _t.time() - t0
        ch = body["choices"][0]
        msg = ch["message"]
        finish = ch.get("finish_reason")
        tcs = msg.get("tool_calls") or []
        content = msg.get("content") or ""
        print(f"[round {i}] {dt:.1f}s finish={finish} tool_calls={len(tcs)} content_len={len(content)}")
        if allow_tools and tcs:
            messages.append(msg)
            for c in tcs:
                fn = c.get("function") or {}
                messages.append({
                    "role": "tool",
                    "tool_call_id": c.get("id"),
                    "name": fn.get("name") or "$web_search",
                    "content": fn.get("arguments") or "{}",
                })
            continue
        print("  content head:", content[:200].replace("\n", " "))
        if len(content) >= 400:
            print("  >>> FINAL report length:", len(content))
        return
    print("  exhausted rounds")


if __name__ == "__main__":
    run(trust_env=False)

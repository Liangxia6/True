"""Link Works + source fetch (Onweller et al. §3.3.1)."""

from __future__ import annotations

import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass

from trueeval.cited_not_verified.prompts import CONTENT_TRUNCATE_CHARS

USER_AGENT = "TrueEval-cited-not-verified/0.1 (research citation check)"
DEFAULT_TIMEOUT_S = 15


@dataclass
class FetchResult:
    url: str
    link_works: int
    url_content: str
    status_code: int | None
    error: str | None


def fetch_url(
    url: str,
    *,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    truncate_chars: int = CONTENT_TRUNCATE_CHARS,
) -> FetchResult:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s, context=ctx) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            if status >= 400 or not text.strip():
                return FetchResult(url, 0, "", status, f"http_{status}_or_empty")
            return FetchResult(url, 1, text[:truncate_chars], status, None)
    except urllib.error.HTTPError as exc:
        return FetchResult(url, 0, "", int(exc.code), f"http_{exc.code}")
    except OSError as exc:
        return FetchResult(url, 0, "", None, type(exc).__name__)

"""Thin HTTP client for the lo-mcp LibreOffice extension.

Ordinary network I/O to a local port — not a subprocess spawn, so nothing
here is subject to macOS Launch Constraints. The extension does the actual
UNO work inside the already-running, independently-launched soffice process.
"""

import json
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8794"
TIMEOUT = 15


class LoMcpError(RuntimeError):
    """The extension ran the operation and reported an error."""


class NotConnected(RuntimeError):
    """Could not reach the lo-mcp LibreOffice extension."""


def ping(base_url: str = DEFAULT_URL, timeout: float = 3) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url}/ping", timeout=timeout) as resp:
            return bool(json.loads(resp.read())["ok"])
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def call(op: str, args: dict | None = None, base_url: str = DEFAULT_URL, timeout: float = TIMEOUT):
    body = json.dumps({"op": op, "args": args or {}}).encode("utf-8")
    req = urllib.request.Request(
        base_url,
        data=body,
        headers={"Content-Type": "application/json", "X-Lo-Mcp-Client": "1"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        payload = json.loads(e.read())
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise NotConnected(
            f"Cannot reach lo-mcp's LibreOffice extension at {base_url}. "
            "Launch LibreOffice, then use the lo-mcp menu > Start Server."
        ) from e

    if not payload.get("ok"):
        raise LoMcpError(payload.get("error", "unknown error"))
    return payload["result"]

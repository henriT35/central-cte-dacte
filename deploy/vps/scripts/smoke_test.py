#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import ssl
import urllib.request


def fetch(url: str) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "CentralCTe-MVP8-SmokeTest/1.0"})
    with urllib.request.urlopen(request, timeout=20, context=ssl.create_default_context()) as response:
        return response.status, response.read(256 * 1024).decode("utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    results = {}
    for name, path in (("health", "/api/health"), ("ready", "/api/ready"), ("home", "/")):
        status, body = fetch(base + path)
        results[name] = {"status": status, "bytes": len(body.encode("utf-8"))}
        if status != 200:
            raise SystemExit(json.dumps(results, indent=2))
    print(json.dumps({"ok": True, "base_url": base, "checks": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

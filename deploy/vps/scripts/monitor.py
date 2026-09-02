#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

URL = os.environ.get("MONITOR_URL", "http://app:8765/api/ready")
INTERVAL = max(10, int(os.environ.get("MONITOR_INTERVAL_SECONDS", "60")))
THRESHOLD = max(1, int(os.environ.get("MONITOR_FAILURE_THRESHOLD", "3")))
WEBHOOK = os.environ.get("ALERT_WEBHOOK_URL", "").strip()
STATE_PATH = Path(os.environ.get("MONITOR_STATE_PATH", "/monitor/last_status.json"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def post_webhook(payload: dict) -> None:
    if not WEBHOOK:
        return
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(WEBHOOK, data=body, method="POST", headers={"Content-Type": "application/json"})
    urllib.request.urlopen(request, timeout=15).read()


def check() -> tuple[bool, dict]:
    started = time.monotonic()
    try:
        with urllib.request.urlopen(URL, timeout=15) as response:
            body = json.loads(response.read().decode("utf-8"))
            ok = response.status == 200 and bool(body.get("ok"))
            return ok, {"status": response.status, "latency_ms": round((time.monotonic() - started) * 1000, 1), "body": body}
    except Exception as exc:
        return False, {"error": str(exc), "latency_ms": round((time.monotonic() - started) * 1000, 1)}


def save_state(payload: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(STATE_PATH)


def main() -> int:
    failures = 0
    alert_open = False
    while True:
        ok, detail = check()
        failures = 0 if ok else failures + 1
        state = {"time": now_iso(), "ok": ok, "consecutive_failures": failures, "detail": detail}
        save_state(state)
        print(json.dumps({"event": "monitor.check", **state}, ensure_ascii=False), flush=True)
        if not ok and failures >= THRESHOLD and not alert_open:
            try:
                post_webhook({"event": "central_cte.down", **state})
                alert_open = True
            except Exception as exc:
                print(json.dumps({"event": "monitor.alert_failure", "error": str(exc)}, ensure_ascii=False), flush=True)
        elif ok and alert_open:
            try:
                post_webhook({"event": "central_cte.recovered", **state})
            finally:
                alert_open = False
        time.sleep(INTERVAL)


if __name__ == "__main__":
    raise SystemExit(main())

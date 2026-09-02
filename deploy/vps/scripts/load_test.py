#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import json
import statistics
import time
import urllib.request
from collections import Counter


def request_once(url: str, timeout: float) -> tuple[int, float, int]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read()
            return response.status, (time.perf_counter() - started) * 1000, len(body)
    except Exception:
        return 0, (time.perf_counter() - started) * 1000, 0


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser(description="Teste leve de carga da Central CT-e")
    parser.add_argument("url", help="Ex.: https://central.seudominio.com.br/api/health")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()
    total = max(1, min(args.requests, 10000))
    concurrency = max(1, min(args.concurrency, 200))
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        results = list(executor.map(lambda _: request_once(args.url, args.timeout), range(total)))
    elapsed = time.perf_counter() - started
    statuses = Counter(result[0] for result in results)
    latencies = [result[1] for result in results]
    summary = {
        "url": args.url,
        "requests": total,
        "concurrency": concurrency,
        "elapsed_seconds": round(elapsed, 3),
        "requests_per_second": round(total / elapsed, 2) if elapsed else 0,
        "statuses": dict(statuses),
        "latency_ms": {
            "min": round(min(latencies), 2),
            "average": round(statistics.fmean(latencies), 2),
            "p50": round(percentile(latencies, 0.50), 2),
            "p95": round(percentile(latencies, 0.95), 2),
            "p99": round(percentile(latencies, 0.99), 2),
            "max": round(max(latencies), 2),
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if statuses.get(200, 0) == total else 1


if __name__ == "__main__":
    raise SystemExit(main())

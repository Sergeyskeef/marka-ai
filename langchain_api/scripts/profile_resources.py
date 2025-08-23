"""
Profile process CPU and memory usage over time and save metrics.
Run inside the container: python scripts/profile_resources.py --seconds 60 --out docs/metrics
"""
import argparse
import json
import os
import time
from datetime import datetime

import psutil


def sample_process_metrics(interval_s: float, duration_s: int) -> dict:
    process = psutil.Process()
    samples = []
    start = time.time()
    # First call to cpu_percent initializes, second gives a valid value
    process.cpu_percent(interval=None)
    while (time.time() - start) < duration_s:
        rss = process.memory_info().rss
        cpu = process.cpu_percent(interval=None)
        samples.append({
            "ts": time.time(),
            "rss_bytes": rss,
            "cpu_percent": cpu,
        })
        time.sleep(interval_s)
    if not samples:
        return {"samples": [], "summary": {}}
    rss_values = [s["rss_bytes"] for s in samples]
    cpu_values = [s["cpu_percent"] for s in samples]
    summary = {
        "num_samples": len(samples),
        "rss_bytes_avg": sum(rss_values) / len(rss_values),
        "rss_bytes_max": max(rss_values),
        "cpu_percent_avg": sum(cpu_values) / len(cpu_values),
        "cpu_percent_max": max(cpu_values),
    }
    return {"samples": samples, "summary": summary}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--out", type=str, default="docs/metrics")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    result = sample_process_metrics(args.interval, args.seconds)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(args.out, f"profile_{ts}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print({
        "saved": out_path,
        **result["summary"],
    })


if __name__ == "__main__":
    main()
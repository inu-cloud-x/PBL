#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def deterministic_value(model: dict, source_idx: int, target_idx: int) -> tuple[int, float, int]:
    latency_values = [int(value) for value in model.get("latency_ms_values", [10, 20, 30, 40])]
    loss_values = [float(value) for value in model.get("loss_pct_values", [0.0, 0.1])]
    bandwidth_values = [int(value) for value in model.get("bandwidth_mbps_values", [50])]
    seed = int(model.get("seed", 17))
    mixed = (source_idx * 1103515245 + target_idx * 12345 + seed) & 0x7FFFFFFF
    latency = latency_values[mixed % len(latency_values)]
    loss = loss_values[(mixed // len(latency_values)) % len(loss_values)]
    bandwidth = bandwidth_values[(mixed // (len(latency_values) * len(loss_values))) % len(bandwidth_values)]
    return latency, loss, bandwidth


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("topology", type=Path)
    parser.add_argument("--sample", type=int, default=200000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    topology = json.loads(args.topology.read_text(encoding="utf-8"))
    model = topology["matrix_model"]
    nodes = topology["nodes"]
    n = len(nodes)
    total = n * (n - 1)
    limit = min(args.sample, total)
    latencies: Counter[int] = Counter()
    losses: Counter[str] = Counter()
    bandwidths: Counter[int] = Counter()
    examples = []
    count = 0
    for source_idx in range(n):
        for offset in range(1, n):
            target_idx = (source_idx + offset) % n
            latency, loss, bandwidth = deterministic_value(model, source_idx, target_idx)
            latencies[latency] += 1
            losses[str(loss)] += 1
            bandwidths[bandwidth] += 1
            if len(examples) < 12:
                examples.append({
                    "source": nodes[source_idx]["id"],
                    "target": nodes[target_idx]["id"],
                    "latency_ms": latency,
                    "loss_pct": loss,
                    "bandwidth_mbps": bandwidth,
                })
            count += 1
            if count >= limit:
                break
        if count >= limit:
            break

    payload = {
        "nodes": n,
        "logical_links": total,
        "sampled_links": count,
        "latency_ms_distribution": dict(sorted(latencies.items())),
        "loss_pct_distribution": dict(sorted(losses.items(), key=lambda item: float(item[0]))),
        "bandwidth_mbps_distribution": dict(sorted(bandwidths.items())),
        "examples": examples,
    }
    text = json.dumps(payload, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
        print(args.output)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

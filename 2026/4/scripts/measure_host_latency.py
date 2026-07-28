#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from statistics import median


def run(command: list[str]) -> str:
    return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT)


def ping_ms(target: str, count: int) -> float:
    output = run(["ping", "-c", str(count), "-q", target])
    match = re.search(r"= [0-9.]+/([0-9.]+)/[0-9.]+/[0-9.]+ ms", output)
    if not match:
        samples = [float(value) for value in re.findall(r"time=([0-9.]+) ms", output)]
        if samples:
            return median(samples)
        raise RuntimeError(f"could not parse ping output for {target}: {output}")
    return float(match.group(1))


def remote_ping_ms(ssh_target: str, target: str, count: int) -> float:
    output = run(["ssh", ssh_target, "ping", "-c", str(count), "-q", target])
    match = re.search(r"= [0-9.]+/([0-9.]+)/[0-9.]+/[0-9.]+ ms", output)
    if not match:
        raise RuntimeError(f"could not parse remote ping output for {ssh_target}->{target}: {output}")
    return float(match.group(1))


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure host-to-host base latency and write it into a topology JSON.")
    parser.add_argument("topology", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--count", type=int, default=5)
    args = parser.parse_args()

    topology = json.loads(args.topology.read_text(encoding="utf-8"))
    hosts = topology["hosts"]
    table: dict[str, int] = {}
    for source in hosts:
        for target in hosts:
            if source["name"] == target["name"]:
                continue
            ssh_user = source.get("ssh_user", "")
            ssh_target = f"{ssh_user}@{source['address']}" if ssh_user else ""
            if ssh_target:
                latency = remote_ping_ms(ssh_target, target["address"], args.count)
            else:
                latency = ping_ms(target["address"], args.count)
            # Round up so the physical link is never under-accounted.
            table[f"{source['name']}->{target['name']}"] = max(1, round(latency + 0.499))

    topology["host_latency_policy"] = topology.get("host_latency_policy", "subtract_from_emulated_delay")
    topology["host_latency_ms"] = table
    output = args.output or args.topology
    output.write_text(json.dumps(topology, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "host_latency_ms": table}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

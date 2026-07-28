#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def flatten_class_plan(path: Path) -> list[dict[str, Any]]:
    data = load_json(path)
    rows: list[dict[str, Any]] = []
    for class_id, entries in data.items():
        for entry in entries:
            rows.append({"class_id": class_id, **entry})
    return rows


def parse_tc_script(path: Path) -> dict[str, dict[str, Any]]:
    sections: dict[str, dict[str, Any]] = {}
    current: str | None = None
    qdisc_re = re.compile(
        r"tc qdisc add dev \"\$veth\" parent 1:(?P<band>\d+) handle \d+: netem delay (?P<latency>\d+)ms(?P<rest>.*?)(?: \|\| true)?$"
    )
    filter_re = re.compile(
        r"match ip dst (?P<dst>[0-9.]+)/32 match ip dport (?P<port>\d+) 0xffff flowid 1:(?P<band>\d+)"
    )
    fallback_re = re.compile(
        r"tc qdisc replace dev eth0 root netem delay (?P<latency>\d+)ms(?P<rest>.*)$"
    )
    container_re = re.compile(r"^container=(?P<container>.+)$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = container_re.match(line)
        if match:
            current = match.group("container").strip("'\"")
            sections[current] = {"classes": {}, "filters": {}, "fallback": None}
            continue
        if not current:
            continue
        match = qdisc_re.search(line)
        if match:
            rest = match.group("rest")
            loss_match = re.search(r"loss ([0-9.]+)%", rest)
            rate_match = re.search(r"rate (\d+)mbit", rest)
            sections[current]["classes"][int(match.group("band"))] = {
                "latency_ms": int(match.group("latency")),
                "loss_pct": float(loss_match.group(1)) if loss_match else 0.0,
                "bandwidth_mbps": int(rate_match.group(1)) if rate_match else None,
            }
            continue
        match = filter_re.search(line)
        if match:
            sections[current]["filters"][(match.group("dst"), int(match.group("port")))] = int(match.group("band"))
            continue
        match = fallback_re.search(line)
        if match:
            rest = match.group("rest")
            loss_match = re.search(r"loss ([0-9.]+)%", rest)
            rate_match = re.search(r"rate (\d+)mbit", rest)
            sections[current]["fallback"] = {
                "handle": None,
                "latency_ms": int(match.group("latency")),
                "loss_pct": float(loss_match.group(1)) if loss_match else 0.0,
                "bandwidth_mbps": int(rate_match.group(1)) if rate_match else None,
                "scope": "container-eth0-root",
            }
    return sections


def expected_attrs(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "latency_ms": int(row["latency_ms"]),
        "loss_pct": float(row.get("loss_pct", 0.0)),
        "bandwidth_mbps": row.get("bandwidth_mbps"),
    }


def attrs_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        int(left["latency_ms"]) == int(right["latency_ms"])
        and abs(float(left.get("loss_pct", 0.0)) - float(right.get("loss_pct", 0.0))) < 1e-9
    )


def verify_host(project: str, host: dict[str, Any], static_ips: dict[str, str], sample_limit: int) -> dict[str, Any]:
    rows = flatten_class_plan(Path(host["class_plan"]))
    sections = parse_tc_script(Path(host["tc_script"]))
    ok = 0
    missing_filter = 0
    missing_class = 0
    mismatch = 0
    samples = []
    failures = []
    for row in rows:
        container = f"{project}-{row['source']}"
        target_ip = static_ips.get(row["target"], "")
        section = sections.get(container)
        applied_band = None
        applied_attrs = None
        status = "ok"
        if not section or not target_ip:
            missing_filter += 1
            status = "missing_filter"
        else:
            applied_band = section["filters"].get((target_ip, 9000))
            if applied_band is None and section.get("fallback") is not None:
                applied_band = "container-eth0-root"
                applied_attrs = section.get("fallback")
                if attrs_match(expected_attrs(row), applied_attrs):
                    ok += 1
                else:
                    mismatch += 1
                    status = "mismatch"
            elif applied_band is None:
                missing_filter += 1
                status = "missing_filter"
            else:
                applied_attrs = section["classes"].get(applied_band)
                if applied_attrs is None:
                    missing_class += 1
                    status = "missing_class"
                elif attrs_match(expected_attrs(row), applied_attrs):
                    ok += 1
                else:
                    mismatch += 1
                    status = "mismatch"
        proof = {
            "source": row["source"],
            "target": row["target"],
            "target_ip": target_ip,
            "matrix_original_latency_ms": row.get("original_latency_ms"),
            "expected": expected_attrs(row),
            "applied_band": applied_band,
            "applied": applied_attrs,
            "status": status,
        }
        if status == "ok" and len(samples) < sample_limit:
            samples.append(proof)
        elif status != "ok" and len(failures) < sample_limit:
            failures.append(proof)
    return {
        "name": host["name"],
        "class_plan": host["class_plan"],
        "tc_script": host["tc_script"],
        "expected_pairs": len(rows),
        "verified_pairs": ok,
        "missing_filter": missing_filter,
        "missing_class": missing_class,
        "mismatch": mismatch,
        "sample_verified_pairs": samples,
        "sample_failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify that generated matrix latency classes are represented in tc/eBPF application scripts.")
    parser.add_argument("placement", type=Path, help="placement.json generated by distributed_emulator.py plan")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sample", type=int, default=10)
    args = parser.parse_args()

    plan = load_json(args.placement)
    project = plan["project"]
    static_ips = plan.get("static_ips", {})
    hosts = [verify_host(project, host, static_ips, args.sample) for host in plan["hosts"]]
    total_expected = sum(host["expected_pairs"] for host in hosts)
    total_verified = sum(host["verified_pairs"] for host in hosts)
    payload = {
        "project": project,
        "rule_mode": plan.get("rule_mode"),
        "quantization_ms": plan.get("quantization_ms"),
        "matrix_evidence_type": "generated-system-configuration",
        "claim": "Each expected peer matrix entry in latency-classes.json is represented by a generated tc filter/map entry and a matching netem class in tc-commands.sh.",
        "total_expected_pairs": total_expected,
        "total_verified_pairs": total_verified,
        "all_pairs_verified": total_expected == total_verified,
        "hosts": hosts,
    }
    text = json.dumps(payload, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(args.output)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

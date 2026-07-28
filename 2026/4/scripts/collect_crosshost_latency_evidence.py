#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any


def run(command: list[str]) -> str:
    return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT)


def is_local(target: str) -> bool:
    return target in {"", "localhost", "127.0.0.1", "::1"}


def remote_command(target: str, command: str) -> list[str]:
    if is_local(target):
        return ["sh", "-c", command]
    return ["ssh", target, command]


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
        r"tc qdisc add dev \"\$veth\" parent 1:(?P<band>\d+) handle (?P<handle>\d+): netem delay (?P<latency>\d+)ms(?P<rest>.*?)(?: \|\| true)?$"
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
                "handle": int(match.group("handle")),
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


def source_runtime_evidence(ssh_target: str, container: str, target_ip: str, handle: int | None) -> dict[str, Any]:
    target_hex = "".join(f"{int(part):02x}" for part in target_ip.split("."))
    command = "\n".join([
        f"if ! docker inspect {shlex.quote(container)} >/dev/null 2>&1; then",
        "  printf '%s\\n' '{\"status\":\"container_missing\"}'",
        "  exit 0",
        "fi",
        f"idx=$(docker exec {shlex.quote(container)} cat /sys/class/net/eth0/iflink 2>/dev/null)",
        "veth=$(ip -o link | awk -F': ' -v idx=\"$idx\" '$1 == idx { split($2, a, \"@\"); print a[1]; exit }')",
        "if [ -z \"$veth\" ]; then",
        "  printf '%s\\n' '{\"status\":\"veth_missing\"}'",
        "  exit 0",
        "fi",
        "printf 'STATUS running\\n'",
        "printf 'VETH %s\\n' \"$veth\"",
        f"printf 'TARGET_HEX %s\\n' {shlex.quote(target_hex)}",
        "printf 'QDISC_BEGIN\\n'",
        "tc -s qdisc show dev \"$veth\" 2>/dev/null || true",
        "printf 'QDISC_END\\n'",
        "printf 'CONTAINER_QDISC_BEGIN\\n'",
        f"docker exec {shlex.quote(container)} tc -s qdisc show dev eth0 2>/dev/null || true",
        "printf 'CONTAINER_QDISC_END\\n'",
        "printf 'FILTER_BEGIN\\n'",
        "tc -s filter show dev \"$veth\" parent 1: 2>/dev/null || true",
        "printf 'FILTER_END\\n'",
        "printf 'DOCKER_LOG_BEGIN\\n'",
        f"docker logs --tail 5 {shlex.quote(container)} 2>/dev/null || true",
        "printf 'DOCKER_LOG_END\\n'",
    ])
    try:
        output = run(remote_command(ssh_target, command))
    except subprocess.CalledProcessError as exc:
        return {"status": "error", "output": exc.output.strip()}
    if '"container_missing"' in output:
        return {"status": "container_missing"}
    qdisc = output.split("QDISC_BEGIN\n", 1)[-1].split("QDISC_END", 1)[0].strip() if "QDISC_BEGIN" in output else ""
    filters = output.split("FILTER_BEGIN\n", 1)[-1].split("FILTER_END", 1)[0].strip() if "FILTER_BEGIN" in output else ""
    container_qdisc = output.split("CONTAINER_QDISC_BEGIN\n", 1)[-1].split("CONTAINER_QDISC_END", 1)[0].strip() if "CONTAINER_QDISC_BEGIN" in output else ""
    logs = output.split("DOCKER_LOG_BEGIN\n", 1)[-1].split("DOCKER_LOG_END", 1)[0].strip() if "DOCKER_LOG_BEGIN" in output else ""
    veth_match = re.search(r"^VETH (.+)$", output, re.MULTILINE)
    return {
        "status": "running" if "STATUS running" in output else "unknown",
        "veth": veth_match.group(1) if veth_match else None,
        "target_hex": target_hex,
        "expected_netem_handle": handle,
        "qdisc_stats_excerpt": qdisc[:4000],
        "filter_stats_excerpt": filters[:4000],
        "container_eth0_qdisc_stats_excerpt": container_qdisc[:4000],
        "docker_log_tail": logs[:2000],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect cross-host matrix latency evidence from generated plan and live tc/docker state.")
    parser.add_argument("placement", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sample", type=int, default=10)
    args = parser.parse_args()

    plan = load_json(args.placement)
    project = plan["project"]
    placement = plan["placement"]
    static_ips = plan.get("static_ips", {})
    hosts = {host["name"]: host for host in plan["hosts"]}
    tc_by_host = {name: parse_tc_script(Path(host["tc_script"])) for name, host in hosts.items()}
    cross_host_rows: list[dict[str, Any]] = []

    for host in hosts.values():
        for row in flatten_class_plan(Path(host["class_plan"])):
            source = row["source"]
            target = row["target"]
            source_host = placement[source]
            target_host = placement[target]
            if source_host == target_host:
                continue
            target_ip = static_ips.get(target, "")
            container = f"{project}-{source}"
            section = tc_by_host[source_host].get(container, {"classes": {}, "filters": {}})
            band = section["filters"].get((target_ip, 9000))
            applied = section["classes"].get(band) if band is not None else section.get("fallback")
            if band is None and applied is not None:
                band = "container-eth0-root"
            generated_ok = applied is not None and int(applied["latency_ms"]) == int(row["latency_ms"]) and float(applied.get("loss_pct", 0.0)) == float(row.get("loss_pct", 0.0))
            evidence = {
                "source": source,
                "target": target,
                "source_host": source_host,
                "target_host": target_host,
                "target_ip": target_ip,
                "matrix_original_latency_ms": row.get("original_latency_ms"),
                "expected_quantized": {
                    "latency_ms": row["latency_ms"],
                    "loss_pct": row.get("loss_pct", 0.0),
                    "bandwidth_mbps": row.get("bandwidth_mbps"),
                },
                "generated_tc_band": band,
                "generated_tc_class": applied,
                "generated_config_verified": generated_ok,
            }
            if len(cross_host_rows) < args.sample:
                evidence["runtime"] = source_runtime_evidence(
                    hosts[source_host].get("ssh_target", ""),
                    container,
                    target_ip,
                    applied.get("handle") if applied else None,
                )
            cross_host_rows.append(evidence)
    payload = {
        "project": project,
        "rule_mode": plan.get("rule_mode"),
        "evidence_type": "cross-host generated-config plus live tc/docker state when containers are running",
        "total_cross_host_pairs": len(cross_host_rows),
        "sampled_pairs": cross_host_rows[: args.sample],
        "note": "Runtime qdisc/filter counters are available only while the emulation containers are running. If containers are stopped, generated_config_verified still proves that the matrix was translated into tc/netem configuration.",
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

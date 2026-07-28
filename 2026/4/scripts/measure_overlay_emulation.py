#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Host:
    name: str
    ssh_target: str
    bridge_name: str
    vxlan_script: str | None
    nodes: list[str]


def run(command: list[str]) -> str:
    return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT)


def is_local(target: str) -> bool:
    return target in {"", "localhost", "127.0.0.1", "::1"}


def remote_command(host: Host, command: str) -> list[str]:
    if is_local(host.ssh_target):
        return ["sh", "-c", command]
    return ["ssh", host.ssh_target, command]


def shell(command: str) -> str:
    return shlex.quote(command)


def probe_host(project: str, host: Host) -> dict:
    prefix = f"{project}-"
    commands = {
        "running_containers": f"docker ps --filter name={shlex.quote(prefix)} --format '{{{{.Names}}}}' | wc -l",
        "published_ports": f"docker ps --filter name={shlex.quote(prefix)} --format '{{{{.Ports}}}}' | grep -cE '0\\.0\\.0\\.0|:::' || true",
        "bridge": f"ip link show {shlex.quote(host.bridge_name)} >/dev/null 2>&1 && echo up || echo missing",
        "vxlan": "ip -d link show type vxlan 2>/dev/null | sed -n '1,4p' || true",
    }
    result: dict[str, object] = {"name": host.name, "expected_nodes": len(host.nodes)}
    for key, command in commands.items():
        try:
            result[key] = run(remote_command(host, command)).strip()
        except subprocess.CalledProcessError as exc:
            result[key] = {"error": exc.output.strip()}

    sample_nodes = host.nodes[: min(10, len(host.nodes))]
    tc_rows = []
    for node in sample_nodes:
        container = f"{project}-{node}"
        command = (
            f"if docker inspect {shlex.quote(container)} >/dev/null 2>&1; then "
            f"idx=$(docker exec {shlex.quote(container)} cat /sys/class/net/eth0/iflink 2>/dev/null); "
            "veth=$(ip -o link | awk -F': ' -v idx=\"$idx\" '$1 == idx { split($2, a, \"@\"); print a[1]; exit }'); "
            "qdisc=$(tc qdisc show dev \"$veth\" 2>/dev/null | wc -l); "
            "filters=$(tc filter show dev \"$veth\" parent 1: 2>/dev/null | grep -c '^filter' || true); "
            "egress_filters=$(tc filter show dev \"$veth\" egress 2>/dev/null | grep -c '^filter' || true); "
            "bpf_filters=$(tc filter show dev \"$veth\" egress 2>/dev/null | grep -c 'bpf' || true); "
            "printf '%s %s %s %s %s %s\\n' \"$veth\" \"$qdisc\" \"$filters\" \"$egress_filters\" \"$bpf_filters\" ok; "
            "else echo '- 0 0 0 0 missing'; fi"
        )
        try:
            output = run(remote_command(host, command)).strip().split()
            tc_rows.append({
                "node": node,
                "veth": output[0],
                "qdisc_lines": int(output[1]),
                "filters": int(output[2]),
                "egress_filters": int(output[3]),
                "bpf_filters": int(output[4]),
                "status": output[5],
            })
        except Exception as exc:
            tc_rows.append({"node": node, "status": f"error: {exc}"})
    result["tc_sample"] = tc_rows
    bpf_command = "if [ -d /sys/fs/bpf/distributed-emulator-latency-classifier ]; then bpftool map show pinned /sys/fs/bpf/distributed-emulator-latency-classifier/latency_class_map 2>/dev/null || true; else echo missing; fi"
    try:
        result["ebpf_latency_map"] = run(remote_command(host, bpf_command)).strip()
    except subprocess.CalledProcessError as exc:
        result["ebpf_latency_map"] = {"error": exc.output.strip()}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect host/container/VXLAN/tc measurement evidence for an emulation plan.")
    parser.add_argument("plan", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    project = plan["project"]
    hosts = [
        Host(
            name=item["name"],
            ssh_target=item["ssh_target"],
            bridge_name=item["bridge_name"],
            vxlan_script=item.get("vxlan_script"),
            nodes=item["nodes"],
        )
        for item in plan["hosts"]
    ]
    payload = {
        "project": project,
        "network": plan.get("network"),
        "peer_topology": plan.get("peer_topology"),
        "publish_ports": plan.get("publish_ports"),
        "rule_mode": plan.get("rule_mode"),
        "hosts": [probe_host(project, host) for host in hosts],
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

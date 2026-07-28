#!/usr/bin/env python3
"""Measure TCP/UDP socket counts for distributed emulation containers."""

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
    nodes: list[str]


def run(command: list[str]) -> str:
    return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT)


def is_local(target: str) -> bool:
    return target in {"", "localhost", "127.0.0.1", "::1"}


def remote_command(host: Host, command: str) -> list[str]:
    if is_local(host.ssh_target):
        return ["sh", "-c", command]
    return ["ssh", host.ssh_target, command]


def load_hosts(plan_path: Path) -> tuple[str, list[Host]]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    project = plan["project"]
    hosts = [
        Host(
            name=item["name"],
            ssh_target=item["ssh_target"],
            nodes=item["nodes"],
        )
        for item in plan["hosts"]
    ]
    return project, hosts


def count_container(project: str, host: Host, node: str) -> dict[str, int | str]:
    container = f"{project}-{node}"
    probe = (
        f"docker exec {shlex.quote(container)} sh -c "
        + shlex.quote(
            "command -v ss >/dev/null 2>&1 || "
            "(command -v apk >/dev/null 2>&1 && apk add --no-cache iproute2 >/dev/null); "
            "tcp_est=$(ss -tan 2>/dev/null | awk 'NR>1 && $1 == \"ESTAB\" {c++} END {print c+0}'); "
            "tcp_listen=$(ss -tan 2>/dev/null | awk 'NR>1 && $1 == \"LISTEN\" {c++} END {print c+0}'); "
            "udp=$(ss -uan 2>/dev/null | awk 'NR>1 {c++} END {print c+0}'); "
            "printf '%s %s %s\\n' \"$tcp_est\" \"$tcp_listen\" \"$udp\""
        )
    )
    try:
        output = run(remote_command(host, probe)).strip()
        tcp_est, tcp_listen, udp = [int(part) for part in output.split()[-3:]]
        status = "ok"
    except (subprocess.CalledProcessError, ValueError) as exc:
        tcp_est = tcp_listen = udp = 0
        status = f"error: {exc}"
    return {
        "host": host.name,
        "node": node,
        "container": container,
        "tcp_established": tcp_est,
        "tcp_listen": tcp_listen,
        "udp_sockets": udp,
        "status": status,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "plan",
        nargs="?",
        type=Path,
        default=Path("build/distributed-emulator/placement.json"),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    project, hosts = load_hosts(args.plan)
    rows = [
        count_container(project, host, node)
        for host in hosts
        for node in host.nodes
    ]
    totals = {
        "tcp_established": sum(int(row["tcp_established"]) for row in rows),
        "tcp_listen": sum(int(row["tcp_listen"]) for row in rows),
        "udp_sockets": sum(int(row["udp_sockets"]) for row in rows),
    }

    if args.json:
        print(json.dumps({"project": project, "totals": totals, "rows": rows}, indent=2))
        return 0

    print(f"project: {project}")
    print(
        "totals: "
        f"tcp_established={totals['tcp_established']} "
        f"tcp_listen={totals['tcp_listen']} "
        f"udp_sockets={totals['udp_sockets']}"
    )
    print("host\tnode\ttcp_established\ttcp_listen\tudp_sockets")
    for row in rows:
        print(
            f"{row['host']}\t{row['node']}\t{row['tcp_established']}\t"
            f"{row['tcp_listen']}\t{row['udp_sockets']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

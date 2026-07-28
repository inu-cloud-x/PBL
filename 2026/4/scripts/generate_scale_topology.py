#!/usr/bin/env python3
"""Generate a lightweight scale-test topology for distributed emulation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def scaled_target(requested: int | None, count: int, reference_count: int = 3500) -> int | None:
    if requested is None:
        return None
    return max(count, round(requested * (count / reference_count)))


def build_topology(
    count: int,
    output: Path,
    evaluation: bool = False,
    host_memory_mb: int = 100000,
    memory_utilization: float = 0.70,
    container_memory_mb: int | None = None,
    target_tcp_connections: int | None = None,
    target_udp_connections: int | None = None,
    publish_ports: bool | None = None,
    cross_host_peers: bool | None = None,
    rule_mode: str | None = None,
    local_to_remote_latency_ms: int = 1,
    remote_to_local_latency_ms: int = 1,
    ebpf: bool = False,
    network_mode: str = "published-port",
    peer_topology: str = "ring-offset",
    research_state_mb: int = 0,
) -> None:
    usable_host_memory_mb = int(host_memory_mb * memory_utilization)
    node_memory_mb = container_memory_mb or (64 if evaluation else 128)
    if evaluation and target_tcp_connections is None:
        target_tcp_connections = scaled_target(8000, count)
    if evaluation and target_udp_connections is None:
        target_udp_connections = scaled_target(64000, count)
    if cross_host_peers is None:
        cross_host_peers = bool(evaluation)
    if publish_ports is None:
        publish_ports = False if network_mode == "vxlan" else bool(cross_host_peers)
    if rule_mode is None and network_mode == "vxlan":
        rule_mode = "host-veth-exact"
    topology = {
        "project": f"chain-scale-{count}",
        "remote_workdir": "/home/blockchain/distributed-emulator-run",
        "emulation": {
            "quantization_ms": 10,
            "rule_mode": rule_mode or ("port-exact" if evaluation and cross_host_peers else "class-aggregate")
        },
        "time_inflation": {
            "factor": 4.0 if evaluation else 1.0
        },
        "network": ({
            "mode": "vxlan",
            "subnet": "10.42.0.0/16",
            "gateway": "10.42.0.1",
            "gateway_by_host": {
                "local-machine": "10.42.0.1",
                "remote-machine": "10.42.0.2"
            },
            "vxlan_id": 4242,
            "vxlan_port": 4789,
            "mtu": 1450
        } if network_mode == "vxlan" else {"mode": "published-port"}),
        "peer_topology": ({
            "type": "small-world",
            "seed": 2026,
            "local_degree": 2,
            "shortcut_probability": 0.35
        } if peer_topology == "small-world" else {"type": "ring-offset"}),
        "host_latency_policy": "subtract_from_emulated_delay",
        "host_latency_ms": {
            "local-machine->remote-machine": local_to_remote_latency_ms,
            "remote-machine->local-machine": remote_to_local_latency_ms
        },
        "ebpf": {
            "enabled": ebpf,
            "mode": "tcp-rto",
            "auto_apply": False
        },
        "hosts": [
            {
                "name": "local-machine",
                "address": "172.16.0.116",
                "ssh_user": "",
                "memory_mb": usable_host_memory_mb,
                "bridge_name": "br-local"
            },
            {
                "name": "remote-machine",
                "address": "172.16.0.117",
                "ssh_user": "blockchain",
                "memory_mb": usable_host_memory_mb,
                "bridge_name": "br-remote"
            }
        ],
        "workload": {
            "enabled": True,
            "tcp_port_base": 30000,
            "udp_port_base": 40000,
            "container_p2p_port": 9000,
            "block_interval_ms": 5000 if evaluation else 1000,
            "transactions_per_block": 20 if evaluation else 1,
            **({
                "target_tcp_connections": target_tcp_connections,
                "target_udp_connections": target_udp_connections,
                "publish_ports": publish_ports,
                "cross_host_peers": cross_host_peers
            } if evaluation else {})
        },
        "defaults": {
            "image": "p2p-blockchain-daemon:latest",
            "memory_mb": node_memory_mb,
            "network": "emulation-net"
        },
        "nodes": [
            {
                "id": f"emulated-node-{idx}",
                **({"env": {"RESEARCH_STATE_MB": str(research_state_mb)}} if research_state_mb else {})
            }
            for idx in range(count)
        ],
        "matrix_model": ({
            "type": "deterministic",
            "seed": 2026,
            "latency_ms_values": [10, 20, 30, 40, 50, 60, 80, 100, 120],
            "loss_pct_values": [0.0, 0.1, 0.2, 0.5, 1.0],
            "bandwidth_mbps_values": [25, 50, 100],
            "aggregate_sample_size": 32
        } if evaluation else {
            "type": "uniform",
            "latency_ms": 40,
            "loss_pct": 0.2,
            "bandwidth_mbps": 50
        })
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(topology, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("count", type=int, nargs="?", help="node count; omitted with --fit-to-memory")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--evaluation", action="store_true")
    parser.add_argument("--host-memory-mb", type=int, default=100000)
    parser.add_argument("--memory-utilization", type=float, default=0.70)
    parser.add_argument("--container-memory-mb", type=int)
    parser.add_argument("--target-tcp-connections", type=int)
    parser.add_argument("--target-udp-connections", type=int)
    parser.add_argument("--publish-ports", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--cross-host-peers", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--fit-to-memory", action="store_true", help="fill two hosts up to the configured memory budget")
    parser.add_argument("--host-count", type=int, default=2)
    parser.add_argument("--rule-mode", choices=["class-aggregate", "port-exact", "host-veth-exact", "ebpf-classifier"], default=None)
    parser.add_argument("--network-mode", choices=["published-port", "vxlan"], default="published-port")
    parser.add_argument("--peer-topology", choices=["ring-offset", "small-world"], default="ring-offset")
    parser.add_argument("--local-to-remote-latency-ms", type=int, default=1)
    parser.add_argument("--remote-to-local-latency-ms", type=int, default=1)
    parser.add_argument("--ebpf", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--research-state-mb", type=int, default=0)
    args = parser.parse_args()
    if not 0 < args.memory_utilization <= 1:
        raise SystemExit("memory utilization must be in (0, 1]")
    container_memory_mb = args.container_memory_mb or (64 if args.evaluation else 128)
    if args.fit_to_memory:
        usable_per_host = int(args.host_memory_mb * args.memory_utilization)
        args.count = args.host_count * (usable_per_host // container_memory_mb)
    if args.count is None or args.count <= 0:
        raise SystemExit("count must be positive, or use --fit-to-memory")
    output = args.output or Path(f"examples/scale-{args.count}.json")
    build_topology(
        args.count,
        output,
        args.evaluation,
        args.host_memory_mb,
        args.memory_utilization,
        container_memory_mb,
        args.target_tcp_connections,
        args.target_udp_connections,
        args.publish_ports,
        args.cross_host_peers,
        args.rule_mode,
        args.local_to_remote_latency_ms,
        args.remote_to_local_latency_ms,
        args.ebpf,
        args.network_mode,
        args.peer_topology,
        args.research_state_mb,
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

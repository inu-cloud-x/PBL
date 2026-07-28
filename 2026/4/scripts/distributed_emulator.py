#!/usr/bin/env python3
"""Prototype controller for distributed Docker-based blockchain emulation."""

from __future__ import annotations

import argparse
import ipaddress
import json
import random
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


BUILD_DIR = Path("build/distributed-emulator")
WORKLOAD_DAEMON = Path("workload/blockchain_daemon.py")
MAX_LINUX_IFNAME = 15


@dataclass(frozen=True)
class Host:
    name: str
    address: str
    ssh_user: str
    memory_mb: int
    bridge_name: str

    @property
    def ssh_target(self) -> str:
        return f"{self.ssh_user}@{self.address}" if self.ssh_user else ""


@dataclass(frozen=True)
class Node:
    id: str
    image: str
    memory_mb: int
    command: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    ports: list[str] = field(default_factory=list)
    network: str = "emulation-net"


@dataclass(frozen=True)
class Link:
    source: str
    target: str
    latency_ms: int = 0
    loss_pct: float = 0.0
    bandwidth_mbps: int | None = None


@dataclass(frozen=True)
class EmulationOptions:
    quantization_ms: int = 10
    rule_mode: str = "class-aggregate"
    time_inflation_factor: float = 1.0
    workload_enabled: bool = True
    tcp_port_base: int = 30000
    udp_port_base: int = 40000
    container_p2p_port: int = 9000
    block_interval_ms: int = 1000
    target_tcp_connections: int | None = None
    target_udp_connections: int | None = None
    publish_ports: bool = True
    cross_host_peers: bool = True


def load_topology(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        topology = json.load(fh)
    validate_topology(topology)
    return topology


def validate_topology(topology: dict[str, Any]) -> None:
    for key in ("hosts", "nodes"):
        if key not in topology or not isinstance(topology[key], list):
            raise ValueError(f"topology must contain a '{key}' list")
    if not topology["hosts"]:
        raise ValueError("at least one host is required")
    if not topology["nodes"]:
        raise ValueError("at least one node is required")

    host_names = [host["name"] for host in topology["hosts"]]
    node_ids = [node["id"] for node in topology["nodes"]]
    if len(host_names) != len(set(host_names)):
        raise ValueError("host names must be unique")
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("node ids must be unique")

    node_set = set(node_ids)
    for link in topology.get("links", []):
        if link["source"] not in node_set or link["target"] not in node_set:
            raise ValueError(f"link references unknown node: {link}")

    matrix = topology.get("matrix")
    if matrix:
        matrix_nodes = matrix.get("nodes", node_ids)
        unknown = sorted(set(matrix_nodes) - node_set)
        if unknown:
            raise ValueError(f"matrix references unknown nodes: {', '.join(unknown)}")
        for key in ("latency_ms", "loss_pct", "bandwidth_mbps"):
            if key in matrix:
                validate_square_matrix(key, matrix[key], len(matrix_nodes))


def validate_square_matrix(name: str, value: Any, size: int) -> None:
    if not isinstance(value, list) or len(value) != size:
        raise ValueError(f"matrix.{name} must have {size} rows")
    for row in value:
        if not isinstance(row, list) or len(row) != size:
            raise ValueError(f"matrix.{name} must be a {size}x{size} matrix")


def safe_bridge_name(host_name: str, requested: str | None = None) -> str:
    raw = requested or f"br-{host_name}"
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "-", raw)
    return safe[:MAX_LINUX_IFNAME]


def parse_emulation_options(topology: dict[str, Any]) -> EmulationOptions:
    emulation = topology.get("emulation", {})
    time_inflation = topology.get("time_inflation", {})
    quantization_ms = int(emulation.get("quantization_ms", 10))
    if quantization_ms <= 0:
        raise ValueError("emulation.quantization_ms must be positive")
    factor = float(time_inflation.get("factor", emulation.get("time_inflation_factor", 1.0)))
    if factor <= 0:
        raise ValueError("time inflation factor must be positive")
    workload = topology.get("workload", {})
    return EmulationOptions(
        quantization_ms=quantization_ms,
        rule_mode=emulation.get("rule_mode", "class-aggregate"),
        time_inflation_factor=factor,
        workload_enabled=bool(workload.get("enabled", True)),
        tcp_port_base=int(workload.get("tcp_port_base", 30000)),
        udp_port_base=int(workload.get("udp_port_base", 40000)),
        container_p2p_port=int(workload.get("container_p2p_port", 9000)),
        block_interval_ms=int(workload.get("block_interval_ms", 1000)),
        target_tcp_connections=(
            int(workload["target_tcp_connections"])
            if "target_tcp_connections" in workload else None
        ),
        target_udp_connections=(
            int(workload["target_udp_connections"])
            if "target_udp_connections" in workload else None
        ),
        publish_ports=bool(workload.get("publish_ports", True)),
        cross_host_peers=bool(workload.get("cross_host_peers", True)),
    )


def parse_hosts(topology: dict[str, Any]) -> list[Host]:
    return [
        Host(
            name=host["name"],
            address=host.get("address", host["name"]),
            ssh_user=host.get("ssh_user", ""),
            memory_mb=int(host["memory_mb"]),
            bridge_name=safe_bridge_name(host["name"], host.get("bridge_name")),
        )
        for host in topology["hosts"]
    ]


def parse_nodes(topology: dict[str, Any]) -> list[Node]:
    defaults = topology.get("defaults", {})
    nodes: list[Node] = []
    for item in topology["nodes"]:
        env = {str(key): str(value) for key, value in item.get("env", {}).items()}
        nodes.append(
            Node(
                id=item["id"],
                image=item.get("image", defaults.get("image", "alpine:latest")),
                memory_mb=int(item.get("memory_mb", defaults.get("memory_mb", 512))),
                command=[str(part) for part in item.get("command", [])],
                env=env,
                ports=[str(port) for port in item.get("ports", [])],
                network=item.get("network", defaults.get("network", "emulation-net")),
            )
        )
    return nodes


def parse_links(topology: dict[str, Any], options: EmulationOptions | None = None) -> list[Link]:
    links = [
        Link(
            source=link["source"],
            target=link["target"],
            latency_ms=int(link.get("latency_ms", 0)),
            loss_pct=float(link.get("loss_pct", 0.0)),
            bandwidth_mbps=(
                int(link["bandwidth_mbps"]) if "bandwidth_mbps" in link else None
            ),
        )
        for link in topology.get("links", [])
    ]
    return links + parse_matrix_links(topology) + parse_matrix_model_links(topology, options)


def parse_matrix_model_links(topology: dict[str, Any], options: EmulationOptions | None) -> list[Link]:
    model = topology.get("matrix_model")
    if not model:
        return []
    nodes = [node["id"] for node in topology["nodes"]]
    model_type = model.get("type", "uniform")

    def deterministic_value(source_idx: int, target_idx: int) -> tuple[int, float, int | None]:
        if model_type == "uniform":
            latency_ms = int(model.get("latency_ms", 0))
            loss_pct = float(model.get("loss_pct", 0.0))
            bandwidth_mbps = (
                int(model["bandwidth_mbps"]) if "bandwidth_mbps" in model else None
            )
            return latency_ms, loss_pct, bandwidth_mbps
        if model_type != "deterministic":
            raise ValueError("matrix_model.type must be uniform or deterministic")

        latency_values = [int(value) for value in model.get("latency_ms_values", [10, 20, 30, 40, 50, 60, 80, 100])]
        loss_values = [float(value) for value in model.get("loss_pct_values", [0.0, 0.1, 0.2, 0.5, 1.0])]
        bandwidth_values = [int(value) for value in model.get("bandwidth_mbps_values", [25, 50, 100])]
        seed = int(model.get("seed", 17))
        mixed = (source_idx * 1103515245 + target_idx * 12345 + seed) & 0x7FFFFFFF
        latency_ms = latency_values[mixed % len(latency_values)]
        loss_pct = loss_values[(mixed // len(latency_values)) % len(loss_values)]
        bandwidth_mbps = bandwidth_values[(mixed // (len(latency_values) * len(loss_values))) % len(bandwidth_values)]
        return latency_ms, loss_pct, bandwidth_mbps

    if options and options.rule_mode == "class-aggregate":
        links = []
        for source_idx, source in enumerate(nodes):
            samples = [
                deterministic_value(source_idx, (source_idx + offset) % len(nodes))
                for offset in range(1, min(len(nodes), int(model.get("aggregate_sample_size", 32)) + 1))
            ]
            latency_ms = max(sample[0] for sample in samples) if samples else 0
            loss_pct = max(sample[1] for sample in samples) if samples else 0.0
            rates = [sample[2] for sample in samples if sample[2] is not None]
            bandwidth_mbps = min(rates) if rates else None
            links.append(
                Link(
                    source=source,
                    target="*",
                    latency_ms=latency_ms,
                    loss_pct=loss_pct,
                    bandwidth_mbps=bandwidth_mbps,
                )
            )
        return links

    return [
        Link(
            source=source,
            target=target,
            latency_ms=deterministic_value(source_idx, target_idx)[0],
            loss_pct=deterministic_value(source_idx, target_idx)[1],
            bandwidth_mbps=deterministic_value(source_idx, target_idx)[2],
        )
        for source_idx, source in enumerate(nodes)
        for target_idx, target in enumerate(nodes)
        if source != target
    ]


def logical_link_count(topology: dict[str, Any], materialized_links: list[Link]) -> int:
    model = topology.get("matrix_model")
    if model:
        node_count = len(topology["nodes"])
        return node_count * (node_count - 1)
    return len(materialized_links)


def parse_matrix_links(topology: dict[str, Any]) -> list[Link]:
    matrix = topology.get("matrix")
    if not matrix:
        return []

    matrix_nodes = matrix.get("nodes", [node["id"] for node in topology["nodes"]])
    latency = matrix.get("latency_ms")
    loss = matrix.get("loss_pct")
    bandwidth = matrix.get("bandwidth_mbps")
    links: list[Link] = []

    for source_idx, source in enumerate(matrix_nodes):
        for target_idx, target in enumerate(matrix_nodes):
            if source == target:
                continue
            latency_ms = int(latency[source_idx][target_idx]) if latency else 0
            loss_pct = float(loss[source_idx][target_idx]) if loss else 0.0
            bandwidth_mbps = (
                int(bandwidth[source_idx][target_idx]) if bandwidth else None
            )
            if latency_ms == 0 and loss_pct == 0.0 and bandwidth_mbps is None:
                continue
            links.append(
                Link(
                    source=source,
                    target=target,
                    latency_ms=latency_ms,
                    loss_pct=loss_pct,
                    bandwidth_mbps=bandwidth_mbps,
                )
            )
    return links


def place_nodes(hosts: list[Host], nodes: list[Node]) -> dict[str, str]:
    remaining = {host.name: host.memory_mb for host in hosts}
    placement: dict[str, str] = {}
    sorted_nodes = sorted(nodes, key=lambda node: node.memory_mb, reverse=True)

    for node in sorted_nodes:
        candidates = [host for host in hosts if remaining[host.name] >= node.memory_mb]
        if not candidates:
            raise RuntimeError(
                f"not enough memory to place {node.id} ({node.memory_mb} MB)"
            )
        selected = max(candidates, key=lambda host: remaining[host.name])
        placement[node.id] = selected.name
        remaining[selected.name] -= node.memory_mb

    return placement


def yaml_scalar(value: str) -> str:
    return json.dumps(value)


def quantize_latency(latency_ms: int, quantum_ms: int) -> int:
    if latency_ms <= 0:
        return 0
    return ((latency_ms + quantum_ms - 1) // quantum_ms) * quantum_ms


def latency_class_id(latency_ms: int) -> str:
    return f"latency_{latency_ms}ms"


def build_latency_classes(links: list[Link], options: EmulationOptions) -> dict[int, list[Link]]:
    classes: dict[int, list[Link]] = {}
    for link in links:
        quantized = quantize_latency(link.latency_ms, options.quantization_ms)
        classes.setdefault(quantized, []).append(link)
    return dict(sorted(classes.items()))


def directed_peer_targets(node_ids: list[str], directed_edges: int) -> dict[str, set[str]]:
    targets: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    if directed_edges <= 0 or len(node_ids) <= 1:
        return targets
    max_edges = len(node_ids) * (len(node_ids) - 1)
    directed_edges = min(directed_edges, max_edges)
    remaining = directed_edges
    offset = 1
    while remaining > 0:
        for idx, node_id in enumerate(node_ids):
            if remaining <= 0:
                break
            target = node_ids[(idx + offset) % len(node_ids)]
            if target != node_id and target not in targets[node_id]:
                targets[node_id].add(target)
                remaining -= 1
        offset += 1
    return targets




def overlay_config(topology: dict[str, Any]) -> dict[str, Any]:
    network = topology.get("network", {})
    if network.get("mode") != "vxlan":
        return {"enabled": False}
    return {
        "enabled": True,
        "mode": "vxlan",
        "subnet": network.get("subnet", "10.42.0.0/16"),
        "gateway": network.get("gateway", "10.42.0.1"),
        "gateway_by_host": network.get("gateway_by_host", {}),
        "vxlan_id": int(network.get("vxlan_id", 4242)),
        "vxlan_port": int(network.get("vxlan_port", 4789)),
        "mtu": int(network.get("mtu", 1450)),
    }


def container_ip_map(topology: dict[str, Any], nodes: list[Node]) -> dict[str, str]:
    overlay = overlay_config(topology)
    if not overlay["enabled"]:
        return {}
    subnet = ipaddress.ip_network(str(overlay["subnet"]))
    reserved = {str(subnet.network_address), str(subnet.broadcast_address), str(overlay.get("gateway", ""))}
    reserved.update(str(value) for value in overlay.get("gateway_by_host", {}).values())
    mapping: dict[str, str] = {}
    candidates = subnet.hosts()
    for node in nodes:
        for candidate in candidates:
            candidate_text = str(candidate)
            last_octet = int(candidate_text.rsplit(".", 1)[1])
            if candidate_text in reserved or last_octet in {0, 255}:
                continue
            mapping[node.id] = candidate_text
            break
        else:
            raise RuntimeError(f"not enough IP addresses in overlay subnet {subnet}")
    return mapping


def small_world_peer_targets(
    node_ids: list[str],
    directed_edges: int,
    seed: int,
    local_degree: int,
    shortcut_probability: float,
) -> dict[str, set[str]]:
    targets: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    if directed_edges <= 0 or len(node_ids) <= 1:
        return targets
    max_edges = len(node_ids) * (len(node_ids) - 1)
    directed_edges = min(directed_edges, max_edges)
    rng = random.Random(seed)
    remaining = directed_edges
    degree = max(1, local_degree)
    for offset in range(1, degree + 1):
        for idx, node_id in enumerate(node_ids):
            if remaining <= 0:
                return targets
            target = node_ids[(idx + offset) % len(node_ids)]
            if target != node_id and target not in targets[node_id]:
                targets[node_id].add(target)
                remaining -= 1
    attempts = 0
    while remaining > 0 and attempts < directed_edges * 20:
        attempts += 1
        source = rng.choice(node_ids)
        if shortcut_probability < 1.0 and rng.random() > shortcut_probability:
            continue
        target = rng.choice(node_ids)
        if target == source or target in targets[source]:
            continue
        targets[source].add(target)
        remaining -= 1
    offset = degree + 1
    while remaining > 0:
        for idx, node_id in enumerate(node_ids):
            if remaining <= 0:
                break
            target = node_ids[(idx + offset) % len(node_ids)]
            if target != node_id and target not in targets[node_id]:
                targets[node_id].add(target)
                remaining -= 1
        offset += 1
    return targets


def peer_targets_for_topology(
    topology: dict[str, Any],
    groups: list[list[str]],
    total_connections: int | None,
    protocol: str,
    explicit_targets: dict[str, set[str]],
) -> dict[str, set[str]]:
    node_ids = [node["id"] for node in topology["nodes"]]
    peer_topology = topology.get("peer_topology", {})
    topology_type = peer_topology.get("type", "ring-offset")
    if total_connections is None:
        if topology.get("matrix_model"):
            return {
                source: targets
                for group in groups
                for source, targets in directed_peer_targets(group, len(group)).items()
            }
        return explicit_targets

    directed_total = (total_connections + 1) // 2 if protocol == "tcp" else max(total_connections - len(node_ids), 0)
    result: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    remaining = directed_total
    for group_idx, group in enumerate(groups):
        share = remaining if group_idx == len(groups) - 1 else directed_total // len(groups)
        if topology_type == "small-world":
            partial = small_world_peer_targets(
                group,
                share,
                int(peer_topology.get("seed", 2026)) + (0 if protocol == "tcp" else 100000) + group_idx,
                int(peer_topology.get("local_degree", 2)),
                float(peer_topology.get("shortcut_probability", 0.35)),
            )
        else:
            partial = directed_peer_targets(group, share)
        for source, targets in partial.items():
            result[source].update(targets)
        remaining -= share
    return result
def format_peers(targets: set[str], endpoints: dict[str, dict[str, Any]]) -> str:
    peers = []
    for target in sorted(targets):
        endpoint = endpoints[target]
        peers.append(
            f"{target}:{endpoint['host']}:{endpoint['tcp_port']}:{endpoint['udp_port']}"
        )
    return ",".join(peers)


def build_peer_config(
    topology: dict[str, Any],
    hosts: list[Host],
    nodes: list[Node],
    placement: dict[str, str],
    options: EmulationOptions,
) -> dict[str, dict[str, Any]]:
    host_by_name = {host.name: host for host in hosts}
    node_ids = [node.id for node in nodes]
    overlay = overlay_config(topology)
    static_ips = container_ip_map(topology, nodes)
    endpoints: dict[str, dict[str, Any]] = {}
    for idx, node_id in enumerate(node_ids):
        host = host_by_name[placement[node_id]]
        endpoints[node_id] = {
            "host": host.address,
            "internal_host": node_id,
            "host_name": host.name,
            "container_ip": static_ips.get(node_id, ""),
            "tcp_port": options.tcp_port_base + idx,
            "udp_port": options.udp_port_base + idx,
        }

    explicit_targets: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    for link in parse_matrix_links(topology):
        if link.target != "*":
            explicit_targets.setdefault(link.source, set()).add(link.target)
    for link in topology.get("links", []):
        explicit_targets.setdefault(link["source"], set()).add(link["target"])

    groups: list[list[str]]
    if options.cross_host_peers:
        groups = [node_ids]
    else:
        by_host: dict[str, list[str]] = {host.name: [] for host in hosts}
        for node_id in node_ids:
            by_host[placement[node_id]].append(node_id)
        groups = [group for group in by_host.values() if group]

    tcp_targets = peer_targets_for_topology(
        topology, groups, options.target_tcp_connections, "tcp", explicit_targets
    )
    udp_targets = peer_targets_for_topology(
        topology, groups, options.target_udp_connections, "udp", explicit_targets
    )

    def format_peer_list(source: str, targets: set[str]) -> str:
        peers = []
        for target in sorted(targets):
            endpoint = endpoints[target]
            if options.publish_ports:
                host = endpoint["host"]
                tcp_port = endpoint["tcp_port"]
                udp_port = endpoint["udp_port"]
            elif overlay["enabled"]:
                host = endpoint["container_ip"]
                tcp_port = options.container_p2p_port
                udp_port = options.container_p2p_port
            else:
                host = endpoint["internal_host"]
                tcp_port = options.container_p2p_port
                udp_port = options.container_p2p_port
            peers.append(f"{target}:{host}:{tcp_port}:{udp_port}")
        return ",".join(peers)

    config: dict[str, dict[str, Any]] = {}
    for node_id in node_ids:
        config[node_id] = {
            **endpoints[node_id],
            "tcp_peers": format_peer_list(node_id, tcp_targets.get(node_id, set())),
            "udp_peers": format_peer_list(node_id, udp_targets.get(node_id, set())),
            "tcp_peer_count": len(tcp_targets.get(node_id, set())),
            "udp_peer_count": len(udp_targets.get(node_id, set())),
        }
    return config


def parse_peer_entries(raw: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        node_id, host, tcp_port, udp_port = item.split(":", 3)
        entries.append(
            {
                "node_id": node_id,
                "host": host,
                "tcp_port": int(tcp_port),
                "udp_port": int(udp_port),
            }
        )
    return entries


def deterministic_matrix_value(model: dict[str, Any], source_idx: int, target_idx: int) -> tuple[int, float, int | None]:
    model_type = model.get("type", "uniform")
    if model_type == "uniform":
        return (
            int(model.get("latency_ms", 0)),
            float(model.get("loss_pct", 0.0)),
            int(model["bandwidth_mbps"]) if "bandwidth_mbps" in model else None,
        )
    if model_type != "deterministic":
        raise ValueError("matrix_model.type must be uniform or deterministic")

    latency_values = [int(value) for value in model.get("latency_ms_values", [10, 20, 30, 40, 50, 60, 80, 100])]
    loss_values = [float(value) for value in model.get("loss_pct_values", [0.0, 0.1, 0.2, 0.5, 1.0])]
    bandwidth_values = [int(value) for value in model.get("bandwidth_mbps_values", [25, 50, 100])]
    seed = int(model.get("seed", 17))
    mixed = (source_idx * 1103515245 + target_idx * 12345 + seed) & 0x7FFFFFFF
    latency_ms = latency_values[mixed % len(latency_values)]
    loss_pct = loss_values[(mixed // len(latency_values)) % len(loss_values)]
    bandwidth_mbps = bandwidth_values[(mixed // (len(latency_values) * len(loss_values))) % len(bandwidth_values)]
    return latency_ms, loss_pct, bandwidth_mbps


def host_pair_latency_ms(topology: dict[str, Any], source_host: str, target_host: str) -> int:
    if source_host == target_host:
        return 0
    table = topology.get("host_latency_ms", topology.get("host_base_latency_ms", {}))
    if not table:
        return 0
    if isinstance(table, dict):
        nested = table.get(source_host)
        if isinstance(nested, dict) and target_host in nested:
            return int(round(float(nested[target_host])))
        for key in (f"{source_host}->{target_host}", f"{source_host},{target_host}", f"{source_host}:{target_host}"):
            if key in table:
                return int(round(float(table[key])))
    return 0


def pair_link_attributes(
    topology: dict[str, Any],
    source: str,
    target: str,
    node_index: dict[str, int],
) -> tuple[int, float, int | None]:
    for link in topology.get("links", []):
        if link.get("source") == source and link.get("target") == target:
            return (
                int(link.get("latency_ms", 0)),
                float(link.get("loss_pct", 0.0)),
                int(link["bandwidth_mbps"]) if "bandwidth_mbps" in link else None,
            )

    matrix = topology.get("matrix")
    if matrix:
        matrix_nodes = matrix.get("nodes", [node["id"] for node in topology["nodes"]])
        if source in matrix_nodes and target in matrix_nodes:
            source_idx = matrix_nodes.index(source)
            target_idx = matrix_nodes.index(target)
            latency = matrix.get("latency_ms")
            loss = matrix.get("loss_pct")
            bandwidth = matrix.get("bandwidth_mbps")
            return (
                int(latency[source_idx][target_idx]) if latency else 0,
                float(loss[source_idx][target_idx]) if loss else 0.0,
                int(bandwidth[source_idx][target_idx]) if bandwidth else None,
            )

    model = topology.get("matrix_model")
    if model:
        return deterministic_matrix_value(model, node_index[source], node_index[target])

    return 0, 0.0, None


def adjusted_pair_link(
    topology: dict[str, Any],
    source: str,
    target: str,
    placement: dict[str, str],
    node_index: dict[str, int],
) -> Link:
    desired_latency, loss_pct, bandwidth_mbps = pair_link_attributes(topology, source, target, node_index)
    base_latency = host_pair_latency_ms(topology, placement[source], placement[target])
    policy = topology.get("host_latency_policy", "subtract_from_emulated_delay")
    if policy == "add_to_emulated_delay":
        latency_ms = desired_latency + base_latency
    elif policy == "ignore":
        latency_ms = desired_latency
    else:
        latency_ms = max(0, desired_latency - base_latency)
    return Link(source=source, target=target, latency_ms=latency_ms, loss_pct=loss_pct, bandwidth_mbps=bandwidth_mbps)


def build_peer_links(
    topology: dict[str, Any],
    nodes: list[Node],
    placement: dict[str, str],
    peer_config: dict[str, dict[str, Any]],
) -> list[Link]:
    node_index = {node.id: idx for idx, node in enumerate(nodes)}
    links: dict[tuple[str, str], Link] = {}
    for source in node_index:
        peers = parse_peer_entries(str(peer_config.get(source, {}).get("tcp_peers", "")))
        peers.extend(parse_peer_entries(str(peer_config.get(source, {}).get("udp_peers", ""))))
        for peer in peers:
            target = peer["node_id"]
            if target in node_index:
                links[(source, target)] = adjusted_pair_link(topology, source, target, placement, node_index)
    return list(links.values())


def render_port_exact_tc_script(
    project: str,
    node_ids: list[str],
    links: list[Link],
    peer_config: dict[str, dict[str, Any]],
    options: EmulationOptions,
) -> str:
    by_source: dict[str, dict[str, Link]] = {node_id: {} for node_id in node_ids}
    for link in links:
        if link.source in by_source:
            by_source[link.source][link.target] = link

    lines = [
        "#!/usr/bin/env sh",
        "set -eu",
        "if ! command -v tc >/dev/null 2>&1; then echo 'tc not found; skipping exact latency shaping' >&2; exit 0; fi",
        "if ! command -v nft >/dev/null 2>&1; then echo 'nft not found; skipping exact latency shaping' >&2; exit 0; fi",
        "",
    ]

    for node_id in sorted(node_ids):
        peer_rows: list[tuple[str, dict[str, Any], Link]] = []
        seen: set[tuple[str, str, int]] = set()
        p2p = peer_config.get(node_id, {})
        for protocol, key in (("tcp", "tcp_peers"), ("udp", "udp_peers")):
            for peer in parse_peer_entries(str(p2p.get(key, ""))):
                target = peer["node_id"]
                link = by_source.get(node_id, {}).get(target)
                if not link:
                    continue
                port = peer["tcp_port"] if protocol == "tcp" else peer["udp_port"]
                dedupe = (protocol, peer["host"], port)
                if dedupe in seen:
                    continue
                seen.add(dedupe)
                peer_rows.append((protocol, peer, link))
        if not peer_rows:
            continue

        class_keys = sorted(
            {
                (
                    quantize_latency(link.latency_ms, options.quantization_ms),
                    link.loss_pct,
                    link.bandwidth_mbps,
                )
                for _, _, link in peer_rows
            }
        )
        class_by_key = {key: idx + 1 for idx, key in enumerate(class_keys)}
        bands = len(class_keys) + 1
        container = f"{project}-{node_id}"
        nft_lines = [
            "nft delete table inet emu_latency 2>/dev/null || true",
            "nft add table inet emu_latency",
            "nft add chain inet emu_latency output '{ type route hook output priority mangle; policy accept; }'",
        ]
        tc_lines = [
            "tc qdisc del dev eth0 root 2>/dev/null || true",
            f"tc qdisc add dev eth0 root handle 1: prio bands {bands}",
        ]
        for key, band in class_by_key.items():
            latency, loss, rate = key
            netem = f"delay {latency}ms"
            if loss > 0:
                netem += f" loss {loss}%"
            # Some iproute2/kernel combinations reject netem rate on child qdiscs.
            # Keep bandwidth in the plan, but apply delay/loss here for portable latency evidence.
            handle = 10 + band
            tc_lines.append(f"tc qdisc add dev eth0 parent 1:{band} handle {handle}: netem {netem}")
            tc_lines.append(f"tc filter add dev eth0 protocol ip parent 1: prio 10 handle {band} fw flowid 1:{band}")
        for protocol, peer, link in peer_rows:
            latency = quantize_latency(link.latency_ms, options.quantization_ms)
            key = (latency, link.loss_pct, link.bandwidth_mbps)
            mark = class_by_key[key]
            port = peer["tcp_port"] if protocol == "tcp" else peer["udp_port"]
            nft_lines.append(
                f"nft add rule inet emu_latency output ip daddr {peer['host']} {protocol} dport {port} meta mark set {mark}"
            )
        script = "; ".join(nft_lines + tc_lines)
        lines.extend(
            [
                f"echo 'applying port-exact latency to {container}: {len(peer_rows)} peer protocol rules, {len(class_keys)} classes'",
                f"docker exec {shlex.quote(container)} sh -c {shlex.quote(script)}",
                "",
            ]
        )
    return "\n".join(lines)



def render_vxlan_script(host: Host, hosts: list[Host], topology: dict[str, Any]) -> str:
    overlay = overlay_config(topology)
    if not overlay["enabled"]:
        return "#!/usr/bin/env sh\nset -eu\necho 'vxlan disabled'\n"
    remotes = [item.address for item in hosts if item.name != host.name]
    if not remotes:
        return "#!/usr/bin/env sh\nset -eu\necho 'vxlan needs at least two hosts'\n"
    vxlan_name = f"vx{host.bridge_name}"[:MAX_LINUX_IFNAME]
    lines = [
        "#!/usr/bin/env sh",
        "set -eu",
        f"BRIDGE={shlex.quote(host.bridge_name)}",
        f"VXLAN={shlex.quote(vxlan_name)}",
        f"VXLAN_ID={overlay['vxlan_id']}",
        f"VXLAN_PORT={overlay['vxlan_port']}",
        f"MTU={overlay['mtu']}",
        "if ! sudo -n ip link show \"$BRIDGE\" >/dev/null 2>&1; then echo \"bridge $BRIDGE does not exist yet\" >&2; exit 1; fi",
        "sudo -n ip link del \"$VXLAN\" 2>/dev/null || true",
    ]
    if len(remotes) == 1:
        lines.append(f"sudo -n ip link add \"$VXLAN\" type vxlan id \"$VXLAN_ID\" remote {shlex.quote(remotes[0])} dstport \"$VXLAN_PORT\" nolearning")
    else:
        lines.append("sudo -n ip link add \"$VXLAN\" type vxlan id \"$VXLAN_ID\" dstport \"$VXLAN_PORT\" nolearning")
        for remote in remotes:
            lines.append(f"sudo -n bridge fdb append 00:00:00:00:00:00 dev \"$VXLAN\" dst {shlex.quote(remote)} self permanent")
    lines.extend([
        "sudo -n ip link set dev \"$VXLAN\" mtu \"$MTU\"",
        "sudo -n ip link set dev \"$VXLAN\" master \"$BRIDGE\"",
        "sudo -n ip link set dev \"$VXLAN\" up",
        "echo \"vxlan $VXLAN attached to $BRIDGE\"",
        "sudo -n ip -d link show \"$VXLAN\"",
        "",
    ])
    return "\n".join(lines)


def render_host_veth_exact_tc_script(
    project: str,
    node_ids: list[str],
    links: list[Link],
    peer_config: dict[str, dict[str, Any]],
    options: EmulationOptions,
) -> str:
    by_source: dict[str, dict[str, Link]] = {node_id: {} for node_id in node_ids}
    for link in links:
        if link.source in by_source:
            by_source[link.source][link.target] = link

    lines = [
        "#!/usr/bin/env sh",
        "set -eu",
        "if ! command -v tc >/dev/null 2>&1; then echo 'tc not found; skipping host-veth shaping' >&2; exit 0; fi",
        "if ! command -v ip >/dev/null 2>&1; then echo 'ip not found; skipping host-veth shaping' >&2; exit 0; fi",
        "find_host_veth() {",
        "  container=$1",
        "  ifindex=$(docker exec \"$container\" cat /sys/class/net/eth0/iflink)",
        "  sudo -n ip -o link | awk -F': ' -v idx=\"$ifindex\" '$1 == idx { split($2, a, \"@\"); print a[1]; exit }'",
        "}",
        "",
    ]
    for node_id in sorted(node_ids):
        peer_rows: list[tuple[dict[str, Any], Link]] = []
        seen: set[tuple[str, int]] = set()
        p2p = peer_config.get(node_id, {})
        for key in ("tcp_peers", "udp_peers"):
            for peer in parse_peer_entries(str(p2p.get(key, ""))):
                target = peer["node_id"]
                link = by_source.get(node_id, {}).get(target)
                if not link:
                    continue
                # Under VXLAN/no published ports both protocols use the same peer IP:9000 path.
                dedupe = (peer["host"], peer["tcp_port"])
                if dedupe in seen:
                    continue
                seen.add(dedupe)
                peer_rows.append((peer, link))
        if not peer_rows:
            continue
        class_keys = sorted(
            {
                (
                    quantize_latency(link.latency_ms, options.quantization_ms),
                    link.loss_pct,
                    link.bandwidth_mbps,
                )
                for _, link in peer_rows
            }
        )
        class_by_key = {key: idx + 1 for idx, key in enumerate(class_keys)}
        bands = len(class_keys) + 1
        container = f"{project}-{node_id}"
        if len(class_keys) == 1:
            latency, loss, rate = class_keys[0]
            netem = f"delay {latency}ms"
            if loss > 0:
                netem += f" loss {loss}%"
            lines.extend([
                f"container={shlex.quote(container)}",
                f"echo 'applying single-class container latency fallback to {container}: {len(peer_rows)} peer rules, {netem}'",
                f"docker exec {shlex.quote(container)} tc qdisc replace dev eth0 root netem {netem}",
                "",
            ])
            continue
        lines.extend([
            f"container={shlex.quote(container)}",
            "veth=$(find_host_veth \"$container\")",
            "if [ -z \"$veth\" ]; then echo \"could not find host veth for $container\" >&2; exit 1; fi",
            f"echo 'applying host-veth latency to {container}: {len(peer_rows)} peer rules, {len(class_keys)} classes'",
            "sudo -n tc qdisc del dev \"$veth\" root 2>/dev/null || true",
            f"sudo -n tc qdisc add dev \"$veth\" root handle 1: prio bands {bands}",
        ])
        for key, band in class_by_key.items():
            latency, loss, rate = key
            netem = f"delay {latency}ms"
            if loss > 0:
                netem += f" loss {loss}%"
            # Some iproute2/kernel combinations reject netem rate on child qdiscs.
            # Keep bandwidth in the plan, but apply delay/loss here for portable latency evidence.
            handle = 10 + band
            lines.append(f"sudo -n tc qdisc add dev \"$veth\" parent 1:{band} handle {handle}: netem {netem}")
        for peer, link in peer_rows:
            latency = quantize_latency(link.latency_ms, options.quantization_ms)
            key = (latency, link.loss_pct, link.bandwidth_mbps)
            band = class_by_key[key]
            lines.append(
                f"sudo -n tc filter add dev \"$veth\" protocol ip parent 1: prio 10 u32 "
                f"match ip dst {peer['host']}/32 match ip dport {peer['tcp_port']} 0xffff flowid 1:{band}"
            )
        lines.append("")
    return "\n".join(lines)


def render_ebpf_latency_classifier_c() -> str:
    return """#include <linux/bpf.h>
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/tcp.h>
#include <linux/udp.h>

#ifndef IPPROTO_TCP
#define IPPROTO_TCP 6
#endif
#ifndef IPPROTO_UDP
#define IPPROTO_UDP 17
#endif
#ifndef TC_ACT_OK
#define TC_ACT_OK 0
#endif

#define SEC(NAME) __attribute__((section(NAME), used))

struct latency_key {
    __u32 ifindex;
    __u32 dst_ip;
    __u16 dst_port;
    __u16 pad;
};

struct latency_value {
    __u32 mark;
};

struct bpf_map_def {
    __u32 type;
    __u32 key_size;
    __u32 value_size;
    __u32 max_entries;
    __u32 map_flags;
};

struct bpf_map_def SEC(\"maps\") latency_class_map = {
    .type = BPF_MAP_TYPE_HASH,
    .key_size = sizeof(struct latency_key),
    .value_size = sizeof(struct latency_value),
    .max_entries = 1048576,
    .map_flags = 0,
};

static void *(*bpf_map_lookup_elem)(void *map, const void *key) = (void *)1;
static int (*bpf_skb_load_bytes)(struct __sk_buff *skb, int off, void *to, int len) = (void *)26;

SEC(\"classifier\")
int classify_latency(struct __sk_buff *skb)
{
    struct ethhdr eth;
    struct iphdr ip;
    __u16 dst_port = 0;
    int ip_offset = sizeof(struct ethhdr);
    int l4_offset;

    if (bpf_skb_load_bytes(skb, 0, &eth, sizeof(eth)) < 0)
        return TC_ACT_OK;
    if (eth.h_proto != __builtin_bswap16(ETH_P_IP))
        return TC_ACT_OK;
    if (bpf_skb_load_bytes(skb, ip_offset, &ip, sizeof(ip)) < 0)
        return TC_ACT_OK;
    if (ip.version != 4)
        return TC_ACT_OK;

    l4_offset = ip_offset + (ip.ihl * 4);
    if (ip.protocol == IPPROTO_TCP) {
        struct tcphdr tcp;
        if (bpf_skb_load_bytes(skb, l4_offset, &tcp, sizeof(tcp)) < 0)
            return TC_ACT_OK;
        dst_port = tcp.dest;
    } else if (ip.protocol == IPPROTO_UDP) {
        struct udphdr udp;
        if (bpf_skb_load_bytes(skb, l4_offset, &udp, sizeof(udp)) < 0)
            return TC_ACT_OK;
        dst_port = udp.dest;
    } else {
        return TC_ACT_OK;
    }

    struct latency_key key = {
        .ifindex = skb->ifindex,
        .dst_ip = ip.daddr,
        .dst_port = dst_port,
        .pad = 0,
    };
    struct latency_value *value = bpf_map_lookup_elem(&latency_class_map, &key);
    if (value)
        skb->mark = value->mark;
    return TC_ACT_OK;
}

char _license[] SEC(\"license\") = \"GPL\";
"""


def render_host_veth_ebpf_classifier_tc_script(
    project: str,
    node_ids: list[str],
    links: list[Link],
    peer_config: dict[str, dict[str, Any]],
    options: EmulationOptions,
) -> str:
    by_source: dict[str, dict[str, Link]] = {node_id: {} for node_id in node_ids}
    for link in links:
        if link.source in by_source:
            by_source[link.source][link.target] = link

    bpf_c = render_ebpf_latency_classifier_c()
    lines = [
        "#!/usr/bin/env sh",
        "set -eu",
        "if ! command -v tc >/dev/null 2>&1; then echo 'tc not found; cannot apply eBPF host-veth shaping' >&2; exit 1; fi",
        "if ! command -v ip >/dev/null 2>&1; then echo 'ip not found; cannot apply eBPF host-veth shaping' >&2; exit 1; fi",
        "if ! command -v bpftool >/dev/null 2>&1; then echo 'bpftool not found; cannot apply eBPF host-veth shaping' >&2; exit 1; fi",
        "BPF_CLANG=${BPF_CLANG:-}",
        "if [ -z \"$BPF_CLANG\" ]; then for candidate in clang clang-18 clang-17 clang-16 clang-15 clang-14 clang-13 clang-12; do if command -v \"$candidate\" >/dev/null 2>&1; then BPF_CLANG=$candidate; break; fi; done; fi",
        "if [ -z \"$BPF_CLANG\" ]; then echo 'clang not found; cannot compile eBPF latency classifier' >&2; exit 1; fi",
        "BPF_PIN=/sys/fs/bpf/distributed-emulator-latency-classifier",
        "BPF_C=/tmp/distributed-emulator-latency-classifier.c",
        "BPF_OBJ=/tmp/distributed-emulator-latency-classifier.o",
        "cat > \"$BPF_C\" <<'BPF_EOF'",
        bpf_c,
        "BPF_EOF",
        "\"$BPF_CLANG\" -O2 -target bpf -c \"$BPF_C\" -o \"$BPF_OBJ\"",
        "sudo -n rm -rf \"$BPF_PIN\"",
        "sudo -n mkdir -p \"$BPF_PIN\"",
        "sudo -n bpftool prog loadall \"$BPF_OBJ\" \"$BPF_PIN\" type sched_cls",
        "MAP_PIN=$BPF_PIN/latency_class_map",
        "PROG_PIN=$BPF_PIN/classify_latency",
        "hex_u16_be() { value=$1; printf '%02x %02x' $((value / 256)) $((value % 256)); }",
        "hex_u32_le() { value=$1; printf '%02x %02x %02x %02x' $((value % 256)) $(((value / 256) % 256)) $(((value / 65536) % 256)) $(((value / 16777216) % 256)); }",
        "ip_hex() { old_ifs=$IFS; IFS=.; set -- $1; IFS=$old_ifs; printf '%02x %02x %02x %02x' \"$1\" \"$2\" \"$3\" \"$4\"; }",
        "map_update() { ifindex=$1; ip=$2; port=$3; mark=$4; key=\"$(hex_u32_le \"$ifindex\") $(ip_hex \"$ip\") $(hex_u16_be \"$port\") 00 00\"; value=\"$(hex_u32_le \"$mark\")\"; sudo -n bpftool map update pinned \"$MAP_PIN\" key hex $key value hex $value; }",
        "find_host_veth() {",
        "  container=$1",
        "  ifindex=$(docker exec \"$container\" cat /sys/class/net/eth0/iflink)",
        "  sudo -n ip -o link | awk -F': ' -v idx=\"$ifindex\" '$1 == idx { split($2, a, \"@\"); print a[1]; exit }'",
        "}",
        "",
    ]
    for node_id in sorted(node_ids):
        peer_rows: list[tuple[dict[str, Any], Link]] = []
        seen: set[tuple[str, int]] = set()
        p2p = peer_config.get(node_id, {})
        for key in ("tcp_peers", "udp_peers"):
            for peer in parse_peer_entries(str(p2p.get(key, ""))):
                target = peer["node_id"]
                link = by_source.get(node_id, {}).get(target)
                if not link:
                    continue
                dedupe = (peer["host"], peer["tcp_port"])
                if dedupe in seen:
                    continue
                seen.add(dedupe)
                peer_rows.append((peer, link))
        if not peer_rows:
            continue
        class_keys = sorted(
            {
                (
                    quantize_latency(link.latency_ms, options.quantization_ms),
                    link.loss_pct,
                    link.bandwidth_mbps,
                )
                for _, link in peer_rows
            }
        )
        class_by_key = {key: idx + 1 for idx, key in enumerate(class_keys)}
        bands = len(class_keys) + 1
        container = f"{project}-{node_id}"
        lines.extend([
            f"container={shlex.quote(container)}",
            "veth=$(find_host_veth \"$container\")",
            "if [ -z \"$veth\" ]; then echo \"could not find host veth for $container\" >&2; exit 1; fi",
            "ifindex=$(cat /sys/class/net/$veth/ifindex)",
            f"echo 'applying eBPF host-veth latency to {container}: {len(peer_rows)} map entries, {len(class_keys)} classes'",
            "sudo -n tc qdisc del dev \"$veth\" root 2>/dev/null || true",
            "sudo -n tc qdisc del dev \"$veth\" clsact 2>/dev/null || true",
            f"sudo -n tc qdisc add dev \"$veth\" root handle 1: prio bands {bands}",
        ])
        for key, band in class_by_key.items():
            latency, loss, rate = key
            netem = f"delay {latency}ms"
            if loss > 0:
                netem += f" loss {loss}%"
            # Some iproute2/kernel combinations reject netem rate on child qdiscs.
            # Keep bandwidth in the plan, but apply delay/loss here for portable latency evidence.
            handle = 10 + band
            lines.append(f"sudo -n tc qdisc add dev \"$veth\" parent 1:{band} handle {handle}: netem {netem}")
            lines.append(f"sudo -n tc filter add dev \"$veth\" protocol ip parent 1: prio 10 handle {band} fw flowid 1:{band}")
        lines.append("sudo -n tc qdisc add dev \"$veth\" clsact")
        lines.append("sudo -n tc filter replace dev \"$veth\" egress bpf object-pinned \"$PROG_PIN\" direct-action")
        for peer, link in peer_rows:
            latency = quantize_latency(link.latency_ms, options.quantization_ms)
            mark = class_by_key[(latency, link.loss_pct, link.bandwidth_mbps)]
            lines.append(f"map_update \"$ifindex\" {shlex.quote(peer['host'])} {peer['tcp_port']} {mark}")
        lines.append("")
    return "\n".join(lines)

def render_compose(
    project: str,
    host: Host,
    nodes: list[Node],
    options: EmulationOptions,
    peer_config: dict[str, dict[str, Any]],
    topology: dict[str, Any],
    static_ips: dict[str, str],
) -> str:
    if not nodes:
        return "services: {}\n"

    lines = ["services:"]
    networks = sorted({node.network for node in nodes})

    for node in nodes:
        image = node.image
        command = ["python", "/app/blockchain_daemon.py"] if options.workload_enabled else node.command
        p2p = peer_config.get(node.id, {})
        lines.extend(
            [
                f"  {node.id}:",
                f"    image: {yaml_scalar(image)}",
                f"    container_name: {yaml_scalar(project + '-' + node.id)}",
                "    restart: unless-stopped",
                "    cap_add:",
                "      - NET_ADMIN",
                "    mem_limit: " + yaml_scalar(f"{node.memory_mb}m"),
                "    environment:",
                f"      TIME_INFLATION_FACTOR: {yaml_scalar(str(options.time_inflation_factor))}",
                f"      EMULATION_NODE_ID: {yaml_scalar(node.id)}",
                f"      P2P_TCP_PORT: {yaml_scalar(str(options.container_p2p_port))}",
                f"      P2P_UDP_PORT: {yaml_scalar(str(options.container_p2p_port))}",
                f"      P2P_TCP_PEERS: {yaml_scalar(str(p2p.get('tcp_peers', '')))}",
                f"      P2P_UDP_PEERS: {yaml_scalar(str(p2p.get('udp_peers', '')))}",
                f"      P2P_TCP_PEER_COUNT: {yaml_scalar(str(p2p.get('tcp_peer_count', 0)))}",
                f"      P2P_UDP_PEER_COUNT: {yaml_scalar(str(p2p.get('udp_peer_count', 0)))}",
                f"      BLOCK_INTERVAL_MS: {yaml_scalar(str(options.block_interval_ms))}",
            ]
        )
        for key, value in sorted(node.env.items()):
            lines.append(f"      {key}: {yaml_scalar(value)}")
        if node.id in static_ips:
            lines.extend(
                [
                    "    networks:",
                    f"      {node.network}:",
                    f"        ipv4_address: {yaml_scalar(static_ips[node.id])}",
                ]
            )
        else:
            lines.extend(
                [
                    "    networks:",
                    f"      - {node.network}",
                ]
            )
        if command:
            encoded = ", ".join(yaml_scalar(part) for part in command)
            lines.append(f"    command: [{encoded}]")
        if options.workload_enabled:
            lines.append("    volumes:")
            lines.append("      - ./blockchain_daemon.py:/app/blockchain_daemon.py:ro")
        ports = list(node.ports)
        if options.workload_enabled and options.publish_ports:
            ports.extend(
                [
                    f"{p2p['tcp_port']}:{options.container_p2p_port}/tcp",
                    f"{p2p['udp_port']}:{options.container_p2p_port}/udp",
                ]
            )
        if ports:
            lines.append("    ports:")
            for port in ports:
                lines.append(f"      - {yaml_scalar(port)}")

    overlay = overlay_config(topology)
    lines.append("networks:")
    for network in networks:
        lines.extend(
            [
                f"  {network}:",
                f"    name: {yaml_scalar(project + '-' + host.name + '-' + network)}",
                "    driver: bridge",
                "    driver_opts:",
                f"      com.docker.network.bridge.name: {yaml_scalar(host.bridge_name)}",
            ]
        )
        if overlay["enabled"]:
            lines.extend(
                [
                    "    ipam:",
                    "      config:",
                    f"        - subnet: {yaml_scalar(overlay['subnet'])}",
                    f"          gateway: {yaml_scalar(overlay['gateway_by_host'].get(host.name, overlay['gateway']))}",
                ]
            )
    return "\n".join(lines) + "\n"

def render_bridge_script(host: Host) -> str:
    return "\n".join(
        [
            "#!/usr/bin/env sh",
            "set -eu",
            f"BRIDGE={shlex.quote(host.bridge_name)}",
            "if ! command -v ip >/dev/null 2>&1; then",
            "  echo 'ip command not found; cannot inspect bridge' >&2",
            "  exit 1",
            "fi",
            "if ip link show \"$BRIDGE\" >/dev/null 2>&1; then",
            "  echo \"virtual bridge $BRIDGE exists\"",
            "else",
            "  echo \"virtual bridge $BRIDGE will be created by docker compose\"",
            "fi",
            "ip link show \"$BRIDGE\" 2>/dev/null || true",
            "",
        ]
    )


def render_class_plan(links: list[Link], options: EmulationOptions) -> str:
    classes = build_latency_classes(links, options)
    payload = {
        latency_class_id(latency): [
            {
                "source": link.source,
                "target": link.target,
                "latency_ms": latency,
                "original_latency_ms": link.latency_ms,
                "loss_pct": link.loss_pct,
                "bandwidth_mbps": link.bandwidth_mbps,
            }
            for link in class_links
        ]
        for latency, class_links in classes.items()
    }
    return json.dumps(payload, indent=2) + "\n"


def render_tc_script(project: str, node_ids: list[str], links: list[Link], options: EmulationOptions) -> str:
    by_source: dict[str, list[Link]] = {node_id: [] for node_id in node_ids}
    for link in links:
        if link.source in by_source:
            by_source[link.source].append(link)

    lines = [
        "#!/usr/bin/env sh",
        "set -eu",
        "if ! command -v tc >/dev/null 2>&1; then",
        "  echo 'tc not found; skipping netem shaping' >&2",
        "  exit 0",
        "fi",
        "",
    ]

    for node_id, node_links in sorted(by_source.items()):
        if not node_links:
            continue
        container = f"{project}-{node_id}"
        latency = max(link.latency_ms for link in node_links)
        loss = max(link.loss_pct for link in node_links)
        rates = [link.bandwidth_mbps for link in node_links if link.bandwidth_mbps]
        rate = min(rates) if rates else None

        latency = quantize_latency(latency, options.quantization_ms)
        netem = f"delay {latency}ms"
        if loss > 0:
            netem += f" loss {loss}%"
        if rate:
            netem += f" rate {rate}mbit"

        class_name = latency_class_id(latency)
        targets = ",".join(link.target for link in node_links)
        lines.extend(
            [
                f"echo 'applying {class_name} to {container} for targets [{targets}]: {netem}'",
                f"docker exec {shlex.quote(container)} sh -c "
                + shlex.quote(
                    "command -v tc >/dev/null 2>&1 || "
                    "(command -v apk >/dev/null 2>&1 && apk add --no-cache iproute2)"
                ),
                f"docker exec {shlex.quote(container)} sh -c "
                + shlex.quote("tc qdisc del dev eth0 root 2>/dev/null || true"),
                f"docker exec {shlex.quote(container)} tc qdisc add dev eth0 root netem {netem}",
                "",
            ]
        )

    return "\n".join(lines)


def write_plan(topology: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    project = topology.get("project", "distributed-emulator")
    hosts = parse_hosts(topology)
    nodes = parse_nodes(topology)
    options = parse_emulation_options(topology)
    placement = place_nodes(hosts, nodes)
    static_ips = container_ip_map(topology, nodes)
    peer_config = build_peer_config(topology, hosts, nodes, placement, options)
    if options.rule_mode in {"port-exact", "host-veth-exact", "ebpf-classifier"}:
        links = build_peer_links(topology, nodes, placement, peer_config)
    else:
        links = parse_links(topology, options)
    nodes_by_host = {host.name: [] for host in hosts}
    for node in nodes:
        nodes_by_host[placement[node.id]].append(node)

    output_dir.mkdir(parents=True, exist_ok=True)
    plan = {
        "project": project,
        "hosts": [],
        "placement": placement,
        "link_count": logical_link_count(topology, links),
        "materialized_rule_count": len(links),
        "quantization_ms": options.quantization_ms,
        "rule_mode": options.rule_mode,
        "time_inflation_factor": options.time_inflation_factor,
        "workload_enabled": options.workload_enabled,
        "target_tcp_connections": options.target_tcp_connections,
        "target_udp_connections": options.target_udp_connections,
        "publish_ports": options.publish_ports,
        "cross_host_peers": options.cross_host_peers,
        "latency_classes": sorted(
            latency_class_id(latency) for latency in build_latency_classes(links, options)
        ),
        "host_latency_ms": topology.get("host_latency_ms", topology.get("host_base_latency_ms", {})),
        "host_latency_policy": topology.get("host_latency_policy", "subtract_from_emulated_delay"),
        "ebpf": topology.get("ebpf", {}),
        "network": topology.get("network", {}),
        "peer_topology": topology.get("peer_topology", {"type": "ring-offset"}),
        "static_ips": static_ips,
    }

    for host in hosts:
        host_dir = output_dir / host.name
        host_dir.mkdir(parents=True, exist_ok=True)
        host_nodes = nodes_by_host[host.name]
        host_links = [link for link in links if placement.get(link.source) == host.name]
        compose_path = host_dir / "compose.yaml"
        workload_path = host_dir / "blockchain_daemon.py"
        tc_path = host_dir / "tc-commands.sh"
        bridge_path = host_dir / "bridge-check.sh"
        vxlan_path = host_dir / "vxlan-setup.sh"
        class_plan_path = host_dir / "latency-classes.json"
        compose_path.write_text(
            render_compose(project, host, host_nodes, options, peer_config, topology, static_ips),
            encoding="utf-8",
        )
        if options.workload_enabled:
            workload_path.write_text(WORKLOAD_DAEMON.read_text(encoding="utf-8"), encoding="utf-8")
        if options.rule_mode == "port-exact":
            tc_script = render_port_exact_tc_script(
                project, [node.id for node in host_nodes], host_links, peer_config, options
            )
        elif options.rule_mode == "host-veth-exact":
            tc_script = render_host_veth_exact_tc_script(
                project, [node.id for node in host_nodes], host_links, peer_config, options
            )
        elif options.rule_mode == "ebpf-classifier":
            tc_script = render_host_veth_ebpf_classifier_tc_script(
                project, [node.id for node in host_nodes], host_links, peer_config, options
            )
        else:
            tc_script = render_tc_script(project, [node.id for node in host_nodes], host_links, options)
        tc_path.write_text(tc_script, encoding="utf-8")
        bridge_path.write_text(render_bridge_script(host), encoding="utf-8")
        vxlan_path.write_text(render_vxlan_script(host, hosts, topology), encoding="utf-8")
        class_plan_path.write_text(render_class_plan(host_links, options), encoding="utf-8")
        tc_path.chmod(0o755)
        bridge_path.chmod(0o755)
        vxlan_path.chmod(0o755)
        plan["hosts"].append(
            {
                "name": host.name,
                "ssh_target": host.ssh_target,
                "bridge_name": host.bridge_name,
                "memory_mb": host.memory_mb,
                "used_memory_mb": sum(node.memory_mb for node in host_nodes),
                "nodes": [node.id for node in host_nodes],
                "compose": str(compose_path),
                "tc_script": str(tc_path),
                "bridge_script": str(bridge_path),
                "vxlan_script": str(vxlan_path),
                "class_plan": str(class_plan_path),
                "workload": str(workload_path) if options.workload_enabled else None,
            }
        )

    plan_path = output_dir / "placement.json"
    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    return plan


def run(command: list[str]) -> None:
    print("+ " + " ".join(shlex.quote(part) for part in command))
    subprocess.run(command, check=True)


def is_local_target(target: str) -> bool:
    return target in {"", "localhost", "127.0.0.1", "::1"}


def apply_plan(plan: dict[str, Any], remote_workdir: str) -> None:
    for host in plan["hosts"]:
        target = host["ssh_target"]
        remote_dir = f"{remote_workdir}/{host['name']}"
        if is_local_target(target):
            local_dir = Path(remote_dir)
            local_dir.mkdir(parents=True, exist_ok=True)
            sources = [host["compose"], host["tc_script"], host["bridge_script"], host.get("vxlan_script", "")]
            sources = [source for source in sources if source]
            if host.get("workload"):
                sources.append(host["workload"])
            for source in sources:
                source_path = Path(source)
                destination = local_dir / source_path.name
                destination.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
                if source_path.name.endswith(".sh"):
                    destination.chmod(0o755)
            run(["docker", "compose", "-f", f"{remote_dir}/compose.yaml", "up", "-d"])
            run(["sh", f"{remote_dir}/bridge-check.sh"])
            if host.get("vxlan_script"):
                run(["sh", f"{remote_dir}/vxlan-setup.sh"])
            run(["sh", f"{remote_dir}/tc-commands.sh"])
            continue

        run(["ssh", target, "mkdir", "-p", remote_dir])
        run(
            [
                "scp",
                host["compose"],
                host["tc_script"],
                host["bridge_script"],
                *([host["vxlan_script"]] if host.get("vxlan_script") else []),
                *([host["workload"]] if host.get("workload") else []),
                f"{target}:{remote_dir}/",
            ]
        )
        run(
            [
                "ssh",
                target,
                "docker",
                "compose",
                "-f",
                f"{remote_dir}/compose.yaml",
                "up",
                "-d",
            ]
        )
        run(["ssh", target, "sh", f"{remote_dir}/bridge-check.sh"])
        if host.get("vxlan_script"):
            run(["ssh", target, "sh", f"{remote_dir}/vxlan-setup.sh"])
        run(["ssh", target, "sh", f"{remote_dir}/tc-commands.sh"])


def print_summary(plan: dict[str, Any], output_dir: Path) -> None:
    print(f"project: {plan['project']}")
    print(f"output: {output_dir}")
    print(f"links: {plan['link_count']}")
    print(f"materialized_rules: {plan['materialized_rule_count']}")
    for host in plan["hosts"]:
        used = host["used_memory_mb"]
        total = host["memory_mb"]
        nodes = host["nodes"]
        if not nodes:
            node_list = "(none)"
        elif len(nodes) <= 12:
            node_list = ", ".join(nodes)
        else:
            head = ", ".join(nodes[:6])
            tail = ", ".join(nodes[-3:])
            node_list = f"{head}, ... {tail} ({len(nodes)} nodes)"
        print(
            f"- {host['name']}: {used}/{total} MB, bridge={host['bridge_name']} -> {node_list}"
        )
    print(f"quantization: {plan['quantization_ms']} ms")
    print(f"rule_mode: {plan['rule_mode']}")
    if plan.get("network"):
        print(f"network: {plan['network']}")
    if plan.get("peer_topology"):
        print(f"peer_topology: {plan['peer_topology']}")
    if plan.get("host_latency_ms"):
        print(f"host_latency_policy: {plan['host_latency_policy']}")
        print(f"host_latency_ms: {plan['host_latency_ms']}")
    if plan.get("ebpf", {}).get("enabled"):
        print(f"ebpf: enabled ({plan['ebpf'].get('mode', 'tcp-rto')})")
    print(f"time_inflation: {plan['time_inflation_factor']}x")
    print(f"workload_enabled: {plan['workload_enabled']}")
    if plan.get("target_tcp_connections") is not None:
        print(f"target_tcp_connections: {plan['target_tcp_connections']}")
    if plan.get("target_udp_connections") is not None:
        print(f"target_udp_connections: {plan['target_udp_connections']}")
    print(f"publish_ports: {plan['publish_ports']}")
    print(f"cross_host_peers: {plan['cross_host_peers']}")
    print("latency_classes: " + ", ".join(plan["latency_classes"]))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["plan", "apply"])
    parser.add_argument("topology", type=Path)
    parser.add_argument("--output-dir", type=Path, default=BUILD_DIR)
    args = parser.parse_args(argv)

    topology = load_topology(args.topology)
    output_dir = args.output_dir
    plan = write_plan(topology, output_dir)
    print_summary(plan, output_dir)

    if args.command == "apply":
        remote_workdir = topology.get("remote_workdir", "/home/blockchain/distributed-emulator-run")
        apply_plan(plan, remote_workdir)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)

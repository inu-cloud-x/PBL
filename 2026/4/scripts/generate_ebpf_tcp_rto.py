#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path


def load_controller():
    controller_path = Path(__file__).with_name("distributed_emulator.py")
    spec = importlib.util.spec_from_file_location("distributed_emulator", controller_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load distributed_emulator.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def render_c(timeout_seconds: int, hz: int) -> str:
    return """#include <linux/bpf.h>

#ifndef __section
# define __section(NAME) __attribute__((section(NAME), used))
#endif

__section(\"sockops\")
int set_initial_rto(struct bpf_sock_ops *skops)
{
    const int timeout = %d;
    const int hz = %d;

    int op = (int) skops->op;
    if (op == BPF_SOCK_OPS_TIMEOUT_INIT) {
        skops->reply = hz * timeout;
        return 1;
    }

    return 1;
}

char _license[] __section(\"license\") = \"GPL\";
""" % (timeout_seconds, hz)


def render_load() -> str:
    return """#!/usr/bin/env sh
set -eu
clang -O2 -target bpf -c tcp-rto.c -o tcp-rto.o
sudo bpftool prog load tcp-rto.o /sys/fs/bpf/distributed-emulator-tcp-rto
PROG_ID=$(sudo bpftool prog show | awk '/set_initial_rto/ { sub(\":\", \"\", $1); print $1; exit }')
sudo bpftool cgroup attach /sys/fs/cgroup sock_ops id \"$PROG_ID\"
echo \"loaded distributed-emulator tcp-rto eBPF program id=$PROG_ID\"
"""


def render_unload() -> str:
    return """#!/usr/bin/env sh
set -eu
PROG_ID=$(sudo bpftool prog show | awk '/set_initial_rto/ { sub(\":\", \"\", $1); print $1; exit }')
if [ -n \"${PROG_ID:-}\" ]; then
  sudo bpftool cgroup detach /sys/fs/cgroup sock_ops id \"$PROG_ID\" 2>/dev/null || true
fi
sudo rm -f /sys/fs/bpf/distributed-emulator-tcp-rto
echo \"unloaded distributed-emulator tcp-rto eBPF program\"
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate eBPF TCP initial-RTO scripts for an emulation topology.")
    parser.add_argument("topology", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("build/ebpf-tcp-rto"))
    parser.add_argument("--hz", type=int, default=250)
    parser.add_argument("--min-timeout-seconds", type=int, default=3)
    args = parser.parse_args()

    de = load_controller()
    topology = de.load_topology(args.topology)
    hosts = de.parse_hosts(topology)
    nodes = de.parse_nodes(topology)
    options = de.parse_emulation_options(topology)
    placement = de.place_nodes(hosts, nodes)
    peer_config = de.build_peer_config(topology, hosts, nodes, placement, options)
    if options.rule_mode == "port-exact":
        links = de.build_peer_links(topology, nodes, placement, peer_config)
    else:
        links = de.parse_links(topology, options)

    max_latency_ms = max((link.latency_ms for link in links), default=0)
    timeout_seconds = max(args.min_timeout_seconds, math.ceil(max_latency_ms / 1000) * 2)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "topology": str(args.topology),
        "max_netem_latency_ms": max_latency_ms,
        "timeout_seconds": timeout_seconds,
        "hz": args.hz,
        "hosts": [host.name for host in hosts],
        "mode": "tcp initial RTO sock_ops",
    }
    for host in hosts:
        host_dir = args.output_dir / host.name
        host_dir.mkdir(parents=True, exist_ok=True)
        (host_dir / "tcp-rto.c").write_text(render_c(timeout_seconds, args.hz), encoding="utf-8")
        for name, script in (("load-ebpf-tcp-rto.sh", render_load()), ("unload-ebpf-tcp-rto.sh", render_unload())):
            path = host_dir / name
            path.write_text(script, encoding="utf-8")
            path.chmod(0o755)
    (args.output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(args.output_dir / "metadata.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

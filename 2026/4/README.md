prototype for scalable multi-host blockchain network
emulation. It distributes lightweight blockchain containers across multiple
machines, connects per-host Docker bridges with VXLAN, and applies matrix-based
latency control with Linux `tc netem`.

## Key Features

- Memory-aware container placement across multiple machines.
- One Docker Compose file per host.
- Per-host Docker virtual bridge creation.
- Bridge-to-bridge VXLAN overlay for container-to-container communication.
- Matrix-based latency/loss/bandwidth planning with 10 ms quantization.
- Small-world peer topology generation.
- Lightweight blockchain-like P2P daemon.
- Evidence scripts for matrix-to-`tc netem` verification and cross-host logs.
- Prototype eBPF classifier mode for latency class lookup through BPF maps.

## Repository Layout

```text
scripts/     controller, topology generator, measurement, evidence tools
workload/    lightweight blockchain daemon and Dockerfile
```

## Quick Start

Install Docker on each host:

```bash
scripts/install_docker_ubuntu.sh
```

Build the lightweight workload image:

```bash
docker build -t p2p-blockchain-daemon:latest workload
```

Generate a two-host smoke topology:

```bash
python3 scripts/generate_scale_topology.py 2 \
  --evaluation \
  --network-mode vxlan \
  --peer-topology ring-offset \
  --rule-mode host-veth-exact \
  --container-memory-mb 220 \
  --target-tcp-connections 2 \
  --target-udp-connections 2 \
  --no-publish-ports \
  --cross-host-peers \
  --output examples/evaluation-crosshost-2.json
```

Apply it:

```bash
sg docker -c 'python3 scripts/distributed_emulator.py apply examples/evaluation-crosshost-2.json --output-dir build/evaluation-crosshost-2'
```

Collect cross-host latency evidence:

```bash
python3 scripts/collect_crosshost_latency_evidence.py \
  build/evaluation-crosshost-2/placement.json \
  --output reports/evaluation-crosshost-2-crosshost-latency-evidence.json
```

Verify generated matrix application:

```bash
python3 scripts/verify_matrix_application.py \
  build/evaluation-crosshost-2/placement.json \
  --output reports/evaluation-crosshost-2-matrix-proof.json
```

## Notes

- This is a research prototype, not a production blockchain client.
- The workload is intentionally lightweight and Python-based.
- `tc netem` performs the actual latency/loss shaping.
- The eBPF classifier mode is for latency class lookup optimization and requires
  `clang`, `bpftool`, and compatible kernel support.
- Large generated directories such as `build/` are intentionally excluded from
  this GitHub upload bundle.

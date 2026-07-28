#!/usr/bin/env python3
"""Tiny blockchain-like P2P daemon for emulation workloads.

It is intentionally not a real blockchain client. It creates TCP and UDP peer
traffic, advances a lightweight block height, and reports simple status lines so
container counts, socket counts, and network emulation can be measured.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Peer:
    node_id: str
    host: str
    tcp_port: int
    udp_port: int


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def parse_peers(raw: str) -> list[Peer]:
    peers: list[Peer] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        node_id, host, tcp_port, udp_port = item.split(":", 3)
        peers.append(Peer(node_id, host, int(tcp_port), int(udp_port)))
    return peers


NODE_ID = os.environ.get("EMULATION_NODE_ID", "node")
TCP_PORT = env_int("P2P_TCP_PORT", 9000)
UDP_PORT = env_int("P2P_UDP_PORT", 9000)
TIME_INFLATION = env_float("TIME_INFLATION_FACTOR", 1.0)
BLOCK_INTERVAL_MS = env_int("BLOCK_INTERVAL_MS", 1000)
TCP_PEERS = parse_peers(os.environ.get("P2P_TCP_PEERS", os.environ.get("P2P_PEERS", "")))
UDP_PEERS = parse_peers(os.environ.get("P2P_UDP_PEERS", os.environ.get("P2P_PEERS", "")))
STATE = {"height": 0, "tcp_in": 0, "udp_in": 0, "tcp_out": 0, "udp_out": 0}
STATE_LOCK = threading.Lock()
RESEARCH_STATE_MB = env_int("RESEARCH_STATE_MB", 0)
TRANSACTIONS_PER_BLOCK = env_int("TRANSACTIONS_PER_BLOCK", 20)
RESEARCH_STATE: list[bytearray] = []
CHAIN: list[dict[str, str | int]] = []
MEMPOOL: list[dict[str, str | int]] = []


def inflated_sleep(ms: int) -> None:
    time.sleep((ms / 1000.0) * TIME_INFLATION)


def initialize_research_state() -> None:
    """Keep deterministic in-memory state similar to a research blockchain node."""
    if RESEARCH_STATE_MB <= 0:
        return
    chunk_size = 1024 * 1024
    seed = hashlib.sha256(NODE_ID.encode()).digest()
    for idx in range(RESEARCH_STATE_MB):
        chunk = bytearray(chunk_size)
        pattern = hashlib.sha256(seed + idx.to_bytes(4, "big")).digest()
        for offset in range(0, chunk_size, len(pattern)):
            chunk[offset : offset + len(pattern)] = pattern[: chunk_size - offset]
        RESEARCH_STATE.append(chunk)


def tcp_server() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", TCP_PORT))
    server.listen(256)
    while True:
        conn, _ = server.accept()
        threading.Thread(target=handle_tcp_peer, args=(conn,), daemon=True).start()


def handle_tcp_peer(conn: socket.socket) -> None:
    with conn:
        conn.settimeout(30)
        while True:
            data = conn.recv(4096)
            if not data:
                return
            with STATE_LOCK:
                STATE["tcp_in"] += 1
                payload = json.dumps({"node": NODE_ID, "height": STATE["height"]})
            conn.sendall((payload + "\n").encode())


def udp_server() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", UDP_PORT))
    while True:
        data, addr = sock.recvfrom(4096)
        if data:
            with STATE_LOCK:
                STATE["udp_in"] += 1
                payload = json.dumps({"node": NODE_ID, "height": STATE["height"]})
            sock.sendto(payload.encode(), addr)


def tcp_client(peer: Peer) -> None:
    while True:
        try:
            with socket.create_connection((peer.host, peer.tcp_port), timeout=5) as conn:
                conn.settimeout(10)
                while True:
                    with STATE_LOCK:
                        height = STATE["height"]
                        STATE["tcp_out"] += 1
                    payload = json.dumps({"from": NODE_ID, "height": height})
                    conn.sendall((payload + "\n").encode())
                    conn.recv(4096)
                    inflated_sleep(BLOCK_INTERVAL_MS)
        except OSError:
            inflated_sleep(1000)


def udp_clients(peers: list[Peer]) -> None:
    sockets: list[tuple[Peer, socket.socket]] = []
    for peer in peers:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.01)
        sockets.append((peer, sock))

    while True:
        for peer, sock in sockets:
            try:
                with STATE_LOCK:
                    height = STATE["height"]
                    STATE["udp_out"] += 1
                payload = json.dumps({"from": NODE_ID, "height": height}).encode()
                sock.sendto(payload, (peer.host, peer.udp_port))
                try:
                    sock.recvfrom(4096)
                except socket.timeout:
                    pass
            except OSError:
                pass
        inflated_sleep(BLOCK_INTERVAL_MS)


def block_clock() -> None:
    while True:
        inflated_sleep(BLOCK_INTERVAL_MS)
        with STATE_LOCK:
            STATE["height"] += 1
            height = STATE["height"]
            previous = CHAIN[-1]["hash"] if CHAIN else "genesis"
            txs = []
            for index in range(TRANSACTIONS_PER_BLOCK):
                digest = hashlib.sha256(f"{NODE_ID}:{height}:{index}:{previous}".encode()).hexdigest()
                tx = {"height": height, "index": index, "txid": digest}
                txs.append(tx)
                MEMPOOL.append(tx)
            merkleish = hashlib.sha256(("".join(tx["txid"] for tx in txs) + str(previous)).encode()).hexdigest()
            CHAIN.append({"height": height, "tx_count": len(txs), "hash": merkleish})
            if len(CHAIN) > 512:
                del CHAIN[: len(CHAIN) - 512]
            if len(MEMPOOL) > 4096:
                del MEMPOOL[: len(MEMPOOL) - 4096]


def reporter() -> None:
    while True:
        inflated_sleep(5000)
        with STATE_LOCK:
            snapshot = dict(STATE)
        print(json.dumps({"node": NODE_ID, "tcp_peers": len(TCP_PEERS), "udp_peers": len(UDP_PEERS), **snapshot}), flush=True)


def main() -> None:
    print(
        json.dumps(
            {
                "node": NODE_ID,
                "tcp_port": TCP_PORT,
                "udp_port": UDP_PORT,
                "tcp_peers": [peer.node_id for peer in TCP_PEERS],
                "udp_peers": [peer.node_id for peer in UDP_PEERS],
                "time_inflation": TIME_INFLATION,
                "research_state_mb": RESEARCH_STATE_MB,
                "transactions_per_block": TRANSACTIONS_PER_BLOCK,
            }
        ),
        flush=True,
    )
    initialize_research_state()
    threading.Thread(target=tcp_server, daemon=True).start()
    threading.Thread(target=udp_server, daemon=True).start()
    threading.Thread(target=block_clock, daemon=True).start()
    threading.Thread(target=reporter, daemon=True).start()
    for peer in TCP_PEERS:
        threading.Thread(target=tcp_client, args=(peer,), daemon=True).start()
    threading.Thread(target=udp_clients, args=(UDP_PEERS,), daemon=True).start()
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()

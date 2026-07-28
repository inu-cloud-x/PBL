#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


def render(data: dict, output: Path) -> None:
    rows = [
        ("Docker 컨테이너 수", f"{data['docker_containers_planned']}개 계획 / {data['docker_containers_actual']}", "#fff4c9", True),
        ("TCP 연결", f"목표 약 {data['tcp_connections_target']}개", "#ffffff", False),
        ("UDP 연결", f"목표 약 {data['udp_connections_target']}개", "#ffffff", False),
        ("Block time", data["block_time"], "#ffffff", False),
        ("Workload", data["workload"], "#ffffff", False),
        ("Time inflation", data["time_inflation"], "#ffffff", False),
        ("RAM 사용량", data["ram"], "#f5dfcc", True),
        ("CPU 사용률", data["cpu"], "#fff4c9", True),
        ("Evaluation status", data["status"], "#ffd9d9", True),
        ("Failure reason", data["failure_reason"], "#ffd9d9", False),
    ]
    width = 1600
    left = 520
    row_h = 86
    height = row_h * len(rows) + 8
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
    ]
    for i, (label, value, fill, bold) in enumerate(rows):
        y = i * row_h + 4
        weight = "800" if bold else "500"
        svg.extend([
            f'<rect x="4" y="{y}" width="{left}" height="{row_h}" fill="#d9d9d9" stroke="black" stroke-width="8"/>',
            f'<rect x="{left+4}" y="{y}" width="{width-left-8}" height="{row_h}" fill="{fill}" stroke="black" stroke-width="8"/>',
            f'<text x="28" y="{y+56}" font-family="Arial, Noto Sans CJK KR, sans-serif" font-size="48" font-weight="500">{html.escape(label)}</text>',
            f'<text x="{left+28}" y="{y+56}" font-family="Arial, Noto Sans CJK KR, sans-serif" font-size="44" font-weight="{weight}" font-style="italic">{html.escape(str(value))}</text>',
        ])
    svg.append('</svg>')
    output.write_text("\n".join(svg), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("summary", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    render(json.loads(args.summary.read_text(encoding="utf-8")), args.output)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

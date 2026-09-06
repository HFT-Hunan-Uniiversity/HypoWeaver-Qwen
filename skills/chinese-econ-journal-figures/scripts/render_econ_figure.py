#!/usr/bin/env python3
"""Render reproducible grayscale figures for Chinese economics manuscripts."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


def _font() -> font_manager.FontProperties:
    candidates = [
        Path("C:/Windows/Fonts/simsun.ttc"),
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return font_manager.FontProperties(fname=str(candidate))
    return font_manager.FontProperties(family="DejaVu Sans")


FONT = _font()
matplotlib.rcParams["axes.unicode_minus"] = False


def _validate_interval(estimate: float, lower: float, upper: float, label: str) -> None:
    if lower > estimate or estimate > upper:
        raise ValueError(f"Invalid interval for {label}: expected lower <= estimate <= upper")


def _apply_axes_style(ax: plt.Axes) -> None:
    ax.set_facecolor("white")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_linewidth(0.8)
    ax.spines["bottom"].set_linewidth(0.8)
    ax.tick_params(axis="both", width=0.7, length=3, labelsize=9)
    for label in [*ax.get_xticklabels(), *ax.get_yticklabels()]:
        label.set_fontproperties(FONT)


def _provenance_tag(ax: plt.Axes, status: str) -> None:
    if status in {"demo", "simulated"}:
        label = "预置示范估计" if status == "demo" else "模拟数据"
        ax.text(
            0.99,
            0.99,
            label,
            transform=ax.transAxes,
            ha="right",
            va="top",
            color="#555555",
            fontsize=8,
            fontproperties=FONT,
            bbox={"facecolor": "white", "edgecolor": "#777777", "linewidth": 0.6, "pad": 2.5},
        )


def _render_event_study(spec: dict[str, Any]) -> plt.Figure:
    x = spec["x"]
    estimate = spec["estimate"]
    lower = spec["lower"]
    upper = spec["upper"]
    if not (len(x) == len(estimate) == len(lower) == len(upper)):
        raise ValueError("event_study arrays must have equal lengths")
    if x != sorted(x):
        raise ValueError("event_study x values must be sorted")
    for period, est, low, high in zip(x, estimate, lower, upper):
        _validate_interval(est, low, high, str(period))

    figure, ax = plt.subplots(figsize=(7.2, 4.35))
    _apply_axes_style(ax)
    errors = [[est - low for est, low in zip(estimate, lower)], [high - est for est, high in zip(estimate, upper)]]
    ax.errorbar(
        x,
        estimate,
        yerr=errors,
        fmt="o-",
        color="#111111",
        ecolor="#333333",
        linewidth=1.1,
        elinewidth=0.9,
        markersize=4.5,
        capsize=3,
        markerfacecolor="white",
        markeredgewidth=1.0,
    )
    ax.axhline(0, color="#555555", linestyle=(0, (3, 3)), linewidth=0.8)
    ax.axvline(spec.get("policy_time", 0), color="#888888", linestyle="-", linewidth=0.75)
    ax.set_xticks(x)
    ax.set_xticklabels(spec.get("x_labels", [str(value) for value in x]), fontproperties=FONT)
    ax.set_xlabel(spec.get("x_label", "相对政策时点"), fontproperties=FONT, fontsize=10)
    ax.set_ylabel(spec.get("y_label", "估计系数"), fontproperties=FONT, fontsize=10)
    if "y_limits" in spec:
        ax.set_ylim(*spec["y_limits"])
    ref = spec.get("reference_period")
    if ref is not None:
        ax.annotate(
            f"基期：{ref}",
            xy=(ref, 0),
            xytext=(5, -18),
            textcoords="offset points",
            fontsize=8,
            color="#555555",
            fontproperties=FONT,
        )
    _provenance_tag(ax, spec.get("provenance", "estimated"))
    figure.tight_layout(pad=1.1)
    return figure


def _render_coefficient(spec: dict[str, Any]) -> plt.Figure:
    rows = spec["rows"]
    if not rows:
        raise ValueError("coefficient plot requires at least one row")
    for row in rows:
        _validate_interval(row["estimate"], row["lower"], row["upper"], row["label"])

    figure, ax = plt.subplots(figsize=(7.2, max(3.6, 0.56 * len(rows) + 1.6)))
    _apply_axes_style(ax)
    ordered = list(reversed(rows))
    y = list(range(len(ordered)))
    estimates = [row["estimate"] for row in ordered]
    lower = [row["lower"] for row in ordered]
    upper = [row["upper"] for row in ordered]
    errors = [[est - low for est, low in zip(estimates, lower)], [high - est for est, high in zip(estimates, upper)]]
    ax.errorbar(
        estimates,
        y,
        xerr=errors,
        fmt="o",
        color="#111111",
        ecolor="#333333",
        elinewidth=1.0,
        markersize=5,
        capsize=3,
        markerfacecolor="white",
        markeredgewidth=1.1,
    )
    ax.axvline(spec.get("reference", 0), color="#555555", linestyle=(0, (3, 3)), linewidth=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels([row["label"] for row in ordered], fontproperties=FONT)
    ax.set_xlabel(spec.get("x_label", "估计系数及95%置信区间"), fontproperties=FONT, fontsize=10)
    if "x_limits" in spec:
        ax.set_xlim(*spec["x_limits"])
    _provenance_tag(ax, spec.get("provenance", "estimated"))
    figure.tight_layout(pad=1.1)
    return figure


def _render_mechanism(spec: dict[str, Any]) -> plt.Figure:
    nodes = spec["nodes"]
    node_map = {node["id"]: node for node in nodes}
    if len(node_map) != len(nodes):
        raise ValueError("mechanism node IDs must be unique")
    for edge in spec["edges"]:
        if edge["from"] not in node_map or edge["to"] not in node_map:
            raise ValueError(f"Unknown edge endpoint: {edge}")

    figure, ax = plt.subplots(figsize=(9.0, 4.9))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    for node in nodes:
        x, y = node["x"], node["y"]
        width, height = node.get("width", 0.18), node.get("height", 0.15)
        box = FancyBboxPatch(
            (x - width / 2, y - height / 2),
            width,
            height,
            boxstyle="round,pad=0.012,rounding_size=0.008",
            linewidth=0.9,
            edgecolor="#222222",
            facecolor=node.get("fill", "#FFFFFF"),
        )
        ax.add_patch(box)
        ax.text(x, y, node["label"], ha="center", va="center", fontsize=10.2, fontproperties=FONT, linespacing=1.35)

    for edge in spec["edges"]:
        source = node_map[edge["from"]]
        target = node_map[edge["to"]]
        start = (source["x"], source["y"])
        end = (target["x"], target["y"])
        line_style = (0, (4, 3)) if edge.get("style") == "dashed" else "-"
        arrow = FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=10,
            linewidth=0.9,
            linestyle=line_style,
            color="#333333",
            shrinkA=45,
            shrinkB=45,
            connectionstyle=edge.get("connection", "arc3,rad=0"),
        )
        ax.add_patch(arrow)
        if edge.get("label"):
            mid_x = (start[0] + end[0]) / 2 + edge.get("label_dx", 0)
            mid_y = (start[1] + end[1]) / 2 + edge.get("label_dy", 0.035)
            ax.text(mid_x, mid_y, edge["label"], ha="center", va="center", fontsize=8.5, color="#444444", fontproperties=FONT)

    if spec.get("provenance") in {"demo", "simulated"}:
        ax.text(0.99, 0.02, "研究框架图（非估计结果）", ha="right", va="bottom", fontsize=8, color="#666666", fontproperties=FONT)
    figure.tight_layout(pad=0.8)
    return figure


RENDERERS = {
    "event_study": _render_event_study,
    "coefficient": _render_coefficient,
    "mechanism": _render_mechanism,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    raw = args.spec.read_bytes()
    spec = json.loads(raw.decode("utf-8"))
    kind = spec.get("kind")
    if kind not in RENDERERS:
        raise ValueError(f"Unsupported kind: {kind!r}")
    figure_id = spec.get("id")
    if not figure_id or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in figure_id):
        raise ValueError("spec.id must contain only letters, numbers, underscores, or hyphens")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    figure = RENDERERS[kind](spec)
    outputs: dict[str, str] = {}
    for extension, options in {
        "png": {"dpi": 300},
        "svg": {},
        "pdf": {},
    }.items():
        destination = args.output_dir / f"{figure_id}.{extension}"
        figure.savefig(destination, bbox_inches="tight", facecolor="white", **options)
        outputs[extension] = destination.name
    plt.close(figure)

    metadata = {
        "figure_id": figure_id,
        "kind": kind,
        "provenance": spec.get("provenance", "estimated"),
        "spec_sha256": hashlib.sha256(raw).hexdigest(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "spec": str(args.spec),
        "outputs": outputs,
    }
    metadata_path = args.output_dir / f"{figure_id}.metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False))


if __name__ == "__main__":
    main()

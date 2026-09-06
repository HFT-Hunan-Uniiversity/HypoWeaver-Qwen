from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib.ticker as mtick
import numpy as np


DEFAULT_V2 = Path(
    "output/experiments/ai_scientist_system_capability_v2/"
    "evaluation_v3evaluator_check.json"
)
DEFAULT_V3 = Path("output/experiments/ai_scientist_system_capability_v3/evaluation.json")
DEFAULT_OUTPUT = Path(
    "output/experiments/ai_scientist_system_capability_v3/figures/"
    "system_capability_v2_v3"
)
DEFAULT_FIGUREKIT = Path(__file__).resolve().with_name("figurekit.py")

METRICS = [
    ("cell_completed", "结构化计划完成"),
    ("h0_compilable", "Reviewer / H0 通过"),
    ("topic_fidelity", "冻结词表主题忠实"),
    ("readiness_blocked_correctly", "缺输入时正确阻断"),
    ("diversity_gate_passed", "检索多样性门通过"),
    ("safe_stop", "安全停止"),
]


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def import_figurekit(path: Path):
    resolved = path.resolve(strict=True)
    sys.path.insert(0, str(resolved.parent))
    from figurekit import (  # type: ignore[import-not-found]
        FigureStyle,
        PALETTE,
        apply_publication_style,
        create_subplots,
        figure_size,
        finalize_figure,
    )

    return {
        "FigureStyle": FigureStyle,
        "PALETTE": PALETTE,
        "apply_publication_style": apply_publication_style,
        "create_subplots": create_subplots,
        "figure_size": figure_size,
        "finalize_figure": finalize_figure,
        "source_path": str(resolved),
    }


def metric_arrays(evaluation: dict[str, Any]) -> dict[str, np.ndarray]:
    metrics = evaluation["metrics_wilson_95"]
    rows = [metrics[key] for key, _ in METRICS]
    return {
        "successes": np.asarray([row["successes"] for row in rows], dtype=int),
        "totals": np.asarray([row["total"] for row in rows], dtype=int),
        "estimate": np.asarray([row["rate"] for row in rows], dtype=float),
        "lower": np.asarray([row["lower"] for row in rows], dtype=float),
        "upper": np.asarray([row["upper"] for row in rows], dtype=float),
    }


def validate_arrays(values: dict[str, np.ndarray]) -> None:
    lengths = {array.size for array in values.values()}
    if lengths != {len(METRICS)}:
        raise ValueError("metric arrays are not aligned")
    if np.any(values["lower"] > values["estimate"]) or np.any(
        values["estimate"] > values["upper"]
    ):
        raise ValueError("Wilson intervals do not contain their estimates")
    if np.any(values["totals"] <= 0) or np.any(values["successes"] < 0):
        raise ValueError("invalid metric counts")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v2", type=Path, default=DEFAULT_V2)
    parser.add_argument("--v3", type=Path, default=DEFAULT_V3)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--figurekit", type=Path, default=DEFAULT_FIGUREKIT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    kit = import_figurekit(args.figurekit)
    FigureStyle = kit["FigureStyle"]
    palette = kit["PALETTE"]
    kit["apply_publication_style"](
        FigureStyle(
            font_size=9.2,
            marker_size=5.2,
            font_family=("Microsoft YaHei", "Arial", "DejaVu Sans", "sans-serif"),
        )
    )

    v2 = metric_arrays(load_json(args.v2))
    v3 = metric_arrays(load_json(args.v3))
    validate_arrays(v2)
    validate_arrays(v3)
    if not np.array_equal(v2["totals"], v3["totals"]):
        raise ValueError("v2 and v3 denominators differ")

    fig, axes = kit["create_subplots"](
        figsize=kit["figure_size"](width_mm=178, height_mm=108)
    )
    ax = axes[0]
    y = np.arange(len(METRICS), dtype=float)
    offset = 0.135

    for index in range(len(METRICS)):
        ax.plot(
            [v2["estimate"][index], v3["estimate"][index]],
            [y[index], y[index]],
            color=palette["light"],
            linewidth=1.5,
            zorder=0,
        )

    v2_xerr = np.vstack((v2["estimate"] - v2["lower"], v2["upper"] - v2["estimate"]))
    v3_xerr = np.vstack((v3["estimate"] - v3["lower"], v3["upper"] - v3["estimate"]))
    ax.errorbar(
        v2["estimate"],
        y + offset,
        xerr=v2_xerr,
        fmt="o",
        color=palette["comparison"],
        ecolor=palette["comparison"],
        markerfacecolor="white",
        markeredgewidth=1.2,
        capsize=2.3,
        elinewidth=1.15,
        label="v2（Wilson 95% CI）",
        zorder=2,
    )
    ax.errorbar(
        v3["estimate"],
        y - offset,
        xerr=v3_xerr,
        fmt="s",
        color=palette["key"],
        ecolor=palette["key"],
        markerfacecolor=palette["key"],
        markeredgecolor="white",
        markeredgewidth=0.6,
        capsize=2.3,
        elinewidth=1.15,
        label="v3（Wilson 95% CI）",
        zorder=3,
    )

    for index in range(len(METRICS)):
        equal_points = bool(np.isclose(v2["estimate"][index], v3["estimate"][index]))
        v2_text_offset = (-11, -7) if equal_points else (0, -7)
        v3_text_offset = (11, 6) if equal_points else (0, 6)
        ax.annotate(
            f"{v2['successes'][index]}/{v2['totals'][index]}",
            (v2["estimate"][index], y[index] + offset),
            xytext=v2_text_offset,
            textcoords="offset points",
            ha="right" if equal_points else "center",
            va="top",
            color=palette["comparison"],
            fontsize=7.2,
        )
        ax.annotate(
            f"{v3['successes'][index]}/{v3['totals'][index]}",
            (v3["estimate"][index], y[index] - offset),
            xytext=v3_text_offset,
            textcoords="offset points",
            ha="left" if equal_points else "center",
            va="bottom",
            color=palette["key"],
            fontsize=7.2,
        )
        delta = v3["estimate"][index] - v2["estimate"][index]
        ax.text(
            1.105,
            y[index],
            f"{100 * delta:+.1f} pp",
            ha="center",
            va="center",
            color=palette["positive"] if delta > 0 else palette["neutral"],
            fontweight="bold" if delta > 0 else "normal",
            fontsize=8.0,
        )

    ax.text(
        1.105,
        -0.62,
        "v3−v2",
        ha="center",
        va="center",
        color=palette["text"],
        fontweight="bold",
        fontsize=8.2,
    )
    ax.set_yticks(y, labels=[label for _, label in METRICS])
    ax.invert_yaxis()
    ax.set_ylim(len(METRICS) - 0.35, -0.65)
    ax.set_xlim(0.0, 1.18)
    ax.set_xticks(np.linspace(0, 1, 6))
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(xmax=1.0, decimals=0))
    ax.set_xlabel("系统单元通过率（失败单元保留在 30 的分母中）")
    ax.grid(axis="x", color=palette["light"], linewidth=0.55, alpha=0.75)
    ax.tick_params(axis="y", length=0)
    ax.legend(loc="lower center", bbox_to_anchor=(0.48, 1.01), ncol=2)
    ax.text(
        0.0,
        -0.19,
        "注：点为通过率，横线为 Wilson 95% CI；同一行灰线仅连接 v2 与 v3 点估计。"
        "执行就绪率未绘制：在线协议故意不提供完整数据资产，ready 路径由独立正负对照验证。",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=7.4,
        color=palette["neutral"],
        wrap=True,
    )

    metadata = {
        "Title": "HypoWeaver-Qwen AI Scientist system capability v2-v3 comparison",
        "Description": (
            "Six pre-registered system pass rates with Wilson 95% confidence intervals; "
            "all 30 question-seed cells remain in the denominator."
        ),
        "Software": f"econ-research-figures figurekit: {kit['source_path']}",
    }
    outputs = kit["finalize_figure"](
        fig,
        args.output,
        formats=("png", "pdf", "svg"),
        dpi=300,
        metadata=metadata,
    )
    sidecar = args.output.with_name(f"{args.output.name}_metadata.json")
    sidecar.write_text(
        json.dumps(
            {
                "schema_version": "research-figure-metadata/1.0.0",
                "code_path": str(Path(__file__).resolve()),
                "data_sources": {
                    "v2_evaluation": str(args.v2.resolve()),
                    "v3_evaluation": str(args.v3.resolve()),
                },
                "field_mapping": {
                    "x": "metrics_wilson_95.<metric>.rate",
                    "x_interval": "metrics_wilson_95.<metric>.lower/upper",
                    "y": "six named system metrics",
                    "color_and_marker": "evaluation version",
                    "direct_label": "successes/total",
                },
                "uncertainty": "Wilson 95% confidence interval over all 30 frozen cells",
                "transformations": "rates and intervals are read from the independent evaluator; no re-estimation in the plotting script",
                "omitted_metric": "execution_ready is omitted because the online protocol intentionally has no complete data assets; the deterministic readiness control verifies the ready path",
                "random_seed": None,
                "output_basename": str(args.output.resolve()),
                "outputs": [str(path.resolve()) for path in outputs],
                "figurekit_source": kit["source_path"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"outputs": [str(path) for path in outputs], "metadata": str(sidecar)},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

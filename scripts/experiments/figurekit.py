"""Reusable publication plotting helpers for economics and management research."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np


PALETTE: Mapping[str, str] = {
    "key": "#0072B2",
    "comparison": "#D55E00",
    "positive": "#009E73",
    "caution": "#E69F00",
    "secondary": "#CC79A7",
    "sky": "#56B4E9",
    "neutral": "#6B7280",
    "light": "#D1D5DB",
    "text": "#1F2937",
}

DEFAULT_COLORS = [
    PALETTE["key"],
    PALETTE["comparison"],
    PALETTE["positive"],
    PALETTE["secondary"],
    PALETTE["caution"],
    PALETTE["neutral"],
]

SUPPORTED_FORMATS = {"png", "pdf", "svg", "eps", "jpg", "jpeg", "tif", "tiff"}


@dataclass(frozen=True)
class FigureStyle:
    font_size: float = 9.0
    axes_linewidth: float = 0.8
    line_width: float = 1.6
    marker_size: float = 4.5
    use_tex: bool = False
    font_family: tuple[str, ...] = (
        "Arial",
        "Helvetica",
        "Microsoft YaHei",
        "Noto Sans CJK SC",
        "DejaVu Sans",
        "sans-serif",
    )


def apply_publication_style(style: FigureStyle | None = None) -> FigureStyle:
    """Apply a restrained, vector-safe Matplotlib style and return it."""
    style = style or FigureStyle()
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": list(style.font_family),
            "font.size": style.font_size,
            "axes.labelsize": style.font_size,
            "axes.titlesize": style.font_size,
            "axes.linewidth": style.axes_linewidth,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.edgecolor": PALETTE["text"],
            "axes.labelcolor": PALETTE["text"],
            "xtick.color": PALETTE["text"],
            "ytick.color": PALETTE["text"],
            "xtick.major.width": style.axes_linewidth,
            "ytick.major.width": style.axes_linewidth,
            "lines.linewidth": style.line_width,
            "lines.markersize": style.marker_size,
            "legend.frameon": False,
            "legend.fontsize": max(style.font_size - 1, 6),
            "text.usetex": style.use_tex,
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "savefig.facecolor": "white",
            "figure.facecolor": "white",
        }
    )
    return style


def figure_size(
    width_mm: float = 178,
    height_mm: float | None = None,
    aspect_ratio: float | None = None,
) -> tuple[float, float]:
    """Convert journal dimensions in millimetres to Matplotlib inches."""
    if width_mm <= 0:
        raise ValueError("width_mm must be positive")
    if height_mm is not None and height_mm <= 0:
        raise ValueError("height_mm must be positive")
    if aspect_ratio is not None and aspect_ratio <= 0:
        raise ValueError("aspect_ratio must be positive")
    if height_mm is None:
        height_mm = width_mm * (aspect_ratio if aspect_ratio is not None else 0.62)
    return width_mm / 25.4, height_mm / 25.4


def create_subplots(nrows: int = 1, ncols: int = 1, figsize=None, **kwargs):
    """Create subplots and return a flattened 1-D axes array."""
    if nrows < 1 or ncols < 1:
        raise ValueError("nrows and ncols must be positive")
    fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=figsize, **kwargs)
    return fig, np.atleast_1d(axes).reshape(-1)


def _as_1d(name: str, values: Sequence[float] | np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    if array.size == 0:
        raise ValueError(f"{name} must not be empty")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} contains non-finite values")
    return array


def _aligned(*named_arrays: tuple[str, Sequence[float] | np.ndarray]) -> list[np.ndarray]:
    arrays = [_as_1d(name, values) for name, values in named_arrays]
    if len({array.size for array in arrays}) != 1:
        lengths = ", ".join(f"{name}={array.size}" for (name, _), array in zip(named_arrays, arrays))
        raise ValueError(f"aligned arrays must have equal lengths: {lengths}")
    return arrays


def _intervals(
    estimate: Sequence[float], lower: Sequence[float], upper: Sequence[float]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    estimate_a, lower_a, upper_a = _aligned(
        ("estimate", estimate), ("lower", lower), ("upper", upper)
    )
    if np.any(lower_a > estimate_a) or np.any(estimate_a > upper_a):
        raise ValueError("intervals must satisfy lower <= estimate <= upper")
    return estimate_a, lower_a, upper_a


def make_coefficient_plot(
    ax,
    labels: Sequence[str],
    estimate: Sequence[float],
    lower: Sequence[float],
    upper: Sequence[float],
    *,
    xlabel: str = "Estimate (95% CI)",
    reference: float = 0.0,
    color: str = PALETTE["key"],
):
    """Plot horizontal estimates and confidence intervals."""
    estimate_a, lower_a, upper_a = _intervals(estimate, lower, upper)
    if len(labels) != estimate_a.size:
        raise ValueError("labels must align with estimates")
    y = np.arange(estimate_a.size)
    xerr = np.vstack((estimate_a - lower_a, upper_a - estimate_a))
    ax.axvline(reference, color=PALETTE["neutral"], linewidth=0.9, linestyle="--", zorder=0)
    ax.errorbar(
        estimate_a,
        y,
        xerr=xerr,
        fmt="o",
        color=color,
        ecolor=color,
        capsize=2.5,
        elinewidth=1.2,
        markeredgecolor="white",
        markeredgewidth=0.6,
        zorder=2,
    )
    ax.set_yticks(y, labels=list(labels))
    ax.invert_yaxis()
    ax.set_xlabel(xlabel)
    ax.grid(axis="x", color=PALETTE["light"], linewidth=0.5, alpha=0.6)
    return ax


def make_event_study(
    ax,
    event_time: Sequence[float],
    estimate: Sequence[float],
    lower: Sequence[float],
    upper: Sequence[float],
    *,
    xlabel: str = "Periods relative to treatment",
    ylabel: str = "Estimate (95% CI)",
    reference: float = 0.0,
    treatment_time: float = 0.0,
    color: str = PALETTE["key"],
):
    """Plot dynamic estimates with interval bars and treatment/reference lines."""
    event_a, estimate_a = _aligned(("event_time", event_time), ("estimate", estimate))
    estimate_a, lower_a, upper_a = _intervals(estimate_a, lower, upper)
    order = np.argsort(event_a)
    event_a, estimate_a, lower_a, upper_a = (
        event_a[order], estimate_a[order], lower_a[order], upper_a[order]
    )
    yerr = np.vstack((estimate_a - lower_a, upper_a - estimate_a))
    ax.axhline(reference, color=PALETTE["neutral"], linewidth=0.9, linestyle="--", zorder=0)
    ax.axvline(treatment_time - 0.5, color=PALETTE["neutral"], linewidth=0.8, linestyle=":", zorder=0)
    ax.errorbar(
        event_a,
        estimate_a,
        yerr=yerr,
        fmt="o-",
        color=color,
        ecolor=color,
        capsize=2.5,
        elinewidth=1.1,
        markeredgecolor="white",
        markeredgewidth=0.5,
    )
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_xticks(event_a)
    ax.grid(axis="y", color=PALETTE["light"], linewidth=0.5, alpha=0.6)
    return ax


def make_trend(
    ax,
    x: Sequence[float],
    series: Sequence[Sequence[float]],
    labels: Sequence[str],
    *,
    lower: Sequence[Sequence[float]] | None = None,
    upper: Sequence[Sequence[float]] | None = None,
    xlabel: str | None = None,
    ylabel: str | None = None,
    colors: Sequence[str] | None = None,
    show_markers: bool = False,
):
    """Plot aligned trends with optional uncertainty bands."""
    x_a = _as_1d("x", x)
    if len(series) != len(labels):
        raise ValueError("series and labels must have equal lengths")
    if (lower is None) != (upper is None):
        raise ValueError("lower and upper must be provided together")
    if lower is not None and (len(lower) != len(series) or len(upper) != len(series)):
        raise ValueError("uncertainty bands must align with series")
    colors = list(colors or DEFAULT_COLORS)
    for index, (values, label) in enumerate(zip(series, labels)):
        y_a = _as_1d(f"series[{index}]", values)
        if y_a.size != x_a.size:
            raise ValueError(f"series[{index}] must align with x")
        color = colors[index % len(colors)]
        marker = "o" if show_markers else None
        ax.plot(x_a, y_a, label=label, color=color, marker=marker)
        if lower is not None and upper is not None:
            y_check, lo_a, hi_a = _intervals(y_a, lower[index], upper[index])
            ax.fill_between(x_a, lo_a, hi_a, color=color, alpha=0.14, linewidth=0)
    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)
    ax.legend()
    ax.grid(axis="y", color=PALETTE["light"], linewidth=0.5, alpha=0.6)
    return ax


def make_grouped_bar(
    ax,
    categories: Sequence[str],
    series: Sequence[Sequence[float]],
    labels: Sequence[str],
    *,
    ylabel: str = "Value",
    colors: Sequence[str] | None = None,
    annotate: bool = False,
    start_at_zero: bool = True,
):
    """Plot aligned grouped bars with a zero baseline by default."""
    if not categories:
        raise ValueError("categories must not be empty")
    if len(series) != len(labels) or not series:
        raise ValueError("series and labels must be non-empty and aligned")
    arrays = [_as_1d(f"series[{i}]", values) for i, values in enumerate(series)]
    if any(values.size != len(categories) for values in arrays):
        raise ValueError("every series must align with categories")
    colors = list(colors or DEFAULT_COLORS)
    x = np.arange(len(categories), dtype=float)
    width = min(0.8 / len(arrays), 0.28)
    offset_center = (len(arrays) - 1) / 2
    for index, (values, label) in enumerate(zip(arrays, labels)):
        positions = x + (index - offset_center) * width
        bars = ax.bar(
            positions,
            values,
            width=width,
            label=label,
            color=colors[index % len(colors)],
            edgecolor="white",
            linewidth=0.6,
        )
        if annotate:
            ax.bar_label(bars, fmt="%.2g", padding=2, fontsize=max(mpl.rcParams["font.size"] - 2, 6))
    ax.set_xticks(x, labels=list(categories))
    ax.set_ylabel(ylabel)
    ax.legend()
    ax.grid(axis="y", color=PALETTE["light"], linewidth=0.5, alpha=0.6)
    if start_at_zero:
        values_all = np.concatenate(arrays)
        if np.min(values_all) >= 0:
            ax.set_ylim(bottom=0)
        elif np.max(values_all) <= 0:
            ax.set_ylim(top=0)
    return ax


def make_heatmap(
    ax,
    matrix: Sequence[Sequence[float]],
    *,
    x_labels: Sequence[str] | None = None,
    y_labels: Sequence[str] | None = None,
    cmap: str = "viridis",
    cbar_label: str | None = None,
    annotate: bool = False,
    value_format: str = ".2f",
    vmin: float | None = None,
    vmax: float | None = None,
    center: float | None = None,
):
    """Render a numeric matrix with optional labels and cell values."""
    matrix_a = np.asarray(matrix, dtype=float)
    if matrix_a.ndim != 2 or matrix_a.size == 0:
        raise ValueError("matrix must be a non-empty two-dimensional array")
    if not np.all(np.isfinite(matrix_a)):
        raise ValueError("matrix contains non-finite values")
    rows, cols = matrix_a.shape
    if x_labels is not None and len(x_labels) != cols:
        raise ValueError("x_labels must align with matrix columns")
    if y_labels is not None and len(y_labels) != rows:
        raise ValueError("y_labels must align with matrix rows")
    if center is not None:
        data_min = float(np.min(matrix_a)) if vmin is None else float(vmin)
        data_max = float(np.max(matrix_a)) if vmax is None else float(vmax)
        if not data_min < center < data_max:
            raise ValueError("center must lie strictly between vmin and vmax")
        norm = mpl.colors.TwoSlopeNorm(vmin=data_min, vcenter=float(center), vmax=data_max)
        image = ax.imshow(matrix_a, cmap=cmap, norm=norm, aspect="auto")
    else:
        image = ax.imshow(matrix_a, cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto")
    if x_labels is not None:
        ax.set_xticks(np.arange(cols), labels=list(x_labels), rotation=35, ha="right")
    if y_labels is not None:
        ax.set_yticks(np.arange(rows), labels=list(y_labels))
    colorbar = ax.figure.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    if cbar_label:
        colorbar.set_label(cbar_label)
    if annotate:
        for row in range(rows):
            for col in range(cols):
                rgba = image.cmap(image.norm(matrix_a[row, col]))
                luminance = 0.2126 * rgba[0] + 0.7152 * rgba[1] + 0.0722 * rgba[2]
                text_color = "white" if luminance < 0.5 else PALETTE["text"]
                ax.text(col, row, format(matrix_a[row, col], value_format), ha="center", va="center", color=text_color, fontsize=max(mpl.rcParams["font.size"] - 2, 6))
    return image


def add_panel_labels(
    axes: Iterable,
    labels: Sequence[str] | None = None,
    *,
    x: float = -0.12,
    y: float = 1.06,
    fontsize: float | None = None,
):
    """Add bold A/B/C panel labels in axes coordinates."""
    axes_list = list(axes)
    labels = list(labels or [chr(ord("A") + index) for index in range(len(axes_list))])
    if len(labels) != len(axes_list):
        raise ValueError("panel labels must align with axes")
    for ax, label in zip(axes_list, labels):
        ax.text(
            x,
            y,
            label,
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontweight="bold",
            fontsize=fontsize or mpl.rcParams["font.size"] + 1,
        )


def finalize_figure(
    fig,
    out_path: str | Path,
    *,
    formats: Sequence[str] = ("png", "pdf", "svg"),
    dpi: int = 300,
    close: bool = True,
    pad: float = 0.04,
    metadata: Mapping[str, str] | None = None,
) -> list[Path]:
    """Save a figure to one or more validated formats."""
    if dpi <= 0:
        raise ValueError("dpi must be positive")
    path = Path(out_path)
    if path.suffix:
        inferred = path.suffix.lstrip(".").lower()
        if formats == ("png", "pdf", "svg"):
            formats = (inferred,)
        path = path.with_suffix("")
    normalized = [str(fmt).lower().lstrip(".") for fmt in formats]
    unsupported = sorted(set(normalized) - SUPPORTED_FORMATS)
    if unsupported:
        raise ValueError(f"unsupported formats: {unsupported}")
    if not normalized:
        raise ValueError("formats must not be empty")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(pad=0.8)
    saved: list[Path] = []
    for fmt in normalized:
        destination = path.with_suffix(f".{fmt}")
        raw_metadata = dict(metadata or {})
        if fmt == "pdf":
            save_metadata = {
                "Title": raw_metadata.get("Title", path.name),
                "Subject": raw_metadata.get("Description", ""),
                "Creator": raw_metadata.get("Software", "econ-research-figures"),
            }
        elif fmt == "svg":
            save_metadata = {
                "Title": raw_metadata.get("Title", path.name),
                "Description": raw_metadata.get("Description", ""),
                "Creator": raw_metadata.get("Software", "econ-research-figures"),
            }
        elif fmt == "png":
            save_metadata = raw_metadata
        else:
            save_metadata = None
        fig.savefig(
            destination,
            format=fmt,
            dpi=dpi,
            bbox_inches="tight",
            pad_inches=pad,
            metadata=save_metadata,
        )
        saved.append(destination)
    if close:
        plt.close(fig)
    return saved

from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

from ..seal import canonical_sha256
from .recipe_contracts import recipe_data_snapshot, validate_recipe_data
from .renderer import (
    DEFAULT_FIGURE_ROOT,
    MIME_TYPES,
    _file_sha256,
    _mechanism_positions,
    _neutral_metadata,
    _plot_dependencies,
    _rendering_fingerprint,
    _safe_component,
    _save_all,
    render_request as render_builtin_request,
)


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SKILL_SCRIPT = (
    PROJECT_ROOT
    / "skills"
    / "chinese-econ-journal-figures"
    / "scripts"
    / "render_econ_figure.py"
)
ADAPTER_VERSION = "skill-adapter-1.4"
SUPPORTED_RECIPES = frozenset(
    {
        "coefficient_forest",
        "event_study",
        "heterogeneity_forest",
        "specification_curve",
        "mechanism_evidence_graph",
    }
)
_LOAD_LOCK = threading.Lock()
_RENDER_LOCK = threading.Lock()
_MODULE_CACHE: dict[tuple[str, int], ModuleType] = {}


def skill_script_path() -> Path:
    configured = os.getenv("HYPOWEAVER_ECON_FIGURE_SKILL_PATH")
    return Path(configured).expanduser().resolve() if configured else DEFAULT_SKILL_SCRIPT


def render_request_with_skill(
    request: dict[str, Any],
    *,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    """Render journal-style recipes with the project skill and preserve the API contract."""

    recipe_id = str(request["recipe_id"])
    if recipe_id not in SUPPORTED_RECIPES:
        return render_builtin_request(request, artifact_root=artifact_root)

    data = validate_recipe_data(recipe_id, request["bindings"]["data"])
    if hasattr(data, "model_dump"):
        data = data.model_dump(mode="json")
    data_snapshot = recipe_data_snapshot(recipe_id, data)
    stage = str(request["stage"])
    request_id = str(request["request_id"])
    workflow_run_id = str(request["source"]["artifact_id"]).removesuffix(
        ":research_run"
    )
    output_root = (artifact_root or DEFAULT_FIGURE_ROOT).resolve()
    script_path = skill_script_path()
    if not script_path.is_file():
        raise RuntimeError(
            "中文经管期刊图表 Skill 不可用："
            f"未找到 {script_path}。可通过 HYPOWEAVER_ECON_FIGURE_SKILL_PATH 指定。"
        )

    rendering_fingerprint = {
        **_rendering_fingerprint(),
        "adapter_version": ADAPTER_VERSION,
        "adapter_code_sha256": _file_sha256(Path(__file__).resolve()),
        "skill_script_sha256": _file_sha256(script_path),
    }
    figure_id = "figure-" + canonical_sha256(
        {
            "request": request,
            "rendering_fingerprint": rendering_fingerprint,
        }
    )[:24]
    output_dir = (
        output_root / _safe_component(workflow_run_id) / _safe_component(stage)
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    provenance = str(request["provenance"])
    skill_spec = _skill_spec(recipe_id, data, figure_id, provenance)
    spec_bytes = (
        json.dumps(
            skill_spec,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    spec_sha256 = _write_immutable(
        output_dir / f"{figure_id}.spec.json",
        spec_bytes,
    )

    module = _load_skill_module(script_path)
    renderer = getattr(module, "RENDERERS", {}).get(skill_spec["kind"])
    if renderer is None:
        raise RuntimeError(
            f"中文经管期刊图表 Skill 不支持 {skill_spec['kind']!r}。"
        )
    _, _, pd, plt, _ = _plot_dependencies()
    source_frame = _source_frame(pd, recipe_id, data)
    with _RENDER_LOCK:
        figure = renderer(skill_spec)
        try:
            result = _save_all(
                figure,
                source_frame,
                output_dir,
                figure_id,
            )
        finally:
            plt.close(figure)

    metadata = {
        "figure_id": figure_id,
        "recipe_id": recipe_id,
        "skill_kind": skill_spec["kind"],
        "provenance": provenance,
        "spec_sha256": spec_sha256,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "outputs": {
            file_format: info["path"].name
            for file_format, info in result.items()
        },
        "renderer": {
            "name": "chinese-econ-journal-figures",
            "adapter_version": ADAPTER_VERSION,
            "skill_script_sha256": rendering_fingerprint["skill_script_sha256"],
        },
    }
    metadata_path = output_dir / f"{figure_id}.metadata.json"
    if metadata_path.is_file():
        existing = json.loads(metadata_path.read_text(encoding="utf-8"))
        if existing.get("spec_sha256") != spec_sha256:
            raise RuntimeError("immutable figure metadata collision")
    else:
        _write_immutable(
            metadata_path,
            (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode(
                "utf-8"
            ),
        )
    metadata_sha256 = _file_sha256(metadata_path)

    files = [
        {
            "format": file_format,
            "mime_type": MIME_TYPES[file_format],
            "artifact_uri": (
                "artifact://figures/"
                f"{_safe_component(workflow_run_id)}/{_safe_component(stage)}/"
                f"{info['path'].name}"
            ),
            "sha256": info["sha256"],
        }
        for file_format, info in result.items()
        if file_format in request["formats"]
    ]
    title, caption, alt_text = _neutral_metadata(recipe_id, stage, data)
    identity = {
        "request_id": request_id,
        "figure_id": figure_id,
        "files": [file["sha256"] for file in files],
    }
    return {
        "schema_version": request["schema_version"],
        "bundle_id": f"figure-bundle-{canonical_sha256(identity)[:24]}",
        "stage": stage,
        "status": "succeeded",
        "figures": [
            {
                "figure_id": figure_id,
                "recipe_id": recipe_id,
                "recipe_version": request["recipe_version"],
                "provenance": provenance,
                "title": title,
                "caption": caption,
                "alt_text": alt_text,
                "execution_ids": request["execution_ids"],
                "claim_ids": request["claim_ids"],
                "sources": [request["source"], *request.get("data_sources", [])],
                "files": files,
                "data_snapshot": data_snapshot,
                "warnings": [],
            }
        ],
        "renderer": {
            "name": "chinese-econ-journal-figures",
            "version": ADAPTER_VERSION,
            "backend": "matplotlib",
            "provenance": provenance,
            "skill_kind": skill_spec["kind"],
            "skill_script": "skills/chinese-econ-journal-figures/scripts/render_econ_figure.py",
            "skill_script_sha256": rendering_fingerprint["skill_script_sha256"],
            "spec_sha256": spec_sha256,
            "metadata_sha256": metadata_sha256,
        },
        "warnings": [],
    }


def _load_skill_module(path: Path) -> ModuleType:
    key = (str(path), path.stat().st_mtime_ns)
    with _LOAD_LOCK:
        cached = _MODULE_CACHE.get(key)
        if cached is not None:
            return cached
        spec = importlib.util.spec_from_file_location(
            "hypoweaver_chinese_econ_journal_figures",
            path,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("无法加载中文经管期刊图表 Skill。")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _MODULE_CACHE.clear()
        _MODULE_CACHE[key] = module
        return module


def _skill_spec(
    recipe_id: str,
    data: list[dict[str, Any]] | dict[str, Any],
    figure_id: str,
    provenance: str,
) -> dict[str, Any]:
    if recipe_id == "event_study":
        assert isinstance(data, dict)
        points = sorted(
            data["points"],
            key=lambda item: (item["relative_time"], item["execution_id"]),
        )
        return {
                "id": figure_id,
                "kind": "event_study",
                "provenance": provenance,
                "x": [item["relative_time"] for item in points],
                "x_labels": [
                    _period_label(item["relative_time"]) for item in points
                ],
                "estimate": [item["coefficient"] for item in points],
                "lower": [item["ci_lower"] for item in points],
                "upper": [item["ci_upper"] for item in points],
                "policy_time": 0,
                "reference_period": data.get("reference_period"),
                "x_label": "相对政策时点",
                "y_label": "估计系数及95%置信区间",
            }

    if recipe_id in {
        "coefficient_forest",
        "heterogeneity_forest",
        "specification_curve",
    }:
        rows = _coefficient_rows(recipe_id, data)
        return {
                "id": figure_id,
                "kind": "coefficient",
                "provenance": provenance,
                "reference": 0,
                "x_label": "估计系数及95%置信区间",
                "rows": rows,
            }

    assert recipe_id == "mechanism_evidence_graph"
    assert isinstance(data, dict)
    nodes = sorted(data["nodes"], key=lambda item: item["node_id"])
    edges = sorted(data["edges"], key=lambda item: item["edge_id"])
    has_declared_positions = all(
        item.get("x") is not None and item.get("y") is not None for item in nodes
    )
    positions = (
        {
            item["node_id"]: (float(item["x"]), float(item["y"]))
            for item in nodes
        }
        if has_declared_positions
        else {
            node_id: (x * 0.76 + 0.12, y * 0.72 + 0.14)
            for node_id, (x, y) in _mechanism_positions(nodes, edges).items()
        }
    )
    return {
            "id": figure_id,
            "kind": "mechanism",
            "provenance": provenance,
            "nodes": [
                {
                    "id": item["node_id"],
                    "label": item.get("label"),
                    "x": positions[item["node_id"]][0],
                    "y": positions[item["node_id"]][1],
                    "width": item.get("width") or 0.2,
                    "height": item.get("height") or 0.14,
                    **({"fill": item["fill"]} if item.get("fill") else {}),
                }
                for item in nodes
            ],
            "edges": [
                {
                    "from": item["source"],
                    "to": item["target"],
                    "label": item["label"],
                    "style": item.get("style", "dashed"),
                    "connection": f"arc3,rad={float(item.get('curvature', 0)):g}",
                    "label_dx": item.get("label_dx", 0),
                    "label_dy": item.get("label_dy", 0.035),
                }
                for item in edges
            ],
        }


def _coefficient_rows(
    recipe_id: str,
    data: list[dict[str, Any]] | dict[str, Any],
) -> list[dict[str, Any]]:
    if recipe_id == "specification_curve":
        assert isinstance(data, dict)
        # The workflow builder has already frozen a deterministic order with
        # the baseline first. Preserve that order for paper readability.
        records = list(data["points"])
        labels = [item["specification"] for item in records]
    else:
        assert isinstance(data, list)
        records = sorted(
            data,
            key=(
                (lambda item: (
                    item["subgroup_variable"],
                    item["subgroup"],
                    item["execution_id"],
                ))
                if recipe_id == "heterogeneity_forest"
                else (lambda item: (
                    item["term"],
                    item["execution_id"],
                    item["coefficient"],
                ))
            ),
        )
        if recipe_id == "heterogeneity_forest":
            labels = [
                f"{item['subgroup_variable']}：{item['subgroup']}" for item in records
            ]
        else:
            term_counts = {
                item["term"]: sum(other["term"] == item["term"] for other in records)
                for item in records
            }
            labels = [
                (
                    f"{item['term']} · {item['execution_id']}"
                    if term_counts[item["term"]] > 1
                    else item["term"]
                )
                for item in records
            ]
    return [
        {
            "label": label,
            "estimate": item["coefficient"],
            "lower": item["ci_lower"],
            "upper": item["ci_upper"],
        }
        for label, item in zip(labels, records, strict=True)
    ]


def _period_label(value: Any) -> str:
    number = float(value)
    if number.is_integer():
        integer = int(number)
        return f"+{integer}" if integer > 0 else str(integer)
    return f"{number:g}"


def _source_frame(
    pd: Any,
    recipe_id: str,
    data: list[dict[str, Any]] | dict[str, Any],
) -> Any:
    if isinstance(data, list):
        return pd.DataFrame(data)
    if recipe_id in {"event_study", "specification_curve"}:
        rows = data["points"]
        frame = pd.DataFrame(rows)
        for key, value in data.items():
            if key != "points":
                frame[key] = value
        return frame
    if recipe_id == "mechanism_evidence_graph":
        return pd.DataFrame(
            [
                {
                    "record_type": "node",
                    "id": item["node_id"],
                    "source": None,
                    "target": None,
                    "kind": None,
                    "label": item["label"],
                }
                for item in data["nodes"]
            ]
            + [
                {
                    "record_type": "edge",
                    "id": item["edge_id"],
                    "source": item["source"],
                    "target": item["target"],
                    "kind": item["edge_kind"],
                    "label": item["label"],
                }
                for item in data["edges"]
            ]
        )
    return pd.DataFrame([data])


def _write_immutable(path: Path, payload: bytes) -> str:
    digest = hashlib.sha256(payload).hexdigest()
    if path.is_file():
        if path.read_bytes() != payload:
            raise RuntimeError(f"immutable figure artifact collision for {path.name}")
    else:
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_bytes(payload)
        try:
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
    return digest

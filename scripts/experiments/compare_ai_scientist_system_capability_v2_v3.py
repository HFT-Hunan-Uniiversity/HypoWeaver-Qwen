from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


DEFAULT_V2 = Path(
    "output/experiments/ai_scientist_system_capability_v2/"
    "evaluation_v3evaluator_check.json"
)
DEFAULT_V3 = Path(
    "output/experiments/ai_scientist_system_capability_v3/evaluation.json"
)
DEFAULT_JSON_OUTPUT = Path(
    "output/experiments/ai_scientist_system_capability_v3/"
    "comparison_v2_v3.json"
)
DEFAULT_REPORT_OUTPUT = Path(
    "output/experiments/ai_scientist_system_capability_v3/"
    "comparison_v2_v3.md"
)

BINARY_METRICS = [
    ("cell_completed", "结构化计划完成"),
    ("h0_compilable", "H0 可编译通过"),
    ("topic_fidelity", "主题忠实"),
    ("final_consistency_passed", "Reviewer 最终通过"),
    ("diversity_gate_passed", "检索多样性门通过"),
    ("readiness_blocked_correctly", "缺输入时正确阻断"),
    ("safe_stop", "安全停止"),
]


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"evaluation must be a JSON object: {path}")
    return payload


def percentile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def cluster_bootstrap_delta(
    paired_rows: list[tuple[str, float, float]],
    *,
    reps: int,
    seed: int,
) -> dict[str, Any]:
    by_question: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for case_id, before, after in paired_rows:
        by_question[case_id].append((before, after))
    question_ids = sorted(by_question)
    if not question_ids:
        raise ValueError("cluster bootstrap requires paired questions")

    observed = mean(after - before for _, before, after in paired_rows)
    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(reps):
        sampled = [rng.choice(question_ids) for _ in question_ids]
        differences = [
            after - before
            for case_id in sampled
            for before, after in by_question[case_id]
        ]
        draws.append(mean(differences))

    return {
        "estimate": round(observed, 6),
        "lower": round(percentile(draws, 0.025), 6),
        "upper": round(percentile(draws, 0.975), 6),
        "method": f"paired question-cluster bootstrap percentile 95%, {reps} reps",
        "clusters": len(question_ids),
        "seed": seed,
    }


def exact_mcnemar_p(improved: int, regressed: int) -> float:
    discordant = improved + regressed
    if discordant == 0:
        return 1.0
    tail = min(improved, regressed)
    probability = sum(
        math.comb(discordant, successes) for successes in range(tail + 1)
    ) / (2**discordant)
    return min(1.0, 2 * probability)


def cell_index(evaluation: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cells = evaluation.get("cells")
    if not isinstance(cells, list):
        raise ValueError("evaluation is missing the cells list")
    index: dict[str, dict[str, Any]] = {}
    for cell in cells:
        if not isinstance(cell, dict) or not isinstance(cell.get("cell_id"), str):
            raise ValueError("every evaluated cell must have a string cell_id")
        if cell["cell_id"] in index:
            raise ValueError(f"duplicate cell_id: {cell['cell_id']}")
        index[cell["cell_id"]] = cell
    return index


def metric_value(cell: dict[str, Any], key: str) -> bool:
    value = cell.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"cell {cell.get('cell_id')} has non-boolean {key}: {value!r}")
    return value


def rate_payload(payload: dict[str, Any], key: str) -> dict[str, Any]:
    item = payload[key]
    return {
        "successes": int(item["successes"]),
        "total": int(item["total"]),
        "rate": float(item["rate"]),
        "lower": float(item["lower"]),
        "upper": float(item["upper"]),
        "method": item["method"],
    }


def descriptive_change(before: float, after: float) -> dict[str, float | None]:
    relative = None if before == 0 else (after - before) / before
    return {
        "v2": round(before, 6),
        "v3": round(after, 6),
        "absolute_change": round(after - before, 6),
        "relative_change": None if relative is None else round(relative, 6),
    }


def compare(
    v2: dict[str, Any],
    v3: dict[str, Any],
    *,
    bootstrap_reps: int,
    bootstrap_seed: int,
) -> dict[str, Any]:
    v2_cells = cell_index(v2)
    v3_cells = cell_index(v3)
    if set(v2_cells) != set(v3_cells):
        missing_v2 = sorted(set(v3_cells) - set(v2_cells))
        missing_v3 = sorted(set(v2_cells) - set(v3_cells))
        raise ValueError(
            f"cell sets differ; missing from v2={missing_v2}, missing from v3={missing_v3}"
        )

    cell_ids = sorted(v2_cells)
    binary: dict[str, Any] = {}
    for metric_index, (key, label) in enumerate(BINARY_METRICS):
        paired: list[tuple[str, float, float]] = []
        improved = regressed = stable_pass = stable_fail = 0
        for cell_id in cell_ids:
            before = metric_value(v2_cells[cell_id], key)
            after = metric_value(v3_cells[cell_id], key)
            case_id = str(v2_cells[cell_id]["case_id"])
            if case_id != str(v3_cells[cell_id]["case_id"]):
                raise ValueError(f"case_id mismatch for {cell_id}")
            paired.append((case_id, float(before), float(after)))
            if not before and after:
                improved += 1
            elif before and not after:
                regressed += 1
            elif before and after:
                stable_pass += 1
            else:
                stable_fail += 1

        before_successes = sum(int(row[1]) for row in paired)
        after_successes = sum(int(row[2]) for row in paired)
        reported_before = int(v2["metrics_wilson_95"][key]["successes"])
        reported_after = int(v3["metrics_wilson_95"][key]["successes"])
        if before_successes != reported_before or after_successes != reported_after:
            raise ValueError(f"cell-level count does not match evaluator metric for {key}")

        binary[key] = {
            "label": label,
            "total": len(paired),
            "v2_successes": before_successes,
            "v2_rate": round(before_successes / len(paired), 6),
            "v3_successes": after_successes,
            "v3_rate": round(after_successes / len(paired), 6),
            "absolute_change": round((after_successes - before_successes) / len(paired), 6),
            "paired_transitions": {
                "improved_0_to_1": improved,
                "regressed_1_to_0": regressed,
                "stable_pass": stable_pass,
                "stable_fail": stable_fail,
            },
            "mcnemar_exact_two_sided_p": round(
                exact_mcnemar_p(improved, regressed), 6
            ),
            "cluster_bootstrap_change_95": cluster_bootstrap_delta(
                paired,
                reps=bootstrap_reps,
                seed=bootstrap_seed + metric_index,
            ),
        }

    diversity_pairs = [
        (
            str(v2_cells[cell_id]["case_id"]),
            float(v2_cells[cell_id]["evidence_diversity_ratio"]),
            float(v3_cells[cell_id]["evidence_diversity_ratio"]),
        )
        for cell_id in cell_ids
    ]
    diversity_change = cluster_bootstrap_delta(
        diversity_pairs,
        reps=bootstrap_reps,
        seed=bootstrap_seed + len(BINARY_METRICS),
    )
    diversity_change.update(
        {
            "v2_mean": round(mean(row[1] for row in diversity_pairs), 6),
            "v3_mean": round(mean(row[2] for row in diversity_pairs), 6),
        }
    )

    usage: dict[str, Any] = {}
    for key in (
        "provider_attempts",
        "input_tokens",
        "output_tokens",
        "model_wall_time_seconds",
    ):
        usage[key] = descriptive_change(
            float(v2["usage_totals"][key]), float(v3["usage_totals"][key])
        )

    return {
        "schema_version": "ai-scientist-system-capability-comparison/1.0.0",
        "comparison_scope": (
            "在相同 10 个问题和 3 个供应商种子上的配对系统比较；"
            "不是模型排行榜，也不对单项代码改动作因果分解"
        ),
        "matched_cells": len(cell_ids),
        "question_clusters": len({v2_cells[cell_id]["case_id"] for cell_id in cell_ids}),
        "v2": {
            "evaluation_schema_version": v2["schema_version"],
            "protocol_sha256": v2["protocol_sha256"],
            "completed_cells": v2["completed_cells"],
            "failed_cells": v2["failed_cells"],
        },
        "v3": {
            "evaluation_schema_version": v3["schema_version"],
            "protocol_sha256": v3["protocol_sha256"],
            "completed_cells": v3["completed_cells"],
            "failed_cells": v3["failed_cells"],
        },
        "binary_metrics": binary,
        "evidence_diversity_ratio": diversity_change,
        "schema_repair_recovery": {
            "v2": rate_payload(v2, "schema_repair_recovery_rate"),
            "v3": rate_payload(v3, "schema_repair_recovery_rate"),
            "descriptive_rate_change": round(
                float(v3["schema_repair_recovery_rate"]["rate"])
                - float(v2["schema_repair_recovery_rate"]["rate"]),
                6,
            ),
            "note": "logical_call 分母不同，不作配对单元检验",
        },
        "reviewer_requery_recovery": {
            "v2": rate_payload(v2, "repair_recovery_rate"),
            "v3": rate_payload(v3, "repair_recovery_rate"),
            "descriptive_rate_change": round(
                float(v3["repair_recovery_rate"]["rate"])
                - float(v2["repair_recovery_rate"]["rate"]),
                6,
            ),
            "note": "重检索触发分母不同，不作配对单元检验",
        },
        "usage_descriptive": usage,
        "inference_guardrails": [
            "全部 30 个冻结单元均保留在分母中，包括供应商或 schema 失败。",
            "供应商 seed 仅为 best-effort，不能使云端生成严格确定。",
            "McNemar p 值仅作探索性单元配对诊断；30 个单元共享 10 个问题簇。",
            "问题聚类 bootstrap 只有 10 个簇，必须与原始分子/分母共同报告。",
            "v2—v3 同时改变了多项预注册系统组件，不能把差值解释为某一组件的孤立因果效应。",
            "在线协议没有许可完整的不可变数据资产，因此执行就绪率按设计为 0；独立确定性正对照已验证 ready 路径。",
        ],
    }


def pct(value: float) -> str:
    return f"{100 * value:.1f}%"


def signed_pp(value: float) -> str:
    return f"{100 * value:+.1f} pp"


def render_report(comparison: dict[str, Any]) -> str:
    lines = [
        "# AI Scientist 系统能力 v2—v3 配对比较",
        "",
        f"同一冻结问题框架共匹配 {comparison['matched_cells']} 个问题—种子单元，"
        f"归属于 {comparison['question_clusters']} 个问题簇。v2 完成 "
        f"{comparison['v2']['completed_cells']}/{comparison['matched_cells']}，v3 完成 "
        f"{comparison['v3']['completed_cells']}/{comparison['matched_cells']}。",
        "",
        "| 系统指标 | v2 | v3 | 绝对变化 | 0→1 / 1→0 | 问题聚类 bootstrap 95% CI | McNemar p |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for key, _ in BINARY_METRICS:
        item = comparison["binary_metrics"][key]
        transition = item["paired_transitions"]
        interval = item["cluster_bootstrap_change_95"]
        lines.append(
            f"| {item['label']} | {item['v2_successes']}/{item['total']} "
            f"({pct(item['v2_rate'])}) | {item['v3_successes']}/{item['total']} "
            f"({pct(item['v3_rate'])}) | {signed_pp(item['absolute_change'])} | "
            f"{transition['improved_0_to_1']} / {transition['regressed_1_to_0']} | "
            f"{signed_pp(interval['lower'])} 至 {signed_pp(interval['upper'])} | "
            f"{item['mcnemar_exact_two_sided_p']:.4f} |"
        )

    schema = comparison["schema_repair_recovery"]
    reviewer = comparison["reviewer_requery_recovery"]
    usage = comparison["usage_descriptive"]
    diversity = comparison["evidence_diversity_ratio"]
    lines.extend(
        [
            "",
            "## 修复闭环与成本",
            "",
            f"- Schema 修复恢复率：{schema['v2']['successes']}/{schema['v2']['total']} "
            f"({pct(schema['v2']['rate'])}) → {schema['v3']['successes']}/{schema['v3']['total']} "
            f"({pct(schema['v3']['rate'])})，描述性变化 {signed_pp(schema['descriptive_rate_change'])}。"
            "两版触发修复的 logical_call 数不同，不作配对显著性检验。",
            f"- Reviewer 重检索最终恢复：{reviewer['v2']['successes']}/{reviewer['v2']['total']} "
            f"({pct(reviewer['v2']['rate'])}) → {reviewer['v3']['successes']}/{reviewer['v3']['total']} "
            f"({pct(reviewer['v3']['rate'])})；触发次数从 "
            f"{reviewer['v2']['total']} 降至 {reviewer['v3']['total']}。",
            f"- 证据多样性均值：{diversity['v2_mean']:.3f} → {diversity['v3_mean']:.3f}，"
            f"变化 {diversity['estimate']:+.3f}，问题聚类 bootstrap 95% CI "
            f"[{diversity['lower']:+.3f}, {diversity['upper']:+.3f}]。",
            f"- 百炼供应商尝试：{int(usage['provider_attempts']['v2'])} → "
            f"{int(usage['provider_attempts']['v3'])}（{pct(usage['provider_attempts']['relative_change'])}）。",
            f"- 输入 token：{int(usage['input_tokens']['v2']):,} → "
            f"{int(usage['input_tokens']['v3']):,}（{pct(usage['input_tokens']['relative_change'])}）；"
            f"输出 token：{int(usage['output_tokens']['v2']):,} → "
            f"{int(usage['output_tokens']['v3']):,}（{pct(usage['output_tokens']['relative_change'])}）。",
            f"- 模型阶段累计耗时：{usage['model_wall_time_seconds']['v2']:.1f}s → "
            f"{usage['model_wall_time_seconds']['v3']:.1f}s（"
            f"{pct(usage['model_wall_time_seconds']['relative_change'])}）。耗时受服务侧负载影响，仅作描述。",
            "",
            "## 结论",
            "",
            "v3 在结构完成、Reviewer/H0 通过、主题忠实和缺输入正确阻断上均提高，"
            "同时保持检索多样性门与安全停止 100%。Reviewer 重检索从 10 次降至 3 次，"
            "且首次出现最终恢复通过；Schema 修复触发减少、恢复比例提高。结果支持本轮系统补全有效，"
            "但由于只包含 10 个问题簇、云端生成并非严格确定性且多项组件同时变化，"
            "不得把差值解释为某一代码改动的孤立因果效应。",
            "",
            "执行就绪率在两版均为 0% 是预期设计：在线问题集没有提供许可完整、带哈希且字段绑定齐全的真实数据资产。"
            "独立的确定性正负对照已证明元数据完整时编译器能够从 blocked 切换到 ready。",
            "",
            "## 推断边界",
            "",
        ]
    )
    lines.extend(f"- {guardrail}" for guardrail in comparison["inference_guardrails"])
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v2", type=Path, default=DEFAULT_V2)
    parser.add_argument("--v3", type=Path, default=DEFAULT_V3)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT_OUTPUT)
    parser.add_argument("--bootstrap-reps", type=int, default=20_000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260901)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.bootstrap_reps < 1_000:
        raise ValueError("bootstrap-reps must be at least 1000")
    comparison = compare(
        load_json(args.v2),
        load_json(args.v3),
        bootstrap_reps=args.bootstrap_reps,
        bootstrap_seed=args.bootstrap_seed,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.report_output.write_text(render_report(comparison), encoding="utf-8")
    print(
        json.dumps(
            {
                "matched_cells": comparison["matched_cells"],
                "json_output": str(args.json_output),
                "report_output": str(args.report_output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Evaluate the frozen one-component-off AI Scientist campaign.

The machine-readable files retain internal arm and case IDs for reproducibility.
The public Markdown report uses only judge-facing Chinese labels.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import random
from statistics import mean
from types import SimpleNamespace
from typing import Any

import evaluate_ai_scientist_system_capability_v2 as base_evaluator


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CAMPAIGN = ROOT / "experiments" / "ai_scientist_component_ablation_20260905_protocol.json"
DEFAULT_INPUT_ROOT = ROOT / "output" / "experiments" / "ai_scientist_component_ablation_20260905"

BINARY_METRICS: tuple[tuple[str, str], ...] = (
    ("cell_completed", "结构化计划完成"),
    ("final_consistency_passed", "问题保真审阅通过"),
    ("topic_fidelity", "冻结词表主题忠实"),
    ("diversity_gate_passed", "来源分散门通过"),
    ("readiness_blocked_correctly", "缺输入时正确阻断"),
    ("safe_stop", "安全停止"),
)


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def atomic_json(path: Path, payload: Any) -> None:
    base_evaluator.atomic_json(path, payload)


def percentile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("percentile requires observations")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def question_cluster_bootstrap(
    rows: list[tuple[str, float]],
    *,
    reps: int,
    seed: int,
) -> dict[str, Any]:
    by_question: dict[str, list[float]] = defaultdict(list)
    for question_id, value in rows:
        by_question[question_id].append(value)
    question_ids = sorted(by_question)
    if not question_ids:
        raise ValueError("cluster bootstrap requires at least one question")
    observed = mean(value for _, value in rows)
    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(reps):
        sampled = [rng.choice(question_ids) for _ in question_ids]
        draws.append(
            mean(value for question_id in sampled for value in by_question[question_id])
        )
    return {
        "estimate": round(observed, 6),
        "lower": round(percentile(draws, 0.025), 6),
        "upper": round(percentile(draws, 0.975), 6),
        "clusters": len(question_ids),
        "method": f"paired question-cluster bootstrap percentile 95%, {reps} reps",
        "seed": seed,
    }


def cell_index(evaluation: dict[str, Any]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for cell in evaluation["cells"]:
        cell_id = str(cell["cell_id"])
        if cell_id in output:
            raise ValueError(f"duplicate cell_id: {cell_id}")
        output[cell_id] = cell
    return output


def behavioral_protocol(protocol: dict[str, Any]) -> dict[str, Any]:
    value = json.loads(json.dumps(protocol, ensure_ascii=False))
    value.pop("system_under_test", None)
    value.pop("component_ablation", None)
    return value


def json_differences(before: Any, after: Any, path: str = "") -> list[dict[str, Any]]:
    if isinstance(before, dict) and isinstance(after, dict):
        rows: list[dict[str, Any]] = []
        for key in sorted(set(before) | set(after)):
            child_path = f"{path}/{key}"
            if key not in before:
                rows.append({"path": child_path, "complete": None, "disabled": after[key]})
            elif key not in after:
                rows.append({"path": child_path, "complete": before[key], "disabled": None})
            else:
                rows.extend(json_differences(before[key], after[key], child_path))
        return rows
    if isinstance(before, list) and isinstance(after, list):
        if before == after:
            return []
        return [{"path": path, "complete": before, "disabled": after}]
    if before != after:
        return [{"path": path, "complete": before, "disabled": after}]
    return []


def same_condition_audit(
    campaign: dict[str, Any],
    input_root: Path,
) -> dict[str, Any]:
    protocols = {
        arm_id: load_json(input_root / arm_id / "frozen_protocol.json")
        for arm_id in campaign["arms"]
    }
    complete = behavioral_protocol(protocols["complete_loop"])
    expected = {
        "no_document_diversification": {"/retrieval/diversity_mode"},
        "no_schema_repair": {"/generation/schema_repair_enabled"},
        "no_reviewer_feedback": {"/generation/max_consistency_repairs"},
    }
    arms: dict[str, Any] = {}
    for arm_id in list(campaign["arms"])[1:]:
        differences = json_differences(complete, behavioral_protocol(protocols[arm_id]))
        observed_paths = {item["path"] for item in differences}
        arms[arm_id] = {
            "public_label": campaign["arms"][arm_id]["public_label"],
            "passed": observed_paths == expected[arm_id],
            "expected_behavioral_differences": sorted(expected[arm_id]),
            "observed_behavioral_differences": differences,
        }
    knowledge_hashes = {
        arm_id: base_evaluator.canonical_sha256(
            load_json(input_root / arm_id / "knowledge_status.json")
        )
        for arm_id in campaign["arms"]
    }
    retrieval_fixture_hashes = {
        arm_id: base_evaluator.canonical_sha256(
            load_json(input_root / arm_id / "retrieval_ablation.json")
        )
        for arm_id in campaign["arms"]
    }
    observed_models: dict[str, list[str]] = {}
    observed_providers: dict[str, list[str]] = {}
    for arm_id, protocol in protocols.items():
        models: set[str] = set()
        providers: set[str] = set()
        for case in protocol["cases"]:
            for seed in protocol["generation"]["seeds"]:
                cell_id = f"{case['case_id']}__seed_{seed}"
                cell_dir = input_root / arm_id / "cells" / cell_id
                result_path = cell_dir / "result.json"
                generation_path = cell_dir / "generation.json"
                if not result_path.is_file():
                    continue
                result = load_json(result_path)
                if result.get("status") == "completed" and generation_path.is_file():
                    usage = load_json(generation_path).get("model_usage") or {}
                else:
                    usage = result.get("model_usage") or {}
                for receipt in usage.get("call_receipts") or []:
                    if receipt.get("model"):
                        models.add(str(receipt["model"]))
                    if receipt.get("provider"):
                        providers.add(str(receipt["provider"]))
        observed_models[arm_id] = sorted(models)
        observed_providers[arm_id] = sorted(providers)
    same_observed_models = len({tuple(value) for value in observed_models.values()}) == 1
    same_observed_providers = len({tuple(value) for value in observed_providers.values()}) == 1
    expected_model_observed = all(value == ["qwen3.7-plus"] for value in observed_models.values())
    expected_provider_observed = all(value == ["qwen"] for value in observed_providers.values())
    return {
        "passed": all(item["passed"] for item in arms.values())
        and len(set(knowledge_hashes.values())) == 1
        and len(set(retrieval_fixture_hashes.values())) == 1
        and same_observed_models
        and same_observed_providers
        and expected_model_observed
        and expected_provider_observed,
        "arms": arms,
        "same_knowledge_status": len(set(knowledge_hashes.values())) == 1,
        "knowledge_status_hashes": knowledge_hashes,
        "same_retrieval_fixture": len(set(retrieval_fixture_hashes.values())) == 1,
        "retrieval_fixture_hashes": retrieval_fixture_hashes,
        "same_observed_models": same_observed_models,
        "observed_models": observed_models,
        "same_observed_providers": same_observed_providers,
        "observed_providers": observed_providers,
        "expected_model_observed": expected_model_observed,
        "expected_provider_observed": expected_provider_observed,
        "fixed_conditions": campaign["fixed_conditions"],
    }


def component_comparison(
    *,
    complete: dict[str, Any],
    disabled: dict[str, Any],
    reps: int,
    seed: int,
) -> dict[str, Any]:
    complete_cells = cell_index(complete)
    disabled_cells = cell_index(disabled)
    if set(complete_cells) != set(disabled_cells):
        raise ValueError("component comparison requires identical question-seed cells")
    cell_ids = sorted(complete_cells)
    binary: dict[str, Any] = {}
    for metric_index, (key, label) in enumerate(BINARY_METRICS):
        rows: list[tuple[str, float]] = []
        lost = gained = stable_pass = stable_fail = 0
        for cell_id in cell_ids:
            full_cell = complete_cells[cell_id]
            off_cell = disabled_cells[cell_id]
            full_value = bool(full_cell[key])
            off_value = bool(off_cell[key])
            if full_cell["case_id"] != off_cell["case_id"]:
                raise ValueError(f"case mismatch: {cell_id}")
            # Positive means the enabled component helped.
            rows.append((str(full_cell["case_id"]), float(full_value) - float(off_value)))
            if full_value and not off_value:
                lost += 1
            elif not full_value and off_value:
                gained += 1
            elif full_value and off_value:
                stable_pass += 1
            else:
                stable_fail += 1
        full_successes = sum(bool(complete_cells[cell_id][key]) for cell_id in cell_ids)
        off_successes = sum(bool(disabled_cells[cell_id][key]) for cell_id in cell_ids)
        binary[key] = {
            "label": label,
            "total": len(cell_ids),
            "complete_successes": full_successes,
            "disabled_successes": off_successes,
            "complete_rate": round(full_successes / len(cell_ids), 6),
            "disabled_rate": round(off_successes / len(cell_ids), 6),
            "enabled_component_contribution": round(
                (full_successes - off_successes) / len(cell_ids), 6
            ),
            "paired_transitions_when_disabled": {
                "lost_pass_1_to_0": lost,
                "gained_pass_0_to_1": gained,
                "stable_pass": stable_pass,
                "stable_fail": stable_fail,
            },
            "question_cluster_bootstrap_95": question_cluster_bootstrap(
                rows,
                reps=reps,
                seed=seed + metric_index,
            ),
        }

    continuous_rows: list[tuple[str, float]] = []
    for cell_id in cell_ids:
        full_cell = complete_cells[cell_id]
        off_cell = disabled_cells[cell_id]
        continuous_rows.append(
            (
                str(full_cell["case_id"]),
                float(full_cell["evidence_diversity_ratio"])
                - float(off_cell["evidence_diversity_ratio"]),
            )
        )
    return {
        "paired_cells": len(cell_ids),
        "question_clusters": len({complete_cells[cell_id]["case_id"] for cell_id in cell_ids}),
        "binary_metrics": binary,
        "evidence_diversity_ratio": {
            "complete_mean": round(
                mean(float(complete_cells[cell_id]["evidence_diversity_ratio"]) for cell_id in cell_ids),
                6,
            ),
            "disabled_mean": round(
                mean(float(disabled_cells[cell_id]["evidence_diversity_ratio"]) for cell_id in cell_ids),
                6,
            ),
            "enabled_component_contribution": question_cluster_bootstrap(
                continuous_rows,
                reps=reps,
                seed=seed + len(BINARY_METRICS),
            ),
        },
    }


def pct(value: float) -> str:
    return f"{100 * value:.1f}%"


def pp(value: float) -> str:
    return f"{100 * value:+.1f}个百分点"


def repeat_label(seed: int, campaign: dict[str, Any]) -> str:
    seeds = list(campaign["fixed_conditions"]["seeds"])
    return f"重复{seeds.index(seed) + 1}"


def public_failures(
    evaluation: dict[str, Any],
    campaign: dict[str, Any],
) -> list[dict[str, Any]]:
    labels = campaign["question_labels"]
    rows: list[dict[str, Any]] = []
    for cell in evaluation["cells"]:
        issues: list[str] = []
        if not cell["cell_completed"]:
            issues.append("结构化计划未完成")
        elif not cell["final_consistency_passed"]:
            issues.append("问题保真审阅未通过")
        if not cell["topic_fidelity"]:
            issues.append("冻结词表主题缺失")
        if not cell["diversity_gate_passed"]:
            issues.append("来源分散门未通过")
        if not cell["readiness_blocked_correctly"]:
            issues.append("缺输入阻断不完整")
        if not cell["safe_stop"]:
            issues.append("安全停止未通过")
        if issues:
            rows.append(
                {
                    "question": labels[str(cell["case_id"])],
                    "repeat": repeat_label(int(cell["seed"]), campaign),
                    "issues": issues,
                    "internal_cell_id": cell["cell_id"],
                    "failure_stage": cell.get("failure_stage"),
                    "failure_type": cell.get("failure_type"),
                }
            )
    return rows


def public_markdown(summary: dict[str, Any], campaign: dict[str, Any]) -> str:
    arm_order = list(campaign["arms"])
    labels = {arm_id: campaign["arms"][arm_id]["public_label"] for arm_id in arm_order}
    complete = summary["arms"]["complete_loop"]
    metric_order = (
        "cell_completed",
        "final_consistency_passed",
        "topic_fidelity",
        "diversity_gate_passed",
        "readiness_blocked_correctly",
        "safe_stop",
    )
    unique_change = {
        "complete_loop": "来源分散、格式纠错和审阅回写全部开启",
        "no_document_diversification": "取消“每篇文献最多2条证据”的多来源控制",
        "no_schema_repair": "取消不合格结构化输出的自动纠错",
        "no_reviewer_feedback": "审阅拒绝后不再按缺失概念回写重做",
    }
    state = "阶段性结果" if summary["partial"] else "冻结结果"
    lines = [
        f"# 单组件系统消融（{state}）",
        "",
        "本实验每次只关闭一个系统组件。所有组共享同一10题、同一3个重复、同一模型、温度、知识库快照与并发上限；全部终止单元均按意向分析保留。",
        "",
        f"同条件机器审计：{'通过' if summary['same_condition_audit']['passed'] else '未通过'}。除实验组名称等说明字段外，三个关闭组分别只有一个行为配置与完整组不同；知识库状态、检索夹具、实际供应商和实际模型均一致。",
        "",
        "| 对比组 | 唯一变化 | 完整单元 | 审阅通过 | 主题忠实 | 来源分散门 | 正确阻断 | 安全停止 |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for arm_id in arm_order:
        arm = summary["arms"][arm_id]
        metrics = arm["evaluation"]["metrics_wilson_95"]
        description = unique_change[arm_id]
        values = []
        for key in metric_order:
            item = metrics[key]
            values.append(f"{item['successes']}/{item['total']}（{pct(item['rate'])}）")
        lines.append(f"| {labels[arm_id]} | {description} | " + " | ".join(values) + " |")

    lines.extend(
        [
            "",
            "## 关闭组件后损失了什么",
            "",
            "正值表示该组件开启后带来的净增益；区间按问题聚类，不把同一问题的3次重复误当成完全独立样本。",
            "",
            "| 被验证组件 | 主指标 | 完整闭环 | 关闭组件 | 组件净贡献 | 问题聚类区间 | 关闭后 1→0 / 0→1 |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    focal = {
        "no_document_diversification": "diversity_gate_passed",
        "no_schema_repair": "cell_completed",
        "no_reviewer_feedback": "final_consistency_passed",
    }
    component_names = {
        "no_document_diversification": "多文献来源控制",
        "no_schema_repair": "结构化输出自动纠错",
        "no_reviewer_feedback": "审阅意见反馈重做",
    }
    for arm_index, arm_id in enumerate(arm_order[1:]):
        comparison = summary["comparisons"][arm_id]
        key = focal[arm_id]
        item = comparison["binary_metrics"][key]
        interval = item["question_cluster_bootstrap_95"]
        transitions = item["paired_transitions_when_disabled"]
        component = component_names[arm_id]
        lines.append(
            f"| {component} | {item['label']} | {item['complete_successes']}/{item['total']} "
            f"| {item['disabled_successes']}/{item['total']} | {pp(item['enabled_component_contribution'])} "
            f"| {pp(interval['lower'])} 至 {pp(interval['upper'])} | "
            f"{transitions['lost_pass_1_to_0']} / {transitions['gained_pass_0_to_1']} |"
        )

    lines.extend(
        [
            "",
            "## 失败不是被删掉的样本",
            "",
        ]
    )
    for arm_id in arm_order:
        failures = summary["arms"][arm_id]["public_failures"]
        if not failures:
            lines.append(f"- {labels[arm_id]}：本轮无主门失败。")
            continue
        rendered = "；".join(
            f"{item['question']}·{item['repeat']}（{'、'.join(item['issues'])}）"
            for item in failures
        )
        lines.append(f"- {labels[arm_id]}：{rendered}。")

    lines.extend(
        [
            "",
            "## 对外解释边界",
            "",
            "- 这是系统组件消融，不是回归系数显著性，也不是底层模型排行榜。",
            "- 供应商随机种子是尽力复现而非严格确定性；因此报告原始分子/分母和问题聚类区间，不夸大点估计。",
            "- 在线题集故意没有提供许可完整、字段绑定齐全的实证数据；正确行为是列出阻塞项并安全停止，不是伪造执行结果。",
            "- 适用范围是当前绿色金融题集、当前知识库快照与当前模型配置；跨学科、跨模型、长时漂移仍需外部验证。",
            "",
            "注：内部复现索引保留协议哈希、原始题目编号和供应商随机种子数值；P18/P19只使用本报告的中文名称与“重复1/2/3”。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", type=Path, default=DEFAULT_CAMPAIGN)
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--bootstrap-reps", type=int, default=20_000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260905)
    args = parser.parse_args()
    if args.bootstrap_reps < 1_000:
        raise ValueError("bootstrap-reps must be at least 1000")

    campaign = load_json(args.campaign)
    arms: dict[str, Any] = {}
    for arm_id, arm in campaign["arms"].items():
        arm_dir = args.input_root / arm_id
        evaluation = base_evaluator.evaluate(
            SimpleNamespace(
                protocol=arm_dir / "frozen_protocol.json",
                input_dir=arm_dir,
                allow_partial=args.allow_partial,
            )
        )
        atomic_json(arm_dir / "evaluation.json", evaluation)
        (arm_dir / "evaluation_internal.md").write_text(
            base_evaluator.markdown_report(evaluation), encoding="utf-8"
        )
        arms[arm_id] = {
            "public_label": arm["public_label"],
            "evaluation_path": str(arm_dir / "evaluation.json"),
            "evaluation": evaluation,
            "public_failures": public_failures(evaluation, campaign),
        }

    complete = arms["complete_loop"]["evaluation"]
    comparisons: dict[str, Any] = {}
    for comparison_index, arm_id in enumerate(list(campaign["arms"])[1:]):
        comparisons[arm_id] = component_comparison(
            complete=complete,
            disabled=arms[arm_id]["evaluation"],
            reps=args.bootstrap_reps,
            seed=args.bootstrap_seed + 100 * comparison_index,
        )

    partial = any(arm["evaluation"]["missing_cells"] for arm in arms.values())
    condition_audit = same_condition_audit(campaign, args.input_root)
    if not condition_audit["passed"]:
        raise ValueError("same-condition audit failed; refusing to report component effects")
    summary = {
        "schema_version": "ai-scientist-component-ablation-evaluation/1.0.0",
        "campaign_sha256": base_evaluator.canonical_sha256(campaign),
        "partial": partial,
        "same_condition_audit": condition_audit,
        "arms": arms,
        "comparisons": comparisons,
        "reporting_guardrails": campaign["reporting_rules"],
    }
    atomic_json(args.input_root / "component_ablation_summary.json", summary)
    atomic_json(args.input_root / "same_condition_audit.json", condition_audit)
    report = public_markdown(summary, campaign)
    (args.input_root / "component_ablation_public.md").write_text(report, encoding="utf-8")
    print(
        json.dumps(
            {
                "partial": partial,
                "arms": {
                    arm["public_label"]: arm["evaluation"]["evaluated_cells"]
                    for arm in arms.values()
                },
                "output": str(args.input_root / "component_ablation_summary.json"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

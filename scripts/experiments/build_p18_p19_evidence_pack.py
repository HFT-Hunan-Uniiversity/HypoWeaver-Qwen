#!/usr/bin/env python3
"""Build judge-facing P18/P19 evidence materials from frozen experiment outputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COMPONENT = (
    ROOT
    / "output"
    / "experiments"
    / "ai_scientist_component_ablation_20260905"
    / "component_ablation_summary.json"
)
DEFAULT_HISTORICAL = (
    ROOT
    / "output"
    / "experiments"
    / "ai_scientist_system_capability_v3"
    / "comparison_v2_v3.json"
)
DEFAULT_HISTORICAL_EVALUATION = (
    ROOT
    / "output"
    / "experiments"
    / "ai_scientist_system_capability_v3"
    / "evaluation.json"
)
DEFAULT_READINESS = (
    ROOT
    / "output"
    / "experiments"
    / "execution_readiness_contract_control_v1"
    / "result.json"
)
DEFAULT_VISION = (
    ROOT
    / "output"
    / "experiments"
    / "qwen_vl_scientific_table"
    / "qwen_runs"
    / "batch_summary.json"
)
DEFAULT_CAMPAIGN = (
    ROOT / "experiments" / "ai_scientist_component_ablation_20260905_protocol.json"
)
DEFAULT_OUTPUT = ROOT / "output" / "p18_p19_system_evidence_20260905"

HISTORICAL_METRICS: tuple[tuple[str, str], ...] = (
    ("cell_completed", "结构化计划完成"),
    ("final_consistency_passed", "问题保真审阅通过"),
    ("topic_fidelity", "冻结词表主题忠实"),
    ("readiness_blocked_correctly", "缺输入时正确阻断"),
    ("safe_stop", "安全停止"),
)
COMPONENT_FOCAL = {
    "no_document_diversification": ("多文献来源控制", "diversity_gate_passed"),
    "no_schema_repair": ("结构化输出自动纠错", "cell_completed"),
    "no_reviewer_feedback": ("审阅意见反馈重做", "final_consistency_passed"),
}
PUBLIC_ARM_LABELS = {
    "complete_loop": "完整审阅闭环",
    "no_document_diversification": "关闭来源去重",
    "no_schema_repair": "关闭结构纠错",
    "no_reviewer_feedback": "关闭审阅反馈回写",
}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def write_json(path: Path, value: Any) -> None:
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pct(value: float) -> str:
    return f"{100 * value:.1f}%"


def count_pct(successes: int, total: int) -> str:
    return f"{successes}/{total}（{100 * successes / total:.1f}%）"


def signed_pp(value: float) -> str:
    return f"{100 * value:+.1f}个百分点"


def repeat_label(seed: int, campaign: dict[str, Any]) -> str:
    seeds = list(campaign["fixed_conditions"]["seeds"])
    return f"重复{seeds.index(seed) + 1}"


def public_status(cell: dict[str, Any]) -> tuple[str, str]:
    if not cell["cell_completed"]:
        return "结构失败", "结构化输出在有界纠错预算内仍未满足契约；系统记录失败并停止。"
    if not cell["final_consistency_passed"]:
        return "审阅阻断", "计划改变核心变量角色或遗漏问题限定；审阅闸门未放行。"
    if not cell["topic_fidelity"]:
        return "词表未命中", "语义审阅通过，但冻结词表未匹配到全部预注册概念；主分析仍计失败。"
    if not cell["diversity_gate_passed"]:
        return "来源集中", "证据过度集中于少数文献；来源分散门记录为失败。"
    if not cell["readiness_blocked_correctly"]:
        return "阻断异常", "缺少许可完整数据时，执行阻断信息不完整。"
    if not cell["safe_stop"]:
        return "停止异常", "缺输入条件下未满足安全停止要求。"
    return "核心通过", "结构、问题保真、主题、来源、阻断和安全停止六项主门均通过。"


def historical_rows(historical: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, label in HISTORICAL_METRICS:
        item = historical["binary_metrics"][key]
        interval = item["cluster_bootstrap_change_95"]
        transition = item["paired_transitions"]
        rows.append(
            {
                "系统指标": label,
                "基础门控流程": count_pct(item["v2_successes"], item["total"]),
                "增强审阅闭环": count_pct(item["v3_successes"], item["total"]),
                "绝对变化": signed_pp(item["absolute_change"]),
                "问题聚类区间": f"{signed_pp(interval['lower'])} 至 {signed_pp(interval['upper'])}",
                "改善/退化单元": f"{transition['improved_0_to_1']} / {transition['regressed_1_to_0']}",
            }
        )
    return rows


def component_rows(component: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    focal_rows: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    for arm_id, (component_name, focal_key) in COMPONENT_FOCAL.items():
        comparison = component["comparisons"][arm_id]
        for key, item in comparison["binary_metrics"].items():
            interval = item["question_cluster_bootstrap_95"]
            transitions = item["paired_transitions_when_disabled"]
            row = {
                "被验证组件": component_name,
                "关闭组件组": PUBLIC_ARM_LABELS[arm_id],
                "系统指标": item["label"],
                "完整审阅闭环": count_pct(item["complete_successes"], item["total"]),
                "关闭组件": count_pct(item["disabled_successes"], item["total"]),
                "组件净贡献": signed_pp(item["enabled_component_contribution"]),
                "问题聚类区间": f"{signed_pp(interval['lower'])} 至 {signed_pp(interval['upper'])}",
                "关闭后丢失/新增通过": f"{transitions['lost_pass_1_to_0']} / {transitions['gained_pass_0_to_1']}",
            }
            all_rows.append(row)
            if key == focal_key:
                focal_rows.append(row)
    return focal_rows, all_rows


def p18_template_rows(component: dict[str, Any]) -> list[dict[str, Any]]:
    same_conditions = "同一10题×3重复、同一模型/温度/知识库/检索规模；只关闭该组件"
    mechanism_cost = {
        "no_document_diversification": "不增加模型调用；代价是检索排序需执行文献级配额",
        "no_schema_repair": "仅在结构不合格时增加有界纠错调用；不无限重试",
        "no_reviewer_feedback": "仅在审阅拒绝时最多增加一轮检索—规划—复审",
    }
    rows: list[dict[str, Any]] = []
    for arm_id, (component_name, focal_key) in COMPONENT_FOCAL.items():
        item = component["comparisons"][arm_id]["binary_metrics"][focal_key]
        interval = item["question_cluster_bootstrap_95"]
        rows.append(
            {
                "实际比较对象": f"完整审阅闭环 对比 {PUBLIC_ARM_LABELS[arm_id]}",
                "保持相同的条件": same_conditions,
                "采用的评价方法": f"{item['label']}；同问题同重复配对，按问题成组给95%区间",
                "本作品结果": count_pct(item["complete_successes"], item["total"]),
                "对照结果": count_pct(item["disabled_successes"], item["total"]),
                "结论与代价": (
                    f"组件净贡献{signed_pp(item['enabled_component_contribution'])}，区间"
                    f"{signed_pp(interval['lower'])}至{signed_pp(interval['upper'])}；"
                    f"{mechanism_cost[arm_id]}"
                ),
            }
        )
    return rows


def full_cells(component: dict[str, Any]) -> list[dict[str, Any]]:
    return list(component["arms"]["complete_loop"]["evaluation"]["cells"])


def matrix_rows(
    component: dict[str, Any], campaign: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    labels = campaign["question_labels"]
    by_question: dict[str, dict[int, dict[str, Any]]] = {}
    detail: list[dict[str, Any]] = []
    for cell in full_cells(component):
        case_id = str(cell["case_id"])
        repeat = int(repeat_label(int(cell["seed"]), campaign).replace("重复", ""))
        by_question.setdefault(case_id, {})[repeat] = cell
        status, explanation = public_status(cell)
        detail.append(
            {
                "研究问题": labels[case_id],
                "重复": f"重复{repeat}",
                "结构完成": "通过" if cell["cell_completed"] else "未通过",
                "问题保真审阅": "通过" if cell["final_consistency_passed"] else "未通过",
                "冻结词表主题": "通过" if cell["topic_fidelity"] else "未通过",
                "来源分散门": "通过" if cell["diversity_gate_passed"] else "未通过",
                "缺输入正确阻断": "通过" if cell["readiness_blocked_correctly"] else "未通过",
                "安全停止": "通过" if cell["safe_stop"] else "未通过",
                "归纳状态": status,
                "解释": explanation,
            }
        )
    matrix: list[dict[str, Any]] = []
    for case_id in campaign["question_labels"]:
        repeats = by_question.get(case_id, {})
        if set(repeats) != {1, 2, 3}:
            raise ValueError(f"question is missing repeats: {case_id}")
        matrix.append(
            {
                "研究问题": labels[case_id],
                "重复1": public_status(repeats[1])[0],
                "重复2": public_status(repeats[2])[0],
                "重复3": public_status(repeats[3])[0],
            }
        )
    return matrix, sorted(detail, key=lambda row: (list(labels.values()).index(row["研究问题"]), row["重复"]))


def p19_template_overall_rows(component: dict[str, Any]) -> list[dict[str, Any]]:
    evaluation = component["arms"]["complete_loop"]["evaluation"]
    metrics = evaluation["metrics_wilson_95"]
    cells = evaluation["cells"]
    structure_failures = sum(not cell["cell_completed"] for cell in cells)
    reviewer_blocks = sum(
        cell["cell_completed"] and not cell["final_consistency_passed"] for cell in cells
    )
    wordlist_misses = sum(
        cell["cell_completed"]
        and cell["final_consistency_passed"]
        and not cell["topic_fidelity"]
        for cell in cells
    )
    return [
        {
            "实际测试或实验范围": "研究问题→证据→结构化计划→问题保真审阅",
            "完成的闭环轮次或样本": "10题×3重复＝30单元",
            "主要评价结果": (
                f"结构{count_pct(metrics['cell_completed']['successes'], 30)}；"
                f"审阅{count_pct(metrics['final_consistency_passed']['successes'], 30)}；"
                f"主题{count_pct(metrics['topic_fidelity']['successes'], 30)}"
            ),
            "重复运行表现": "每题三次独立调用；逐单元矩阵留痕",
            "仍存在的问题": f"结构失败{structure_failures}；审阅阻断{reviewer_blocks}；词表未命中{wordlist_misses}",
        },
        {
            "实际测试或实验范围": "证据来源分散与输入就绪编译",
            "完成的闭环轮次或样本": "30单元＋确定性正负对照",
            "主要评价结果": (
                f"来源门{count_pct(metrics['diversity_gate_passed']['successes'], 30)}；"
                f"正确阻断{count_pct(metrics['readiness_blocked_correctly']['successes'], 30)}"
            ),
            "重复运行表现": "缺数据时不伪造执行；完整元数据正对照可切换为候选就绪",
            "仍存在的问题": "真实数据许可、字段绑定与识别假设仍需研究者确认",
        },
        {
            "实际测试或实验范围": "失败封闭、可追溯回执与安全停止",
            "完成的闭环轮次或样本": "全部30个终止单元",
            "主要评价结果": f"安全停止{count_pct(metrics['safe_stop']['successes'], 30)}",
            "重复运行表现": "失败不删除、不用补跑替换；保留协议哈希与匿名化调用回执",
            "仍存在的问题": "供应商随机种子只能尽力复现，不能保证逐字一致",
        },
    ]


def p19_template_boundary_rows(component: dict[str, Any]) -> list[dict[str, Any]]:
    cells = component["arms"]["complete_loop"]["evaluation"]["cells"]
    structure_failures = sum(not cell["cell_completed"] for cell in cells)
    reviewer_blocks = sum(
        cell["cell_completed"] and not cell["final_consistency_passed"] for cell in cells
    )
    wordlist_misses = sum(
        cell["cell_completed"]
        and cell["final_consistency_passed"]
        and not cell["topic_fidelity"]
        for cell in cells
    )
    return [
        {
            "典型失败或边界问题": "生成式结构波动",
            "实际表现": (
                f"{structure_failures}/30 单元未形成契约合格计划"
                if structure_failures
                else "本轮未观察到（0/30）"
            ),
            "原因分析": "模型输出在有界纠错预算内仍可能违反结构约束",
            "目前能够做到的程度": "记录类型化失败与调用回执，禁止伪计划进入下一阶段",
        },
        {
            "典型失败或边界问题": "问题语义或变量角色偏移",
            "实际表现": (
                f"{reviewer_blocks}/30 单元被问题保真审阅阻断"
                if reviewer_blocks
                else "本轮未观察到（0/30）"
            ),
            "原因分析": "候选计划可能遗漏限定条件，或改变暴露/结果/机制角色",
            "目前能够做到的程度": "最多反馈重做一次；仍不合格则保守停止并交还研究者",
        },
        {
            "典型失败或边界问题": "冻结词表对同义词形覆盖有限",
            "实际表现": (
                f"{wordlist_misses}/30 单元出现“审阅通过但词表未命中”"
                if wordlist_misses
                else "本轮未观察到（0/30）"
            ),
            "原因分析": "可复算正则裁判不等同于语义理解，可能漏掉词形或非连续表达",
            "目前能够做到的程度": "主分析不事后改分；下一轮题集预注册时再扩充裁判规则",
        },
    ]


def p19_footer_text() -> str:
    return "\n".join(
        [
            "# P19 模板页脚四问",
            "",
            "- 能够服务的真实用户和实验环节：帮助研究者从绿色金融问题出发完成证据检索、结构化研究计划、问题保真审阅、数据需求清单与执行就绪检查。",
            "- 相比基础方式节省或增加的成本：减少不可复核的人工抄录与反复沟通；增加有界的结构纠错和审阅回写调用，且只在失败触发时发生。",
            "- 必须由研究者决定、审批或承担责任的事项：数据许可与合规、变量字段绑定、识别策略与排除限制、统计方案、结果解释和科学结论授权。",
            "- 尚不能支持的任务、仪器、数据或部署范围：无许可或无哈希的数据不能执行；不能替代实验仪器和线下采集；未验证跨领域、跨模型和长期漂移；不能自主发布结论或部署政策。",
        ]
    )


def figure_captions_text() -> str:
    return "\n".join(
        [
            "# 图注与来源说明",
            "",
            "## P18 历史同条件提升图",
            "",
            "注：同一10个绿色金融问题、每题3次重复的历史配对比较。圆点为增强审阅闭环相对基础门控流程的原始通过率差，横线为按研究问题成组重抽样的95%区间。历史整包升级同时改变多个环节，不解释为单个组件的孤立作用。",
            "",
            "## P18 单组件净贡献图",
            "",
            "注：四个实验组共享题集、重复、模型、温度、知识库、检索规模和并发上限；每个关闭组只改变一个行为配置。圆点为完整审阅闭环相对关闭组件组的主指标配对差，横线为按研究问题成组重抽样的95%区间。供应商随机种子只能尽力复现。",
            "",
            "## P19 10题×3重复能力矩阵",
            "",
            "注：每行是一类评委可读研究问题，每列是一次独立重复。实心圆表示六项主门均通过；空心菱形表示语义审阅通过但冻结词表未命中；三角形表示问题保真审阅阻断；叉号表示结构化计划未完成。所有终止单元均保留在30个单元的分母。",
            "",
            "来源：冻结实验协议、逐单元匿名化调用回执、独立复算结果及同条件差异审计。系统能力指标不使用回归系数或显著性星号。",
        ]
    )


def failure_cards(matrix: list[dict[str, Any]], detail: list[dict[str, Any]]) -> str:
    abnormal = [row for row in detail if row["归纳状态"] != "核心通过"]
    lines = [
        "# P19 异常单元证据卡",
        "",
        "所有异常均保留在30个单元的分母中。下面的说明用于回答“系统哪里会失败、失败后做了什么”。",
        "",
    ]
    if not abnormal:
        lines.append("本轮完整审阅闭环未出现主门异常。")
    for index, row in enumerate(abnormal, start=1):
        lines.extend(
            [
                f"## 证据卡{index}｜{row['研究问题']}·{row['重复']}",
                "",
                f"- 观察到：{row['归纳状态']}。",
                f"- 判定依据：{row['解释']}",
                f"- 六项门控：结构={row['结构完成']}；审阅={row['问题保真审阅']}；主题={row['冻结词表主题']}；来源={row['来源分散门']}；阻断={row['缺输入正确阻断']}；停止={row['安全停止']}。",
                "- 汇报原则：不删除、不补跑替换、不事后改词表；以原始分子/分母进入主表。",
                "",
            ]
        )
    return "\n".join(lines)


def historical_anomaly_text(
    evaluation: dict[str, Any], campaign: dict[str, Any]
) -> str:
    labels = campaign["question_labels"]
    rows = []
    for cell in evaluation["cells"]:
        status, explanation = public_status(cell)
        if status == "核心通过":
            continue
        rows.append(
            {
                "question": labels[str(cell["case_id"])],
                "repeat": repeat_label(int(cell["seed"]), campaign),
                "status": status,
                "explanation": explanation,
            }
        )
    lines = [
        "# 备份材料：历史同条件实验异常",
        "",
        "这份材料只解释历史整包升级实验中的异常，不与本轮单组件消融合并计数。",
        "",
    ]
    if not rows:
        lines.append("历史完整流程在六项主门上没有异常单元。")
    for row in rows:
        lines.append(
            f"- {row['question']}·{row['repeat']}：{row['status']}。{row['explanation']}"
        )
    lines.extend(
        [
            "",
            "历史冻结主分析不因人工复核同义表达而事后改分；这些异常用于说明系统边界和下一轮裁判改进方向。",
        ]
    )
    return "\n".join(lines)


def font() -> font_manager.FontProperties:
    for candidate in (
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simsun.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
    ):
        if candidate.is_file():
            return font_manager.FontProperties(fname=str(candidate))
    return font_manager.FontProperties(family="DejaVu Sans")


def render_matrix(matrix: list[dict[str, Any]], output_dir: Path) -> None:
    font_prop = font()
    status_style = {
        "核心通过": {"marker": "o", "face": "#111111", "edge": "#111111"},
        "词表未命中": {"marker": "D", "face": "white", "edge": "#111111"},
        "审阅阻断": {"marker": "^", "face": "#777777", "edge": "#111111"},
        "结构失败": {"marker": "x", "face": "#111111", "edge": "#111111"},
        "来源集中": {"marker": "s", "face": "white", "edge": "#111111"},
        "阻断异常": {"marker": "P", "face": "white", "edge": "#111111"},
        "停止异常": {"marker": "X", "face": "white", "edge": "#111111"},
    }
    figure, axis = plt.subplots(figsize=(7.2, 6.4))
    y_positions = list(range(len(matrix)))[::-1]
    for y, row in zip(y_positions, matrix):
        for x, repeat in enumerate(("重复1", "重复2", "重复3"), start=1):
            style = status_style[row[repeat]]
            scatter_options = {
                "marker": style["marker"],
                "s": 82,
                "linewidths": 1.1,
                "zorder": 3,
            }
            if style["marker"] == "x":
                scatter_options["color"] = style["edge"]
            else:
                scatter_options["facecolors"] = style["face"]
                scatter_options["edgecolors"] = style["edge"]
            axis.scatter(x, y, **scatter_options)
    axis.set_xlim(0.45, 3.55)
    axis.set_ylim(-0.7, len(matrix) - 0.3)
    axis.set_xticks((1, 2, 3))
    axis.set_xticklabels(("重复1", "重复2", "重复3"), fontproperties=font_prop, fontsize=10)
    axis.set_yticks(y_positions)
    axis.set_yticklabels([row["研究问题"] for row in matrix], fontproperties=font_prop, fontsize=9)
    axis.grid(axis="both", color="#D0D0D0", linewidth=0.55, linestyle=(0, (2, 3)))
    for side in ("top", "right"):
        axis.spines[side].set_visible(False)
    axis.spines["left"].set_linewidth(0.8)
    axis.spines["bottom"].set_linewidth(0.8)
    present = []
    for status in status_style:
        if any(status in (row["重复1"], row["重复2"], row["重复3"]) for row in matrix):
            present.append(status)
    handles = [
        Line2D(
            [0],
            [0],
            marker=status_style[status]["marker"],
            color="none",
            markerfacecolor=status_style[status]["face"],
            markeredgecolor=status_style[status]["edge"],
            markeredgewidth=1.1,
            markersize=7,
            label=status,
        )
        for status in present
    ]
    legend = axis.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.10),
        ncol=min(4, len(handles)),
        frameon=False,
        prop=font_prop,
    )
    for text_item in legend.get_texts():
        text_item.set_fontproperties(font_prop)
    figure.tight_layout(rect=(0, 0.08, 1, 1), pad=0.9)
    for extension, options in (("png", {"dpi": 300}), ("svg", {})):
        figure.savefig(
            output_dir / f"P19_10题x3重复_能力矩阵.{extension}",
            bbox_inches="tight",
            facecolor="white",
            **options,
        )
    plt.close(figure)


def historical_figure_spec(historical: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for key, label in HISTORICAL_METRICS:
        if key == "safe_stop":
            continue
        item = historical["binary_metrics"][key]
        interval = item["cluster_bootstrap_change_95"]
        rows.append(
            {
                "label": label,
                "estimate": round(100 * item["absolute_change"], 3),
                "lower": round(100 * interval["lower"], 3),
                "upper": round(100 * interval["upper"], 3),
            }
        )
    return {
        "id": "P18_historical_same_condition_gain",
        "kind": "coefficient",
        "provenance": "estimated",
        "reference": 0,
        "x_label": "增强审阅闭环相对基础门控流程的通过率变化（百分点）",
        "rows": rows,
        "caption": "同一10题×3重复的历史整包升级配对比较；点为原始通过率差，线为问题聚类bootstrap 95%区间。",
        "source": "冻结系统能力评估；失败单元全部保留。",
    }


def component_figure_spec(component: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for arm_id, (component_name, focal_key) in COMPONENT_FOCAL.items():
        item = component["comparisons"][arm_id]["binary_metrics"][focal_key]
        interval = item["question_cluster_bootstrap_95"]
        rows.append(
            {
                "label": component_name,
                "estimate": round(100 * item["enabled_component_contribution"], 3),
                "lower": round(100 * interval["lower"], 3),
                "upper": round(100 * interval["upper"], 3),
            }
        )
    return {
        "id": "P18_true_component_ablation",
        "kind": "coefficient",
        "provenance": "estimated",
        "reference": 0,
        "x_label": "组件开启相对关闭时的主指标净贡献（百分点）",
        "rows": rows,
        "caption": "同一10题×3重复、每次只关闭一个组件；点为配对通过率差，线为问题聚类bootstrap 95%区间。",
        "source": "冻结单组件消融；所有终止单元按意向分析保留。",
    }


def readiness_text(readiness: dict[str, Any]) -> str:
    positive = readiness["positive_control"]
    negative = readiness["negative_control"]
    assertions = readiness["assertions"]
    return "\n".join(
        [
            "# 执行就绪门控正负对照",
            "",
            "| 对照条件 | 数据元数据与字段绑定 | 编译结果 | 系统动作 |",
            "|---|---|---|---|",
            f"| 完整输入正对照 | 许可、哈希、粒度、时间键、连接键和变量字段齐全 | {'可执行' if positive['can_execute'] else '阻断'} | 进入候选执行态，仍不自动授权科学结论 |",
            f"| 缺失输入负对照 | 数据资源或变量绑定不完整 | {'阻断' if not negative['can_execute'] else '错误放行'} | 列出阻塞项并停在人工确认前 |",
            "",
            f"机器断言：完整输入可编译={'通过' if assertions['complete_contract_is_ready'] else '未通过'}；缺失输入被阻断={'通过' if assertions['missing_contract_is_blocked'] else '未通过'}；未执行统计={'通过' if assertions['no_statistics_executed'] else '未通过'}；未授权科学结论={'通过' if assertions['no_scientific_claim_authorized'] else '未通过'}。",
            "",
            "这项正负对照说明：在线30单元的“执行就绪率为0”不是系统无能力，而是题集没有提供许可完整的真实数据；此时正确能力是识别缺口并安全停止。",
        ]
    )


def vision_text(vision: dict[str, Any]) -> str:
    conditions = vision["aggregate"]["conditions"]
    crop = conditions["cropped_target_table"]
    full = conditions["full_page_with_distractor_table"]
    return "\n".join(
        [
            "# 补充组件证据：表格区域定位",
            "",
            "| 输入方式 | 严格逐字段完全一致 | 字段准确率 | 显著性标记准确率 |",
            "|---|---:|---:|---:|",
            f"| 先定位并裁切目标表格 | {int(round(crop['strict_exact_match_rate'] * 3))}/3 | {pct(crop['mean_field_accuracy'])} | {pct(crop['mean_significance_accuracy'])} |",
            f"| 整页输入且含干扰表格 | {int(round(full['strict_exact_match_rate'] * 3))}/3 | {pct(full['mean_field_accuracy'])} | {pct(full['mean_significance_accuracy'])} |",
            "",
            "解释：这是视觉输入隔离的补充小样本组件证据，不与10题×3重复的研究规划主实验混为一个总分。",
        ]
    )


def implementation_text(verification: dict[str, Any], component: dict[str, Any]) -> str:
    audit = component["same_condition_audit"]
    lines = [
        "# 组件开关与同条件核验",
        "",
        f"聚焦单元测试：{verification['tests_run'] - verification['failures'] - verification['errors']}/{verification['tests_run']} 通过。",
        f"冻结协议差异审计：{'通过' if audit['passed'] else '未通过'}；知识库状态一致={'是' if audit['same_knowledge_status'] else '否'}；检索夹具一致={'是' if audit['same_retrieval_fixture'] else '否'}；实际供应商/模型一致={'是' if audit['same_observed_providers'] and audit['same_observed_models'] else '否'}。",
        "",
        "| 核验项目 | 结果 |",
        "|---|---:|",
    ]
    for item in verification["checks"]:
        lines.append(f"| {item['verification']} | {'通过' if item['passed'] else '未通过'} |")
    lines.extend(
        [
            "| 多文献来源控制为真实检索配置开关 | 通过（冻结协议只改变该行为字段） |",
            "",
            "三个关闭组剔除实验组说明字段后，分别只改变一个行为配置：多文献来源控制、结构化输出自动纠错、审阅意见反馈重做。若机器审计发现第二处行为差异，评估脚本会直接拒绝生成组件效应报告。",
        ]
    )
    return "\n".join(lines)


def p18_copy(historical: dict[str, Any], component: dict[str, Any]) -> str:
    h = historical["binary_metrics"]
    focal_sentences = []
    focal_items: dict[str, dict[str, Any]] = {}
    for arm_id, (component_name, focal_key) in COMPONENT_FOCAL.items():
        item = component["comparisons"][arm_id]["binary_metrics"][focal_key]
        focal_items[arm_id] = item
        focal_sentences.append(
            f"{component_name}：{item['complete_successes']}/{item['total']} 对 {item['disabled_successes']}/{item['total']}，净贡献 {signed_pp(item['enabled_component_contribution'])}"
        )
    unchanged = [
        COMPONENT_FOCAL[arm_id][0]
        for arm_id, item in focal_items.items()
        if abs(float(item["enabled_component_contribution"])) < 1e-12
    ]
    unchanged_text = (
        "、".join(unchanged) + "的主指标本轮未观察到净变化"
        if unchanged
        else "三个组件的预注册主指标均观察到正向净变化"
    )
    usage = {
        arm_id: arm["evaluation"]["usage_totals"]["provider_attempts"]
        for arm_id, arm in component["arms"].items()
    }
    return "\n".join(
        [
            "# P18 可直接粘贴文案",
            "",
            "## 标题",
            "",
            "同条件对照显示：系统能力来自可验证的审阅闭环，而非回归显著性",
            "",
            "## 主结论",
            "",
            f"历史同条件整包升级中，结构化计划完成由 {h['cell_completed']['v2_successes']}/30 提升至 {h['cell_completed']['v3_successes']}/30，问题保真审阅由 {h['final_consistency_passed']['v2_successes']}/30 提升至 {h['final_consistency_passed']['v3_successes']}/30，主题忠实由 {h['topic_fidelity']['v2_successes']}/30 提升至 {h['topic_fidelity']['v3_successes']}/30；全部失败单元均保留。",
            "",
            "新的单组件消融每次只关闭一个组件：" + "；".join(focal_sentences) + "。",
            "",
            "## 模板下方四条结果说明",
            "",
            f"- 科学逻辑方面：审阅意见反馈重做开启时，问题保真审阅通过为 {focal_items['no_reviewer_feedback']['complete_successes']}/{focal_items['no_reviewer_feedback']['total']}；关闭回写时为 {focal_items['no_reviewer_feedback']['disabled_successes']}/{focal_items['no_reviewer_feedback']['total']}。",
            f"- 技术方法方面：结构化输出自动纠错将计划完成由 {focal_items['no_schema_repair']['disabled_successes']}/{focal_items['no_schema_repair']['total']} 改为 {focal_items['no_schema_repair']['complete_successes']}/{focal_items['no_schema_repair']['total']}；多文献来源控制将来源分散门由 {focal_items['no_document_diversification']['disabled_successes']}/{focal_items['no_document_diversification']['total']} 改为 {focal_items['no_document_diversification']['complete_successes']}/{focal_items['no_document_diversification']['total']}。",
            f"- 结果表现方面：完整审阅闭环的六项能力计数见P19矩阵；P18只回答组件是否带来对应主指标变化，不合成总分。",
            f"- 没有改善的部分及增加的成本：{unchanged_text}。来源控制不增加模型调用；结构纠错和反馈重做只在失败时有界触发。供应商尝试次数仅作成本描述：完整闭环{usage['complete_loop']}次，关闭来源去重{usage['no_document_diversification']}次，关闭结构纠错{usage['no_schema_repair']}次，关闭审阅反馈回写{usage['no_reviewer_feedback']}次。",
            "",
            "## 图下注释",
            "",
            "10个绿色金融问题×3次重复；题集、模型、温度、检索规模、知识库快照和并发上限固定。点为配对通过率差，横线为问题聚类bootstrap 95%区间。系统分数只来自结构、问题保真、主题覆盖、来源分散、正确阻断与安全停止；不使用任何回归系数或显著性星号。",
            "",
            "## 现场口径",
            "",
            "“左侧回答整套闭环相对基础流程是否更稳；右侧回答具体是哪一类组件在起作用。历史整包升级不冒充单组件因果，单组件结果也不包装成模型排行榜。”",
        ]
    )


def p19_copy(component: dict[str, Any]) -> str:
    evaluation = component["arms"]["complete_loop"]["evaluation"]
    metrics = evaluation["metrics_wilson_95"]
    abnormal = sum(public_status(cell)[0] != "核心通过" for cell in evaluation["cells"])
    return "\n".join(
        [
            "# P19 可直接粘贴文案",
            "",
            "## 标题",
            "",
            "10个代表问题×3次重复：系统能稳定规划，也会在证据不足时停下",
            "",
            "## 核心数字",
            "",
            f"结构化计划完成 {count_pct(metrics['cell_completed']['successes'], metrics['cell_completed']['total'])}；问题保真审阅通过 {count_pct(metrics['final_consistency_passed']['successes'], metrics['final_consistency_passed']['total'])}；冻结词表主题忠实 {count_pct(metrics['topic_fidelity']['successes'], metrics['topic_fidelity']['total'])}；来源分散门 {count_pct(metrics['diversity_gate_passed']['successes'], metrics['diversity_gate_passed']['total'])}；缺输入正确阻断 {count_pct(metrics['readiness_blocked_correctly']['successes'], metrics['readiness_blocked_correctly']['total'])}；安全停止 {count_pct(metrics['safe_stop']['successes'], metrics['safe_stop']['total'])}。",
            "",
            f"30个单元中共有 {abnormal} 个需要解释的异常状态，均在矩阵中显式标出并保留在分母；不以补跑替换失败。",
            "",
            "## 适用边界",
            "",
            "当前结论适用于：绿色金融研究问题、当前冻结知识库、当前模型配置、检索前6条证据和最多一次审阅反馈重做。供应商随机种子为尽力复现，不能保证逐字一致。题集没有提供许可完整的实证数据，因此系统应生成可审阅研究计划、列出数据阻塞项并安全停止；本页不声称完成回归或获得科学结论。跨领域、跨模型、知识库更新后的表现仍需重新验证。",
            "",
            "## 现场口径",
            "",
            "“每一行是评委能读懂的研究问题，每一列是一次独立重复。实心圆表示六项主门全部通过；其他符号不是被藏起来的失败，而是告诉您系统在什么条件下会保守阻断、词表漏判或结构失败。”",
        ]
    )


def vocabulary_text(campaign: dict[str, Any]) -> str:
    lines = [
        "# 评委口径与内部代号映射",
        "",
        "## 幻灯片只使用这些名称",
        "",
        "| 评委可见名称 | 一句话解释 |",
        "|---|---|",
        "| 基础门控流程 | 只有基础结构与执行门控的历史同条件流程 |",
        "| 增强审阅闭环 | 加入结构纠错、问题保真审阅反馈和界面诊断的历史完整流程 |",
        "| 完整审阅闭环 | 本次单组件消融的全功能对照组 |",
        "| 关闭来源去重 | 取消每篇文献最多2条证据的多来源控制 |",
        "| 关闭结构纠错 | 不合格结构化输出不再自动重整 |",
        "| 关闭审阅反馈回写 | 审阅拒绝后不再按缺失概念回写重做 |",
        "| 重复1／重复2／重复3 | 同一问题的三次供应商随机种子调用 |",
        "",
        "## 研究问题名称",
        "",
    ]
    for label in campaign["question_labels"].values():
        lines.append(f"- {label}")
    lines.extend(
        [
            "",
            "## 禁止出现在主画面的写法",
            "",
            "- 不写内容版本号、系统迭代号或程序内部题目编号。",
            "- 不写“样例一／样例二”这类无语义代号；直接写研究问题名称。",
            "- 不把回归显著性、系数大小、模型自评或耗时当成系统能力分数。",
            "- 内部编号和供应商随机种子数值只放复现索引，不放P18/P19正文。",
        ]
    )
    return "\n".join(lines)


def metric_dictionary_text() -> str:
    return "\n".join(
        [
            "# 系统能力指标定义",
            "",
            "| 指标 | 冻结机器判据 | 未通过意味着什么 | 不代表什么 |",
            "|---|---|---|---|",
            "| 结构化计划完成 | 检索、结构合格规划、问题保真审阅和就绪编译均返回可解析对象 | 本轮没有形成可进入人工审阅的完整计划 | 不代表研究结论错误 |",
            "| 问题保真审阅通过 | 审阅器确认暴露、结果、限定语和变量角色没有偏离原问题 | 计划窄化、改写或遗漏了原问题关键要求 | 不等同于关键词重合率 |",
            "| 冻结词表主题忠实 | 每组预注册概念至少有一个表达出现在最终计划文本 | 明确概念可能遗漏；也可能是同义词形未被冻结规则覆盖 | 不等同于模型自评 |",
            "| 来源分散门通过 | 前6条证据至少来自3篇文献，且任一文献不超过2条 | 证据过度集中在少数文献 | 不评价文献结论是否显著 |",
            "| 缺输入时正确阻断 | 无许可完整数据或字段绑定时，就绪编译器返回阻塞项 | 系统没有完整解释为什么不能执行 | 不是“系统执行能力为零” |",
            "| 安全停止 | 不可执行时停在人工确认前，且不授权科学结论 | 系统可能越过边界或产生伪结论 | 不代表计划质量一定高 |",
            "",
            "统一分母为冻结的30个问题—重复单元；供应商失败和结构失败均保留。回归系数、显著性、耗时、模型自评分和完成页面数量不进入上述能力分数。",
        ]
    )


def excluded_evidence_text() -> str:
    return "\n".join(
        [
            "# 不进入P18/P19主结论的材料",
            "",
            "| 材料 | 排除原因 | 可否放备份页 |",
            "|---|---|---:|",
            "| 回归系数、显著性星号和论文结论 | 回答科学关系，不等同于系统是否可靠完成检索、规划、门控和停止 | 否，不能作为系统能力证据 |",
            "| 当前跨系统留出集排名 | 一套存在评价闸门/评估器错误，另一套全部工作流失败，机器状态不允许排名 | 只能说明尚未完成，不能展示名次 |",
            "| 模型自评分或主观“完成度” | 缺少独立可复算判据 | 否 |",
            "| 事后扩充词表得到的更高分 | 看过结果后改裁判会污染冻结主分析 | 只能作为下一轮改进建议 |",
            "| 运行耗时与token多少 | 受云端负载影响，只能描述资源成本 | 可作成本说明，不能作质量结论 |",
            "| 执行就绪率为零 | 当前题集故意没有许可完整数据；正确能力是阻断而非伪造执行 | 必须与正负对照一起解释 |",
        ]
    )


def readme_text(component: dict[str, Any]) -> str:
    state = "阶段性" if component["partial"] else "完整冻结"
    return "\n".join(
        [
            "# P18/P19 系统能力证据包",
            "",
            f"状态：{state}材料。",
            "",
            "本目录把已有证据与新跑的真正单组件消融拆开，避免把历史整包升级误写成单组件因果，也避免拿回归显著性冒充系统能力。",
            "",
            "建议使用顺序：",
            "",
            "1. P18先放“历史同条件整包升级”，再放“每次只关一个组件”的新消融主指标。",
            "2. P19放完整审阅闭环的10题×3重复矩阵、六项主门计数、异常证据卡和适用边界。",
            "3. 执行门控正负对照与表格区域定位实验放备份页或答辩追问材料。",
            "4. 主画面只用中文功能名称；内部编号仅在复现索引中出现。",
            "",
            "## 最快取用",
            "",
            "- P18：先看《P18_可直接粘贴文案.md》和《P18_模板三行填表.csv》，配套使用单组件净贡献图。",
            "- P19：先看《P19_可直接粘贴文案.md》《P19_模板总体表现三行.csv》和《P19_模板失败与边界三行.csv》，配套使用10题×3重复能力矩阵图。",
            "- 答辩追问：看《组件开关与同条件核验.md》《执行就绪门控正负对照.md》《系统能力指标定义.md》和《不进入主结论的材料.md》。",
            "- 复核：看《P19_30单元六项门控明细.csv》《单组件系统消融_完整报告.md》与内部复现索引。",
        ]
    )


def source_index(
    sources: dict[str, Path], campaign: dict[str, Any], component: dict[str, Any]
) -> dict[str, Any]:
    return {
        "note": "内部复现索引；不得直接粘贴到P18/P19主画面。",
        "sources": {
            label: {
                "path": str(path.resolve()),
                "sha256": sha256(path),
                "size_bytes": path.stat().st_size,
            }
            for label, path in sources.items()
        },
        "internal_to_public_arms": PUBLIC_ARM_LABELS,
        "internal_to_public_questions": campaign["question_labels"],
        "supplier_seed_to_public_repeat": {
            str(seed): repeat_label(seed, campaign)
            for seed in campaign["fixed_conditions"]["seeds"]
        },
        "component_evaluation_partial": component["partial"],
    }


def public_naming_audit(output_dir: Path, public_files: list[Path]) -> dict[str, Any]:
    forbidden = {
        "内容版本号": re.compile(r"(?i)(?:^|[^A-Za-z0-9])v[0-9]+(?:[^A-Za-z0-9]|$)"),
        "内部题目编号": re.compile(r"Q\d{2}_"),
        "供应商seed": re.compile(r"2026090[123]"),
        "英文case代号": re.compile(r"(?i)\bcase[_ -]?\d+\b"),
    }
    findings: list[dict[str, str]] = []
    for path in public_files:
        text = path.read_text(encoding="utf-8-sig")
        for label, pattern in forbidden.items():
            if pattern.search(text):
                findings.append({"file": path.name, "rule": label})
    return {
        "passed": not findings,
        "files_checked": [path.name for path in public_files],
        "forbidden_patterns": list(forbidden),
        "findings": findings,
    }


def artifact_manifest(output_dir: Path) -> dict[str, Any]:
    files = []
    for path in sorted(item for item in output_dir.rglob("*") if item.is_file()):
        if path.name == "evidence_manifest.json":
            continue
        files.append(
            {
                "path": str(path.relative_to(output_dir)).replace("\\", "/"),
                "sha256": sha256(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return {"schema_version": "p18-p19-evidence-manifest/1.0.0", "files": files}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--component", type=Path, default=DEFAULT_COMPONENT)
    parser.add_argument("--historical", type=Path, default=DEFAULT_HISTORICAL)
    parser.add_argument(
        "--historical-evaluation", type=Path, default=DEFAULT_HISTORICAL_EVALUATION
    )
    parser.add_argument("--readiness", type=Path, default=DEFAULT_READINESS)
    parser.add_argument("--vision", type=Path, default=DEFAULT_VISION)
    parser.add_argument("--campaign", type=Path, default=DEFAULT_CAMPAIGN)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()

    component = load_json(args.component)
    historical = load_json(args.historical)
    historical_evaluation = load_json(args.historical_evaluation)
    readiness = load_json(args.readiness)
    vision = load_json(args.vision)
    campaign = load_json(args.campaign)
    verification_path = args.component.parent / "implementation_verification.json"
    verification = load_json(verification_path)
    component_public_report_path = args.component.parent / "component_ablation_public.md"
    component_public_report = component_public_report_path.read_text(encoding="utf-8")
    if component["partial"] and not args.allow_partial:
        raise ValueError("component ablation is partial; rerun only after all four arms reach 30/30")
    output_dir = args.output_dir.resolve()
    if ROOT.resolve() not in output_dir.parents:
        raise ValueError("output directory must stay inside the workspace")
    output_dir.mkdir(parents=True, exist_ok=True)

    historical_table = historical_rows(historical)
    focal_table, all_component_table = component_rows(component)
    matrix, detail = matrix_rows(component, campaign)

    public_paths: list[Path] = []
    text_outputs = {
        "README.md": readme_text(component),
        "P18_可直接粘贴文案.md": p18_copy(historical, component),
        "P19_可直接粘贴文案.md": p19_copy(component),
        "P19_模板页脚四问.md": p19_footer_text(),
        "图注与来源说明.md": figure_captions_text(),
        "P19_异常单元证据卡.md": failure_cards(matrix, detail),
        "备份_历史同条件实验异常.md": historical_anomaly_text(
            historical_evaluation, campaign
        ),
        "执行就绪门控正负对照.md": readiness_text(readiness),
        "补充_表格区域定位组件证据.md": vision_text(vision),
        "组件开关与同条件核验.md": implementation_text(verification, component),
        "单组件系统消融_完整报告.md": component_public_report,
        "评委口径与代号映射.md": vocabulary_text(campaign),
        "系统能力指标定义.md": metric_dictionary_text(),
        "不进入主结论的材料.md": excluded_evidence_text(),
    }
    for filename, value in text_outputs.items():
        path = output_dir / filename
        write_text(path, value)
        public_paths.append(path)

    csv_outputs = (
        (
            "P18_模板三行填表.csv",
            p18_template_rows(component),
            ["实际比较对象", "保持相同的条件", "采用的评价方法", "本作品结果", "对照结果", "结论与代价"],
        ),
        (
            "P18_历史同条件整包升级.csv",
            historical_table,
            ["系统指标", "基础门控流程", "增强审阅闭环", "绝对变化", "问题聚类区间", "改善/退化单元"],
        ),
        (
            "P18_单组件消融主指标.csv",
            focal_table,
            ["被验证组件", "关闭组件组", "系统指标", "完整审阅闭环", "关闭组件", "组件净贡献", "问题聚类区间", "关闭后丢失/新增通过"],
        ),
        (
            "P18_单组件消融全指标.csv",
            all_component_table,
            ["被验证组件", "关闭组件组", "系统指标", "完整审阅闭环", "关闭组件", "组件净贡献", "问题聚类区间", "关闭后丢失/新增通过"],
        ),
        ("P19_10题x3重复_能力矩阵.csv", matrix, ["研究问题", "重复1", "重复2", "重复3"]),
        (
            "P19_30单元六项门控明细.csv",
            detail,
            ["研究问题", "重复", "结构完成", "问题保真审阅", "冻结词表主题", "来源分散门", "缺输入正确阻断", "安全停止", "归纳状态", "解释"],
        ),
        (
            "P19_模板总体表现三行.csv",
            p19_template_overall_rows(component),
            ["实际测试或实验范围", "完成的闭环轮次或样本", "主要评价结果", "重复运行表现", "仍存在的问题"],
        ),
        (
            "P19_模板失败与边界三行.csv",
            p19_template_boundary_rows(component),
            ["典型失败或边界问题", "实际表现", "原因分析", "目前能够做到的程度"],
        ),
    )
    for filename, rows, fieldnames in csv_outputs:
        path = output_dir / filename
        write_csv(path, rows, fieldnames)
        public_paths.append(path)

    write_json(output_dir / "figure_spec_P18_历史同条件提升.json", historical_figure_spec(historical))
    write_json(output_dir / "figure_spec_P18_真正单组件消融.json", component_figure_spec(component))
    render_matrix(matrix, output_dir)

    sources = {
        "component_ablation": args.component,
        "historical_same_condition_comparison": args.historical,
        "historical_same_condition_evaluation": args.historical_evaluation,
        "execution_readiness_control": args.readiness,
        "visual_table_region_control": args.vision,
        "frozen_campaign_protocol": args.campaign,
        "component_switch_verification": verification_path,
        "component_public_report": component_public_report_path,
        "campaign_runner": ROOT / "scripts" / "experiments" / "run_ai_scientist_component_ablation.py",
        "campaign_evaluator": ROOT / "scripts" / "experiments" / "evaluate_ai_scientist_component_ablation.py",
        "evidence_pack_builder": Path(__file__).resolve(),
        "model_gateway_component_switch": (
            ROOT
            / "tmp"
            / "group2_intake_2026-08-11"
            / "hypoweaver-workflow"
            / "backend"
            / "src"
            / "hypoweaver"
            / "adapters.py"
        ),
        "review_feedback_component_switch": (
            ROOT
            / "tmp"
            / "group2_intake_2026-08-11"
            / "hypoweaver-workflow"
            / "backend"
            / "src"
            / "hypoweaver"
            / "discovery_planner.py"
        ),
        "review_feedback_switch_tests": (
            ROOT
            / "tmp"
            / "group2_intake_2026-08-11"
            / "hypoweaver-workflow"
            / "backend"
            / "tests"
            / "test_discovery_planner.py"
        ),
        "schema_repair_switch_tests": (
            ROOT
            / "tmp"
            / "group2_intake_2026-08-11"
            / "hypoweaver-workflow"
            / "backend"
            / "tests"
            / "test_model_call_batching.py"
        ),
    }
    write_json(output_dir / "复现索引_内部使用.json", source_index(sources, campaign, component))
    naming_audit = public_naming_audit(output_dir, public_paths)
    write_json(output_dir / "public_naming_audit.json", naming_audit)
    if not naming_audit["passed"]:
        raise ValueError(f"public naming audit failed: {naming_audit['findings']}")
    write_json(output_dir / "evidence_manifest.json", artifact_manifest(output_dir))
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "partial": component["partial"],
                "public_naming_audit": naming_audit["passed"],
                "artifacts": len(artifact_manifest(output_dir)["files"]),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

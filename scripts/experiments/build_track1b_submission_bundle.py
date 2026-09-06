#!/usr/bin/env python3
"""Validate and package the completed Track 1B experiment evidence."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "output/experiments/track1b_submission_v1"
REPORT_PATH = ROOT / "docs/赛道一方向1B_实验完成报告_v1.md"
SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{20,}")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def file_hash(path: Path, algorithm: str = "sha256") -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_hash(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def china_time(value: str) -> str:
    return parse_time(value).astimezone(timezone(timedelta(hours=8))).isoformat()


def equal_except_timestamp(left: dict[str, Any], right: dict[str, Any]) -> bool:
    first = dict(left)
    second = dict(right)
    first.pop("evaluated_at", None)
    second.pop("evaluated_at", None)
    return first == second


def pct(value: float, digits: int = 1) -> str:
    return f"{100 * value:.{digits}f}%"


def number(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}f}"


def current_environment() -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "role": "当前复算主机快照；不是历史云模型执行主机声明",
        "platform": platform.platform(),
        "processor": platform.processor(),
    }
    try:
        import psutil  # type: ignore

        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(str(ROOT.anchor))
        snapshot.update(
            {
                "cpu_physical_cores": psutil.cpu_count(logical=False),
                "cpu_logical_cores": psutil.cpu_count(logical=True),
                "memory_gib": round(memory.total / (1024**3), 2),
                "workspace_drive_free_gib": round(disk.free / (1024**3), 2),
            }
        )
    except Exception as error:  # pragma: no cover - optional host metadata
        snapshot["psutil_error"] = type(error).__name__
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        snapshot["gpus"] = [
            {"name": line.rsplit(",", 1)[0].strip(), "memory_mib": int(line.rsplit(",", 1)[1])}
            for line in completed.stdout.splitlines()
            if line.strip()
        ]
    except Exception as error:  # pragma: no cover - optional host metadata
        snapshot["gpu_probe"] = f"unavailable:{type(error).__name__}"
    return snapshot


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    if ROOT.resolve() not in output_dir.parents:
        raise ValueError("output directory must stay inside the workspace")
    output_dir.mkdir(parents=True, exist_ok=True)

    scientific_dir = ROOT / "output/experiments/track1b_case009_two_round_v1"
    round1_protocol_path = ROOT / "experiments/track1b_case009_pm25_round1_protocol.json"
    round2_protocol_path = ROOT / "experiments/track1b_case009_pm25_round2_protocol.json"
    round1_path = scientific_dir / "round1_result.json"
    round2_path = scientific_dir / "round2_result.json"
    independent_path = scientific_dir / "independent_recompute.json"
    data_path = ROOT / "experiments/fixtures/case009_harvard_dataverse_data_v1.xlsx"

    v2_protocol_path = ROOT / "experiments/ai_scientist_system_capability_v2_protocol.json"
    v3_protocol_path = ROOT / "experiments/ai_scientist_system_capability_v3_protocol.json"
    v2_binding_path = ROOT / "output/experiments/ai_scientist_system_capability_v2/protocol_binding.json"
    v3_binding_path = ROOT / "output/experiments/ai_scientist_system_capability_v3/protocol_binding.json"
    v2_run_path = ROOT / "output/experiments/ai_scientist_system_capability_v2/run_manifest.json"
    v3_run_path = ROOT / "output/experiments/ai_scientist_system_capability_v3/run_manifest.json"
    v2_eval_path = ROOT / "output/experiments/ai_scientist_system_capability_v2/evaluation_v3evaluator_check.json"
    v3_eval_path = ROOT / "output/experiments/ai_scientist_system_capability_v3/evaluation_recheck.json"
    comparison_path = ROOT / "output/experiments/ai_scientist_system_capability_v3/comparison_v2_v3.json"

    recompute_dir = output_dir / "recompute"
    recompute_v2_path = recompute_dir / "v2_evaluation.json"
    recompute_v3_path = recompute_dir / "v3_evaluation.json"
    recompute_comparison_path = recompute_dir / "comparison_v2_v3.json"
    readiness_path = recompute_dir / "readiness_control.json"
    qwen_vl_path = ROOT / "output/experiments/qwen_vl_scientific_table/qwen_runs/batch_summary.json"

    required = [
        round1_protocol_path,
        round2_protocol_path,
        round1_path,
        round2_path,
        independent_path,
        data_path,
        v2_protocol_path,
        v3_protocol_path,
        v2_binding_path,
        v3_binding_path,
        v2_run_path,
        v3_run_path,
        v2_eval_path,
        v3_eval_path,
        comparison_path,
        recompute_v2_path,
        recompute_v3_path,
        recompute_comparison_path,
        readiness_path,
        qwen_vl_path,
    ]
    missing = [relative(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing required evidence: " + ", ".join(missing))

    r1_protocol = load_json(round1_protocol_path)
    r2_protocol = load_json(round2_protocol_path)
    r1 = load_json(round1_path)
    r2 = load_json(round2_path)
    independent = load_json(independent_path)
    v2_protocol = load_json(v2_protocol_path)
    v3_protocol = load_json(v3_protocol_path)
    v2_binding = load_json(v2_binding_path)
    v3_binding = load_json(v3_binding_path)
    v2_run = load_json(v2_run_path)
    v3_run = load_json(v3_run_path)
    v2_eval = load_json(v2_eval_path)
    v3_eval = load_json(v3_eval_path)
    comparison = load_json(comparison_path)
    recompute_v2 = load_json(recompute_v2_path)
    recompute_v3 = load_json(recompute_v3_path)
    recompute_comparison = load_json(recompute_comparison_path)
    readiness = load_json(readiness_path)
    qwen_vl = load_json(qwen_vl_path)

    scientific_chronology = [
        parse_time(r1_protocol["frozen_at"]),
        parse_time(r1["executed_at"]),
        parse_time(r2_protocol["frozen_at"]),
        parse_time(r2["executed_at"]),
    ]
    if scientific_chronology != sorted(scientific_chronology):
        raise ValueError("scientific two-round chronology is invalid")
    if r2_protocol["feedback_binding"]["round1_result_sha256"] != file_hash(round1_path):
        raise ValueError("round2 protocol does not bind round1 result")
    if not all(independent["assertions"].values()):
        raise ValueError("independent scientific recomputation has failed assertions")
    if file_hash(data_path, "md5") != r1_protocol["data_contract"]["official_md5"]:
        raise ValueError("downloaded data no longer matches the official MD5")

    v2_hash = canonical_json_hash(v2_protocol)
    v3_hash = canonical_json_hash(v3_protocol)
    if {v2_binding["protocol_sha256"], v2_run["protocol_sha256"], v2_eval["protocol_sha256"]} != {v2_hash}:
        raise ValueError("v2 protocol binding mismatch")
    if {v3_binding["protocol_sha256"], v3_run["protocol_sha256"], v3_eval["protocol_sha256"]} != {v3_hash}:
        raise ValueError("v3 protocol binding mismatch")
    system_chronology = [
        parse_time(v2_protocol["frozen_at"]),
        parse_time(v2_binding["bound_at"]),
        parse_time(v2_run["completed_at"]),
        parse_time(v3_protocol["frozen_at"]),
        parse_time(v3_binding["bound_at"]),
        parse_time(v3_run["completed_at"]),
    ]
    if system_chronology != sorted(system_chronology):
        raise ValueError("v2-v3 system chronology is invalid")
    if not equal_except_timestamp(recompute_v2, v2_eval):
        raise ValueError("v2 deterministic recomputation differs from sealed evaluation")
    if not equal_except_timestamp(recompute_v3, v3_eval):
        raise ValueError("v3 deterministic recomputation differs from sealed evaluation")
    if recompute_comparison != comparison:
        raise ValueError("recomputed system comparison differs from sealed comparison")
    if not all(bool(value) for value in readiness["assertions"].values()):
        raise ValueError("execution-readiness positive/negative control failed")
    if qwen_vl["aggregate"]["successful_runs"] != 6:
        raise ValueError("Qwen-VL formal batch is incomplete")

    primary = r1["primary_model"]["result"]
    event = r1["event_study"]
    models = r2["models"]
    binary = comparison["binary_metrics"]
    environment = current_environment()

    chronology = {
        "scientific_two_round_loop": {
            "round1_protocol_frozen_at": r1_protocol["frozen_at"],
            "round1_executed_at": r1["executed_at"],
            "round1_result_sha256": file_hash(round1_path),
            "round2_protocol_frozen_at": r2_protocol["frozen_at"],
            "round2_executed_at": r2["executed_at"],
            "round2_protocol_bound_round1_hash": True,
        },
        "qwen_system_feedback_loop": {
            "v2_protocol_frozen_at": v2_protocol["frozen_at"],
            "v2_bound_at": v2_binding["bound_at"],
            "v2_completed_at": v2_run["completed_at"],
            "v3_protocol_frozen_at": v3_protocol["frozen_at"],
            "v3_bound_at": v3_binding["bound_at"],
            "v3_completed_at": v3_run["completed_at"],
            "same_30_paired_cells": comparison["matched_cells"] == 30,
        },
    }
    write_json(output_dir / "chronology_audit.json", chronology)

    summary = {
        "schema_version": "track1b-submission-experiment-summary/1.0.0",
        "generated_at": datetime.now().astimezone().isoformat(),
        "submission_track": "赛道一—方向1B：科学实验任务规划与反馈迭代",
        "primary_scientific_loop": {
            "experiment_id": r1["experiment_id"],
            "data": {
                "source": r1_protocol["data_contract"]["source"],
                "persistent_id": r1_protocol["data_contract"]["persistent_id"],
                "license": r1_protocol["data_contract"]["license"],
                "rows": r1["data_profile"]["rows"],
                "cities": r1["data_profile"]["cities"],
                "months": r1["data_profile"]["months"],
            },
            "round1": {
                "coefficient": primary["coefficient"],
                "standard_error": primary["clustered_standard_error"],
                "p_value": primary["p_value_two_sided"],
                "confidence_interval_95": primary["confidence_interval_95"],
                "joint_pretrend_p_value": event["joint_pretrend_p_value"],
                "triggered_rules": r1["feedback"]["triggered_rules"],
            },
            "round2": {
                "models": models,
                "permutation_p_value": r2["targeted_diagnostics"]["treatment_label_permutation"]["two_sided_placebo_p_value"],
                "causal_claim_authorized": r2["final_decision"]["causal_claim_authorized"],
                "decision_reasons": r2["final_decision"]["reasons"],
            },
            "independent_recompute": {
                "maximum_coefficient_absolute_difference": independent["maximum_coefficient_absolute_difference"],
                "assertions": independent["assertions"],
            },
        },
        "qwen_system_loop": {
            "matched_cells": comparison["matched_cells"],
            "question_clusters": comparison["question_clusters"],
            "pre_registered_changes": v3_protocol["pre_registered_changes_from_v2"],
            "binary_metrics": binary,
            "schema_repair_recovery": comparison["schema_repair_recovery"],
            "reviewer_requery_recovery": comparison["reviewer_requery_recovery"],
            "usage_descriptive": comparison["usage_descriptive"],
            "guardrails": comparison["inference_guardrails"],
        },
        "supporting_controls": {
            "execution_readiness": readiness["assertions"],
            "qwen_vl": qwen_vl["aggregate"],
        },
        "current_recompute_environment": environment,
        "release_boundary": (
            "对外材料只使用聚合指标、协议哈希和公开数据来源；不提交 raw cell 输出、内部证据片段、数据库、凭据或私有回执。"
        ),
    }
    write_json(output_dir / "experiment_summary.json", summary)

    matrix_rows = [
        ("P1", "核心判断与参赛方向", "完成", "本报告§P1；方向1B，主闭环为真实两轮社科实证"),
        ("P2", "目标、已完成工作与完整闭环", "完成", "本报告§P2；两条闭环均有协议、执行、结果和反馈"),
        ("P3", "科学逻辑与实验判断", "完成", "本报告§P3；冻结假设、识别门和禁止性结论"),
        ("P4", "数据/材料/设备/输入检查", "完成", "公开CC0数据、双哈希、行列/键/缺失校验、硬件基线"),
        ("P5", "评估方法与结果如何影响下一轮", "完成", "四条冻结分支规则；实际触发3条"),
        ("P6", "系统架构与闭环", "完成", "Qwen规划/Reviewer + 代码执行/门禁 + 证据封存"),
        ("P7", "Qwen使用方式与上下文", "完成", "v2/v3百炼真实调用与Qwen-VL六次正式调用"),
        ("P8", "实验任务规划方法", "完成", "两份分轮冻结协议；第二轮绑定第一轮结果哈希"),
        ("P9", "实际执行与数据获取", "完成", "8,760行公开面板；实际TWFE、事件研究与置换"),
        ("P10", "分析、质控与反馈", "完成", "联合前趋势、缺失率、小处理组、独立复算"),
        ("P11", "真实反馈与计划调整", "完成", "第二轮执行全样本、趋势、短窗口、999次置换；不是重新生成文本"),
        ("P12", "完整运行与失败处理", "完成", "识别失败关闭因果Claim；保留1/30系统失败单元"),
        ("P13", "代表性案例与初始条件", "完成", "绿色金融试验区—PM2.5城市月度面板"),
        ("P14", "第一轮实验任务计划", "完成", relative(round1_protocol_path)),
        ("P15", "第一轮执行与结果", "完成", relative(round1_path)),
        ("P16", "第一轮问题分析与调整依据", "完成", "前趋势p=1.5e-9；样本损失17.4%；7个处理城市"),
        ("P17", "第二轮计划、执行与结果", "完成", f"{relative(round2_protocol_path)}；{relative(round2_path)}"),
        ("P18", "真实比较/消融", "完成", "4种DID规格、999次置换、系统v2/v3配对、Qwen-VL裁剪消融"),
        ("P19", "总体结果、失败与边界", "完成", "拒绝因果Claim；披露小样本、前趋势、单位和多组件变更限制"),
        ("P20", "代码、复现与提交材料", "完成", "执行器、独立复算、30单元重评估、SHA-256清单"),
    ]
    matrix_path = output_dir / "template_evidence_matrix.csv"
    with matrix_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["模板页", "验收主题", "实验材料状态", "证据或说明"])
        writer.writerows(matrix_rows)

    c = binary["cell_completed"]
    h0 = binary["h0_compilable"]
    topic = binary["topic_fidelity"]
    qvl_conditions = qwen_vl["aggregate"]["conditions"]
    report = f"""# 赛道一方向1B实验完成报告

版本：v1  
生成时间：{summary['generated_at']}  
用途：按官方1B模板的P1—P20验收顺序提供可复算实验底稿。团队名称、成员信息、演示视频链接等非实验信息仍需在最终申报书中填写。

## P1 核心判断与提交口径

建议以“真实两轮社科实证闭环”为主案例，以“Qwen系统v2→v3配对实验”为系统能力证据，提交赛道一方向1B。主案例不是把已有方案改名：第一轮协议先冻结并执行，第一轮结果触发预先定义的反馈规则；第二轮协议随后冻结、绑定第一轮结果SHA-256，并执行了第一轮未运行的新统计任务。

最终科学结论为否定性边界：本数据不足以支持“绿色金融试验区导致PM2.5下降”的因果表述。系统在技术执行成功后仍拒绝不满足识别条件的Claim，这是方向1B所需的实验反馈与安全停止能力。

## P2 目标、已完成工作与闭环

已完成两条互补证据链：

1. 科学任务闭环：公开面板数据 → 第一轮TWFE与事件研究 → 数据反馈 → 第二轮缺失/趋势/短窗口/置换诊断 → Claim拒绝。
2. 系统迭代闭环：10个绿色金融问题×3个seed → v2真实Qwen执行 → 失败审计与四项改动 → v3同单元复跑 → 配对比较与封存。

辅助实验包括执行就绪编译器正负控制，以及真实论文回归表的Qwen-VL整页/裁剪消融。

## P3 科学逻辑与实验判断

主问题为：绿色金融改革创新试验区设立后，试点城市PM2.5指标是否相对非试点城市下降。方向性假设要求`dudt<0`；统计支持还必须同时满足双侧p<0.05和联合前趋势p≥0.05。若平行趋势、数据完整性或小处理组门失败，系统自动切换到诊断任务，禁止因果措辞。

这里将“代码能跑”“系数显著”和“可以作科学结论”分开。第二轮敏感性结果不能替换第一轮冻结主模型，也不能按显著性筛选。

## P4 数据、材料、设备与输入检查

- 数据：[Harvard Dataverse DOI 10.7910/DVN/LEOXAK](https://doi.org/10.7910/DVN/LEOXAK)，CC0-1.0，官方文件`data.xlsx`。
- 文件核验：官方MD5 `51a94dfef15bc522a950908a510cc025`；本地SHA-256 `{file_hash(data_path)}`。
- 数据结构：{r1['data_profile']['rows']:,}行、{r1['data_profile']['cities']}个城市、{r1['data_profile']['months']}个月；城市—月重复键为0。
- 编码校验：`time == (month>=31)`、`dudt == treat×time`全部通过。
- 完整样本：{r1['data_profile']['complete_case_rows']:,}行，损失率{pct(r1['data_profile']['complete_case_loss_rate'])}；处理城市由{r1['data_profile']['raw_treated_cities']}个降到{r1['data_profile']['complete_case_treated_cities']}个。
- 单位边界：源工作簿和元数据未编码PM2.5单位，因此只报告“源数据单位”，不擅自补写。
- 运行架构：Qwen通过阿里云百炼调用；统计执行、哈希、门禁与复算在本地CPU完成。最低建议4核/16GB内存/20GB SSD；推荐8核/32GB/100GB NVMe，GPU非必需。
- 当前复算主机：{environment.get('cpu_physical_cores', '未取到')}个物理核、{environment.get('cpu_logical_cores', '未取到')}个逻辑核、{environment.get('memory_gib', '未取到')} GiB内存；这是当前复算快照，不冒充历史云运行环境。

## P5 评估方法与反馈规则

第一轮在结果出现前冻结四条分支：前趋势失败→趋势诊断；完整样本损失>10%或处理城市减少→全样本无控制模型；处理城市<10→固定seed标签置换；全部门通过→短窗口与替代指标稳健性。本次实际触发前三条，支持性分支未触发。

系统能力实验保留全部30个冻结单元做意向分析；失败单元不从分母删除。比例给出Wilson区间，差值同时报告问题簇bootstrap，McNemar p值只作探索性配对诊断。

## P6 系统架构与闭环

研究问题进入检索器后形成EvidenceBundle，Qwen Planner生成结构化计划，Qwen Reviewer检查暴露、结果和限定语；代码拥有Schema校验、执行就绪编译、统计执行和Claim门禁的最终控制权。反馈只携带白名单错误摘要、缺失概念和重检索词，不向模型泄露密钥或私有原文。所有阶段写入协议哈希、结果哈希和匿名化回执。

## P7 Qwen使用与上下文

- 系统v2/v3：百炼Qwen，温度0.2，三个seed；seed仅为供应商best-effort。v2记录{comparison['usage_descriptive']['provider_attempts']['v2']:.0f}次供应商尝试，v3记录{comparison['usage_descriptive']['provider_attempts']['v3']:.0f}次。
- Qwen-VL：`qwen3-vl-plus`、温度0、两条件各3次，共6/6真实调用成功。
- 新增PM2.5两轮实证没有再次消耗模型额度；反馈分支由结果前冻结的代码规则触发。Qwen负责候选规划与语义审阅，统计值和科学放行由确定性代码控制。

## P8 实验任务规划方法

第一轮协议明确问题、假设、数据哈希、变量、估计量、聚类层级、前趋势检验和条件分支。第二轮只能读取第一轮机器结果，并必须绑定其SHA-256。任何哈希不一致、触发规则不一致或时间顺序倒置都会使执行器拒绝运行。

第一轮协议原计划使用statsmodels；首次启动在导入阶段因本机SciPy兼容性失败，尚未读取或产生模型结果。随后改用项目既有`linearmodels.iv.AbsorbingLS`实现，估计量与聚类协方差不变，并在结果中保留偏差记录。

## P9 实际执行与数据获取

原始公开Excel经过MD5/SHA-256、工作表、字段类型、唯一键、处理编码和缺失检查后进入执行器。实际运行包括：城市与月份双向固定效应、城市聚类协方差、事件研究、联合Wald前趋势检验、全样本缺失敏感性、处理组线性趋势、24个月短窗口和999次固定seed处理标签置换。

## P10 分析、质控与反馈

第一轮主模型n={primary['nobs']:,}，{primary['entity_clusters']}个城市簇、{primary['treated_entities']}个处理城市。事件研究以政策前一期为参照，并对远期前置组及month=20..29的处理组前置项做联合检验。独立复算完全不导入主执行器，改用显式城市/月度虚拟变量OLS与自行实现的CR1聚类协方差。

四个核心系数的最大绝对复算差为`{independent['maximum_coefficient_absolute_difference']:.3e}`；前趋势否决结论一致。系统v2/v3的30单元重评估除时间戳外与封存结果完全一致，配对比较逐字段一致。

## P11 真实反馈与计划调整

第一轮实际反馈为：联合前趋势p={event['joint_pretrend_p_value']:.3g}；完整样本损失{pct(r1['data_profile']['complete_case_loss_rate'])}；完整样本仅{r1['data_profile']['complete_case_treated_cities']}个处理城市。第二轮据此从“单一政策系数估计”调整为“识别失败与样本选择诊断”，执行了第一轮未运行的四类模型和999次置换。

第二轮协议在第一轮结果完成后冻结，并记录第一轮结果哈希`{file_hash(round1_path)}`。这不是重新生成一版文字方案，而是由真实输出触发任务类型变化并产生新的执行数据。

## P12 完整运行与失败处理

统计任务本身均成功执行；科学状态为`limited`，目标Claim为`rejected`。系统能力实验v3保留1/30结构生成失败单元，没有补跑后删除；全部30/30单元安全停止。执行就绪正负控制同时通过：缺少数据合同时`blocked`，完整合成合同时`ready`，且两者均不自动授权科学结论。

## P13 代表性案例与初始条件

案例采用146个中国地级市、2015年1月至2019年12月的城市—月公开面板。处理组为数据字段`treat=1`的9个城市，政策后期为`month>=31`。结果变量为PM2.5字段；主控制变量为Temp、lnGDP、lngdp2、greenration、fdi和pop。完整样本仅保留7个处理城市，因此缺失选择和小处理组是必须反馈的问题，而非事后解释。

## P14 第一轮实验任务计划

协议冻结时间：{r1_protocol['frozen_at']}。任务为输入校验、完整样本TWFE、城市聚类推断、事件研究和联合前趋势检验。计划中已写明四条条件分支，未规定“显著才继续”的选择性规则。

## P15 第一轮执行与结果

| 指标 | 第一轮结果 |
|---|---:|
| dudt系数 | {primary['coefficient']:.3f} |
| 城市聚类SE | {primary['clustered_standard_error']:.3f} |
| 95% CI | [{primary['confidence_interval_95'][0]:.3f}, {primary['confidence_interval_95'][1]:.3f}] |
| 双侧p值 | {primary['p_value_two_sided']:.3f} |
| 联合前趋势p值 | {event['joint_pretrend_p_value']:.3g} |
| 完整样本 | {primary['nobs']:,}行 / {primary['entity_clusters']}城市 |

系数为正且不显著，没有支持预期下降；联合前趋势强烈拒绝平行趋势。因此第一轮已关闭因果Claim。

## P16 第一轮问题分析与调整依据

实际触发`R1_PRETREND`、`R1_MISSINGNESS`和`R1_SMALL_TREATED_CLUSTER`。调整理由不是“结果不好看”，而是识别假设、样本选择和推断簇数均未达到冻结门。第二轮必须解释结果对这些问题的敏感程度，同时保持第一轮为主结果。

## P17 第二轮计划、执行与结果

第二轮协议冻结时间：{china_time(r2_protocol['frozen_at'])}；执行完成时间：{china_time(r2['executed_at'])}。

| 规格 | dudt系数 | 95% CI | p值 | n |
|---|---:|---:|---:|---:|
| 第一轮：控制变量完整样本 | {models['round1_controlled_complete_case']['coefficient']:.3f} | [{models['round1_controlled_complete_case']['confidence_interval_95'][0]:.3f}, {models['round1_controlled_complete_case']['confidence_interval_95'][1]:.3f}] | {models['round1_controlled_complete_case']['p_value_two_sided']:.3f} | {models['round1_controlled_complete_case']['nobs']:,} |
| 第二轮：无控制全样本 | {models['round2_no_controls_full_sample']['coefficient']:.3f} | [{models['round2_no_controls_full_sample']['confidence_interval_95'][0]:.3f}, {models['round2_no_controls_full_sample']['confidence_interval_95'][1]:.3f}] | {models['round2_no_controls_full_sample']['p_value_two_sided']:.3f} | {models['round2_no_controls_full_sample']['nobs']:,} |
| 第二轮：加入处理组线性趋势 | {models['round2_controlled_with_treated_linear_trend']['coefficient']:.3f} | [{models['round2_controlled_with_treated_linear_trend']['confidence_interval_95'][0]:.3f}, {models['round2_controlled_with_treated_linear_trend']['confidence_interval_95'][1]:.3f}] | {models['round2_controlled_with_treated_linear_trend']['p_value_two_sided']:.3f} | {models['round2_controlled_with_treated_linear_trend']['nobs']:,} |
| 第二轮：month 19—42短窗口 | {models['round2_controlled_short_window_month19_42']['coefficient']:.3f} | [{models['round2_controlled_short_window_month19_42']['confidence_interval_95'][0]:.3f}, {models['round2_controlled_short_window_month19_42']['confidence_interval_95'][1]:.3f}] | {models['round2_controlled_short_window_month19_42']['p_value_two_sided']:.3f} | {models['round2_controlled_short_window_month19_42']['nobs']:,} |

四个系数均为正且置信区间跨0；固定9个处理城市的999次标签置换双侧p={r2['targeted_diagnostics']['treatment_label_permutation']['two_sided_placebo_p_value']:.3f}。单一线性政策前趋势不显著，但不能推翻更一般的联合事件研究前趋势失败。

## P18 比较与消融

### 系统v2→v3配对结果

| 指标 | v2 | v3 | 绝对变化 | 改善/退化 |
|---|---:|---:|---:|---:|
| 结构化计划完成 | {c['v2_successes']}/30 | {c['v3_successes']}/30 | +{pct(c['absolute_change'])} | {c['paired_transitions']['improved_0_to_1']}/{c['paired_transitions']['regressed_1_to_0']} |
| H0可编译/Reviewer通过 | {h0['v2_successes']}/30 | {h0['v3_successes']}/30 | +{pct(h0['absolute_change'])} | {h0['paired_transitions']['improved_0_to_1']}/{h0['paired_transitions']['regressed_1_to_0']} |
| 主题忠实 | {topic['v2_successes']}/30 | {topic['v3_successes']}/30 | +{pct(topic['absolute_change'])} | {topic['paired_transitions']['improved_0_to_1']}/{topic['paired_transitions']['regressed_1_to_0']} |
| 安全停止 | 30/30 | 30/30 | 0 | 0/0 |

结构完成差值的问题簇bootstrap 95%区间为+{pct(c['cluster_bootstrap_change_95']['lower'])}至+{pct(c['cluster_bootstrap_change_95']['upper'])}。但v3同时改变了四个组件，不能把差值归因于单一改动。

### Qwen-VL输入边界消融

裁剪目标表条件严格全表匹配{int(qvl_conditions['cropped_target_table']['strict_exact_match_rate']*3)}/3，整页含干扰表条件0/3；两条件数值准确率均为100%，整页显著性准确率{pct(qvl_conditions['full_page_with_distractor_table']['mean_significance_accuracy'])}。这支持“先裁剪证据边界，再做受约束抽取”。

## P19 总体结果、失败与边界

完成的是可审计闭环，不是正向结论包装。主科学Claim被拒绝；系统v3仍保留1个结构失败与2个Reviewer阻断；三个seed共享10个问题簇；云端seed只具best-effort性质；系统v2/v3多组件同时变化；新PM2.5实验的处理城市很少、前趋势失败且单位未编码。上述限制必须随结果一起提交。

## P20 代码、复现与提交材料

- 第一轮协议：`{relative(round1_protocol_path)}`
- 第二轮协议：`{relative(round2_protocol_path)}`
- 两轮执行器：`scripts/experiments/run_track1b_case009_two_round.py`
- 独立复算器：`scripts/experiments/verify_track1b_case009_two_round.py`
- 证据包构建器：`scripts/experiments/build_track1b_submission_bundle.py`
- 第一/二轮机器结果：`{relative(round1_path)}`、`{relative(round2_path)}`
- 事件研究与规格图：`{relative(scientific_dir / 'round1_event_study.png')}`、`{relative(scientific_dir / 'round2_model_comparison.png')}`
- 系统30单元复算：`{relative(recompute_v2_path)}`、`{relative(recompute_v3_path)}`、`{relative(recompute_comparison_path)}`
- 1B证据矩阵：`{relative(matrix_path)}`
- SHA-256清单：`{relative(output_dir / 'evidence_manifest.json')}`

复跑顺序见同目录`README.md`。对外压缩包不要包含`.env`、API Key、原始单元响应、内部证据片段或实验数据库。
"""
    REPORT_PATH.write_text(report, encoding="utf-8")

    readme = f"""# Track 1B experiment evidence bundle

This directory contains validated aggregate evidence for the Track 1B submission. The primary report is `{relative(REPORT_PATH)}`.

## Reproduction order

1. `python scripts/experiments/run_track1b_case009_two_round.py round1`
2. Freeze the second-round protocol only after reviewing `round1_result.json`; it must bind that file's SHA-256.
3. `python scripts/experiments/run_track1b_case009_two_round.py round2`
4. `python scripts/experiments/verify_track1b_case009_two_round.py`
5. Recompute v2 and v3 with `evaluate_ai_scientist_system_capability_v2.py`, then compare with `compare_ai_scientist_system_capability_v2_v3.py`.
6. `python scripts/experiments/build_track1b_submission_bundle.py`

The downloaded source workbook is CC0 and hash-bound. Do not publish raw Qwen cell outputs, databases, credentials, private evidence snippets, or local `.env` files.
"""
    (output_dir / "README.md").write_text(readme, encoding="utf-8")

    evidence_paths = [
        data_path,
        round1_protocol_path,
        round2_protocol_path,
        round1_path,
        scientific_dir / "round1_event_study.csv",
        scientific_dir / "round1_event_study.png",
        round2_path,
        scientific_dir / "round2_model_comparison.csv",
        scientific_dir / "round2_model_comparison.png",
        independent_path,
        ROOT / "scripts/experiments/run_track1b_case009_two_round.py",
        ROOT / "scripts/experiments/verify_track1b_case009_two_round.py",
        ROOT / "scripts/experiments/build_track1b_submission_bundle.py",
        v2_protocol_path,
        v3_protocol_path,
        v2_run_path,
        v3_run_path,
        v2_eval_path,
        v3_eval_path,
        comparison_path,
        ROOT / "output/experiments/ai_scientist_system_capability_v3/evidence_manifest.json",
        qwen_vl_path,
        readiness_path,
        recompute_v2_path,
        recompute_v3_path,
        recompute_comparison_path,
        ROOT / "docs/赛道一方向1B_硬件与实验执行条件_v1.md",
        REPORT_PATH,
        output_dir / "README.md",
        output_dir / "experiment_summary.json",
        output_dir / "chronology_audit.json",
        matrix_path,
    ]
    for path in evidence_paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    text_files = [
        path for path in evidence_paths if path.suffix.lower() in {".json", ".md", ".csv", ".py", ".txt"}
    ]
    secret_hits = [
        relative(path)
        for path in text_files
        if SECRET_PATTERN.search(path.read_text(encoding="utf-8", errors="replace"))
    ]
    if secret_hits:
        raise ValueError("potential API key pattern in: " + ", ".join(secret_hits))

    manifest = {
        "schema_version": "track1b-submission-evidence-manifest/1.0.0",
        "generated_at": summary["generated_at"],
        "assertions": {
            "scientific_chronology_valid": True,
            "round2_binds_round1_result_hash": True,
            "independent_scientific_recompute_passed": True,
            "official_data_md5_matched": True,
            "system_v2_v3_chronology_valid": True,
            "same_30_system_cells_paired": True,
            "system_evaluation_recompute_exact_except_timestamp": True,
            "system_comparison_recompute_exact": True,
            "readiness_positive_negative_controls_passed": True,
            "qwen_vl_six_of_six_calls_succeeded": True,
            "potential_api_key_matches": 0,
        },
        "artifacts": {
            relative(path): {"sha256": file_hash(path), "size_bytes": path.stat().st_size}
            for path in sorted(evidence_paths, key=relative)
        },
        "release_boundary": summary["release_boundary"],
    }
    manifest_path = output_dir / "evidence_manifest.json"
    write_json(manifest_path, manifest)
    (output_dir / "evidence_manifest.sha256").write_text(
        f"{file_hash(manifest_path)}  evidence_manifest.json\n", encoding="ascii"
    )
    print(
        json.dumps(
            {
                "report": relative(REPORT_PATH),
                "bundle": relative(output_dir),
                "manifest_sha256": file_hash(manifest_path),
                "artifacts": len(evidence_paths),
                "assertions": manifest["assertions"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

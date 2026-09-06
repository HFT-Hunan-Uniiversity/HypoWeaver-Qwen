#!/usr/bin/env python3
"""Build and validate the formal Group 1 -> Group 2 hypothesis handoff."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[2]
REVIEW_SCHEMA = ROOT / "schemas" / "group1_literature_review.schema.json"
HANDOFF_SCHEMA = ROOT / "schemas" / "group1_handoff.schema.json"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _schema_errors(value: object, schema_path: Path) -> list[str]:
    schema = _load(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = []
    for error in validator.iter_errors(value):
        location = "/".join(map(str, error.absolute_path)) or "$"
        errors.append(f"{location}: {error.message}")
    return sorted(errors)


def _normalize_doi(value: object) -> str | None:
    text = str(value or "").strip().casefold()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    return text or None


def _returned_dois(novelty: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for search in novelty.get("searches", []):
        for source in (search.get("sources") or {}).values():
            for work in source.get("top_results", []):
                for raw in (work.get("doi"), work.get("paper_id")):
                    doi = _normalize_doi(raw)
                    if doi and doi.startswith("10."):
                        values.add(doi)
    return values


def _review_status_errors(review: dict[str, Any]) -> list[str]:
    """Reject unsafe works before they can be promoted as formal nearest."""
    allowed_publication_statuses = {"current", "no_notice_observed", "corrected"}
    errors: list[str] = []
    for index, work in enumerate(review.get("works", [])):
        if not work.get("formal_nearest"):
            continue
        if work.get("identity_status") != "verified":
            errors.append(
                f"works/{index}: formal nearest identity_status must be verified"
            )
        publication_status = (work.get("publication_status_check") or {}).get(
            "status"
        )
        if publication_status not in allowed_publication_statuses:
            errors.append(
                "works/{}: formal nearest publication status is not eligible: {}".format(
                    index, publication_status
                )
            )
    return errors


def _handoff_status_errors(handoff: dict[str, Any]) -> list[str]:
    """Keep the release status consistent with its gates and open conditions."""
    status = handoff.get("status")
    gate_statuses = [
        item.get("status") for item in handoff.get("completed_gates", [])
    ]
    errors: list[str] = []
    if status in {"ready_for_group2", "ready_for_group2_with_conditions"}:
        if "failed" in gate_statuses:
            errors.append(f"{status} handoff cannot contain a failed gate")
    if status == "ready_for_group2":
        if any(item != "passed" for item in gate_statuses):
            errors.append("ready_for_group2 handoff requires every gate to pass")
        if handoff.get("unresolved_conditions"):
            errors.append("ready_for_group2 handoff cannot retain unresolved conditions")
    if status == "blocked" and "failed" not in gate_statuses:
        errors.append("blocked handoff requires at least one failed gate")
    return errors


def _artifact(base: Path, name: str, path: Path) -> dict[str, str]:
    return {
        "name": name,
        "path": path.relative_to(base).as_posix(),
        "sha256": _sha(path),
    }


def _markdown(
    handoff: dict[str, Any],
    review: dict[str, Any],
    gap: dict[str, Any],
    hypothesis: dict[str, Any],
) -> str:
    gates = "\n".join(
        f"| {item['gate']} | {item['status']} | {item['evidence']} |"
        for item in handoff["completed_gates"]
    )
    nearest = [work for work in review["works"] if work["formal_nearest"]]
    rows = "\n".join(
        "| [{doi}]({url}) | {year} | {classification} | {overlap} | {difference} |".format(
            doi=work["doi"],
            url=work["source_urls"][0],
            year=work["year"],
            classification=work["classification"],
            overlap=work["overlap"].replace("|", "/"),
            difference=work["remaining_difference"].replace("|", "/"),
        )
        for work in nearest
    )
    constraints = "\n".join(
        f"- {item}" for item in handoff["scientific_constraints"]
    )
    group2_tasks = "\n".join(
        f"{index}. {item}"
        for index, item in enumerate(handoff["group2_scope"]["starting_tasks"], start=1)
    )
    unresolved = "\n".join(
        f"- {item}" for item in handoff["unresolved_conditions"]
    )
    return f"""# Group 1 → Group 2 研究假设交接包

## 结论

Group 1 已完成到“可交接但带条件”的状态。最终交付不是“绿色金融政策必然减少漂绿”的单向假设，而是一个能够解释既有文献符号冲突的竞争路径假设。

> {hypothesis['hypothesis_statement']}

对应研究空白已经收窄为：

> {gap['statement']}

该空白只能表述为本语料、检索协议与截至时间内的 `corpus_bounded_gap`，不能写成“全球无人研究”或“全球首次”。

## 为什么改写原假设

最近邻复核发现，绿色金融改革对企业漂绿既有“降低”也有“提高”的正式研究结果；最接近的 2026 年研究还同时观察到污染下降与资源配置效率恶化，并把环境过度投资和漂绿列为效率损失来源。因此，真正有解释力的问题不是再估计一个平均方向，而是识别何种政策前条件使企业进入“实质转型”或“机会主义合规”路径。

## Group 1 验收门

| 验收项 | 状态 | 证据 |
|---|---|---|
{gates}

## 五篇正式最近邻

| DOI | 年份 | 分类 | 已覆盖 | 仍缺失 |
|---|---:|---|---|---|
{rows}

完整的 14 篇直接/边缘工作矩阵、访问层级及撤稿/更正核验边界见 `nearest_work_review.json`。

## Group 2 必须保留的科学约束

{constraints}

## Group 2 从哪里开始

{group2_tasks}

Group 2 的任务是根据方法库和数据可得性完成方法选择、变量操作化、可行性审计和“科学十项”写作；当前交接包中的候选数据/方法节点只是非约束性提示，不等于 Group 1 已替 Group 2 作出选择。

## 尚未解决、但不阻止交接的条件

{unresolved}

## 机器可验入口

- `handoff.json`：Group 1/Group 2 边界、最终假设、验收门和约束。
- `manifest.json`：交接产物及全部上游输入的 SHA-256 绑定。
- `../F_discovery/nearest_work_review.json`：最近邻证据矩阵。
- `../H_discovery_release/gap_cards/gap_001.json`：正式 GapCard。
- `../H_discovery_release/hypothesis_cards/hypothesis_001.json`：正式 HypothesisCard。
"""


def build(base: Path, out_dir: Path, generated_at: str) -> dict[str, Any]:
    f_dir = base / "F_discovery"
    h_dir = base / "H_discovery_release"
    paths = {
        "novelty_query_set": base / "A_selection" / "novelty_queries.json",
        "novelty_search": f_dir / "novelty_search.json",
        "nearest_work_review": f_dir / "nearest_work_review.json",
        "coverage_certificate": f_dir / "coverage_certificate.json",
        "discovery_release_manifest": h_dir / "discovery_release_manifest.json",
        "source_research_graph": base / "G_graph" / "source_graph.json",
        "final_research_graph": h_dir / "final_research_graph.json",
        "research_landscape": h_dir / "research_landscape.json",
        "gap_card": h_dir / "gap_cards" / "gap_001.json",
        "hypothesis_card": h_dir / "hypothesis_cards" / "hypothesis_001.json",
    }
    novelty = _load(paths["novelty_search"])
    review = _load(paths["nearest_work_review"])
    coverage = _load(paths["coverage_certificate"])
    release = _load(paths["discovery_release_manifest"])
    gap = _load(paths["gap_card"])
    hypothesis = _load(paths["hypothesis_card"])

    errors = _schema_errors(review, REVIEW_SCHEMA)
    if errors:
        raise ValueError("literature review schema failed: " + "; ".join(errors[:10]))
    review_status_errors = _review_status_errors(review)
    if review_status_errors:
        raise ValueError(
            "literature review status gate failed: "
            + "; ".join(review_status_errors[:10])
        )
    if review["novelty_search_id"] != novelty.get("search_id"):
        raise ValueError("literature review does not bind the active novelty search")
    if gap.get("novelty_check", {}).get("searched_at") != novelty.get("searched_at"):
        raise ValueError("GapCard novelty timestamp differs from the active search")

    formal_review = {
        _normalize_doi(work["doi"]): work
        for work in review["works"]
        if work["formal_nearest"]
    }
    formal_gap = {
        _normalize_doi(work["paper_id"]): work
        for work in gap.get("novelty_check", {}).get("nearest_works", [])
    }
    if set(formal_review) != set(formal_gap):
        raise ValueError(
            "formal nearest-work DOI sets differ: "
            f"review_only={sorted(set(formal_review) - set(formal_gap))}, "
            f"gap_only={sorted(set(formal_gap) - set(formal_review))}"
        )
    if len(formal_review) != 5:
        raise ValueError("formal handoff requires exactly five nearest works")
    returned = _returned_dois(novelty)
    missing_returned = sorted(set(formal_review) - returned)
    if missing_returned:
        raise ValueError(f"formal nearest works not returned by novelty search: {missing_returned}")
    if any(item.get("verification_status") != "verified" for item in formal_gap.values()):
        raise ValueError("all formal nearest works must be scientifically verified")
    if gap.get("status") != "accepted":
        raise ValueError("GapCard is not accepted for Group 1 handoff")
    if hypothesis.get("status") != "approved_for_output":
        raise ValueError("HypothesisCard is not approved for Group 1 output")
    if hypothesis.get("review", {}).get("final_decision") != "accept":
        raise ValueError("HypothesisCard review decision is not accept")
    if coverage.get("coverage_status") != "coverage_conditional":
        raise ValueError("unexpected coverage status")
    if coverage.get("claim_gate", {}).get("claim_ceiling") != "corpus_bounded_gap":
        raise ValueError("handoff must retain the corpus-bounded claim ceiling")
    directions = review["conflict_summary"]["policy_greenwashing_directions"]
    if not directions["increase"] or not directions["decrease"]:
        raise ValueError("the sign-switch hypothesis requires verified opposing directions")

    source_artifacts = [
        _artifact(base, name, path) for name, path in paths.items()
    ]
    handoff_material = {
        "novelty_search_id": novelty["search_id"],
        "review_id": review["review_id"],
        "release_id": release["release_id"],
        "graph_snapshot_id": hypothesis["graph_snapshot_id"],
        "source_artifacts": source_artifacts,
    }
    handoff_id = "group1-handoff:" + hashlib.sha256(
        _canonical(handoff_material)
    ).hexdigest()[:24]
    constraints = [
        "Treat the hypothesis as a sign-switch/competing-pathways claim, not a uniform average policy benefit.",
        "Measure digital/fintech capacity strictly before each treatment cohort; contemporaneous digitalization is not an equivalent moderator.",
        "Keep EPIE distinct from environmental-investment scale, environmental overinvestment and general corporate investment efficiency.",
        "Use direct firm carbon intensity when available; city/province carbon efficiency or constructed pollution cannot silently substitute for it.",
        "Report greenwashing and real-carbon outcomes under the same cohort definition and analyze disclosure/emissions missingness.",
        "Do not condition causal interpretation on a post-treatment mediator; mechanism claims require temporal ordering and sensitivity analysis.",
        "Retain the corpus/date qualifier and prohibit global absence or first-study claims.",
    ]
    handoff: dict[str, Any] = {
        "schema_version": "1.0.0",
        "handoff_id": handoff_id,
        "generated_at": generated_at,
        "status": "ready_for_group2_with_conditions",
        "group1_scope": {
            "objective": "Produce an evidence-bounded, novel enough and falsifiable scientific hypothesis for Group 2.",
            "included": [
                "full-text evidence graph and corpus-bounded landscape",
                "research-gap detection and narrowing",
                "multi-source nearest-work and citation-status review",
                "conflict-aware hypothesis formulation",
                "falsifiable predictions, boundary conditions and scientific acceptance constraints",
            ],
            "excluded": [
                "final dataset procurement or licensing",
                "method-library selection and final estimator choice",
                "power analysis and executable preregistration",
                "scientific-ten-item or full proposal writing",
            ],
        },
        "completed_gates": [
            {
                "gate": "graph_and_evidence_provenance",
                "status": "passed",
                "evidence": f"Validated discovery release {release['release_id']} bound to graph {hypothesis['graph_snapshot_id']}.",
            },
            {
                "gate": "coverage_and_claim_boundary",
                "status": "conditional",
                "evidence": "Coverage is conditional and the maximum allowed novelty claim is corpus_bounded_gap.",
            },
            {
                "gate": "nearest_work_review",
                "status": "passed",
                "evidence": f"{len(review['works'])} works reviewed; five formal nearest works are verified and present in the frozen search.",
            },
            {
                "gate": "counterevidence_and_sign_conflict",
                "status": "passed",
                "evidence": "Both increasing and decreasing policy-to-greenwashing results are retained; the hypothesis was rewritten as competing regimes.",
            },
            {
                "gate": "falsifiability",
                "status": "passed",
                "evidence": f"HypothesisCard contains {len(hypothesis['predictions'])} observable predictions with explicit falsifiers.",
            },
            {
                "gate": "group_boundary",
                "status": "passed",
                "evidence": "Method/data choices are explicitly non-binding and assigned to Group 2.",
            },
        ],
        "final_hypothesis": {
            "hypothesis_id": hypothesis["hypothesis_id"],
            "gap_id": hypothesis["gap_card_ids"][0],
            "title": hypothesis["title"],
            "statement": hypothesis["hypothesis_statement"],
            "falsifiable_form": hypothesis["falsifiable_form"],
            "status": hypothesis["status"],
            "novelty_judgement": review["conclusion"]["bounded_gap"],
        },
        "source_artifacts": source_artifacts,
        "scientific_constraints": constraints,
        "group2_scope": {
            "objective": "Select feasible data and methods, then turn the accepted hypothesis into the scientific-ten-item proposal without changing its evidence boundary.",
            "starting_tasks": [
                "Match each construct and falsifier to candidate data sources; audit access, licensing, time coverage and join keys.",
                "Use the method library to compare designs capable of cohort-robust policy effects, baseline-capacity heterogeneity and competing mechanisms.",
                "Choose operational definitions and preregistered robustness/falsification rules, including missingness, spillovers and denominator sensitivity.",
                "Write the scientific ten items/proposal with the GapCard, HypothesisCard and nearest-work matrix as the evidence spine.",
            ],
            "must_not_change_without_return_to_group1": [
                "the conditional sign-switch rather than uniform-benefit hypothesis",
                "the requirement that the digital moderator predates treatment",
                "the distinction between EPIE, overinvestment and general investment efficiency",
                "the paired greenwashing and direct firm-carbon outcomes",
                "the corpus-bounded novelty wording",
            ],
        },
        "unresolved_conditions": [
            *hypothesis.get("feasibility", {}).get("blocking_items", []),
            *review.get("limitations", []),
        ],
    }
    handoff_errors = _schema_errors(handoff, HANDOFF_SCHEMA)
    if handoff_errors:
        raise ValueError("handoff schema failed: " + "; ".join(handoff_errors[:10]))
    handoff_status_errors = _handoff_status_errors(handoff)
    if handoff_status_errors:
        raise ValueError(
            "handoff status gate failed: " + "; ".join(handoff_status_errors[:10])
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    handoff_path = out_dir / "handoff.json"
    readme_path = out_dir / "README_CN.md"
    handoff_path.write_text(
        json.dumps(handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    readme_path.write_text(
        _markdown(handoff, review, gap, hypothesis), encoding="utf-8"
    )
    manifest = {
        "schema_version": "1.0.0",
        "handoff_id": handoff_id,
        "generated_at": generated_at,
        "artifacts": [
            {
                "name": "handoff",
                "path": "handoff.json",
                "sha256": _sha(handoff_path),
            },
            {
                "name": "readme_cn",
                "path": "README_CN.md",
                "sha256": _sha(readme_path),
            },
        ],
        "source_artifacts": source_artifacts,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return handoff


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--generated-at", required=True)
    args = parser.parse_args()
    try:
        handoff = build(args.base.resolve(), args.out.resolve(), args.generated_at)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"WROTE: {args.out} ({handoff['handoff_id']}, {handoff['status']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

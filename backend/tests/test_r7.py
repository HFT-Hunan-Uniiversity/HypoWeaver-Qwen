import asyncio

import pytest
from fastapi.testclient import TestClient

from hypoweaver.app import create_app
from hypoweaver.cases.carbon import SOURCE
from hypoweaver.claims.service import check_wording
from hypoweaver.config import Settings
from hypoweaver.proposal.models import Proposal
from hypoweaver.proposal.rendering import NARRATIVE
from hypoweaver.proposal.service import build_proposal


ORIGINALS = [
    "该暴露不是企业真实处理分配，研究结论限定为条件关联，不作因果解释。",
    "拟使用 Mendeley Data 的“碳市场企业面板 · Mendeley V1”，来源记录为 Wei（2025）发布的 "
    "“Industry Peer Effect of Corporate Green Innovation”，许可标示为 CC BY 4.0。",
    "拟使用 Mendeley Data 的“碳市场企业面板 · Mendeley V1”，来源记录为 Wei（{{num:dataset.year_max}}）发布的 "
    "“Industry Peer Effect of Corporate Green Innovation”，许可标示为 CC BY 4.0。",
    "另一个待检验问题是，独立申请与联合申请分别衡量时，关联模式是否不同。",
    "可将独立申请作为替代结果，并将全部绿色专利作为另一项稳健性分析。",
    "后续应补充暴露构造说明、处理时点与分组依据、变量口径文档，并在具备相应数据和假设支持后再考虑因果识别设计。",
    "在获得相应数据并核验识别假设前，不据此作因果解释。",
]
FINAL_TEXT = "两者存在条件关联。"


def snapshot(empirical=False):
    return {
        "project": {"title": "第七轮回归"},
        "run": {
            "id": "run",
            "result": {"main": {"coef": 0.1, "se": 0.02, "p": 0.01, "n_obs": 100}, "robustness": []},
        }
        if empirical
        else None,
        "claims": [
            {
                "claim_id": "main",
                "chosen_strength": "associational",
                "user_decision": "accepted",
                "final_text": FINAL_TEXT,
            }
        ]
        if empirical
        else [],
        "candidate": {"evidence_ids": []},
        "plan": {"id": "plan"},
        "evidence": [
            {
                "id": "ev_known",
                "title": "The Effect of Policy in 2024",
                "authors": ["Smith"],
                "year": 2024,
                "doi": "10.1234/example.2",
                "abstract": "",
            }
        ],
        "dataset": {
            "name": "碳市场企业面板 · Mendeley V1",
            "n_rows": 100,
            "panel": {"time_min": 2010, "time_max": 2021},
            "source": SOURCE,
        },
        "readiness": {"data_plan": []},
        "binding": None,
    }


class NarrativeLLM:
    def __init__(self, text, interpretation=FINAL_TEXT):
        self.text = text
        self.interpretation = interpretation
        self.calls = []

    async def generate(self, name, payload, schema, project_id=None):
        self.calls.append(name)
        assert payload["numbers"]["dataset.source_year"] == 2025
        assert payload["numbers"]["dataset.year_max"] == 2021
        if name == "interpret_results":
            return schema.model_validate({"paragraphs": [{"claim_id": "main", "text": self.interpretation}]})
        return schema.model_validate({"sections": [{"key": key, "markdown": self.text} for key in NARRATIVE]})


@pytest.mark.parametrize(
    "text",
    ORIGINALS
    + [
        "另一研究方向是其一，也属于研究议题之一；应统一口径并逐一核查。",
        "来源引用年为{{num:dataset.source_year}}。",
        "依据 Smith（2024）的 The Effect of Policy in 2024，DOI 为 10.1234/example.2。",
        "数据 DOI 为 10.17632/rrfwny7byp.1。",
    ],
)
def test_narrative_generation_accepts_originals_and_known_metadata(text):
    llm = NarrativeLLM(text)
    sections, _, record = asyncio.run(build_proposal(snapshot(), llm, "project", lambda _: None))
    assert record["narrative_status"] == "complete"
    assert record["narrative_errors"] == []
    assert llm.calls == ["write_proposal_sections"]
    assert all(s["markdown"] == text for s in sections if s["key"] in NARRATIVE)


@pytest.mark.parametrize(
    "text",
    [
        "碳市场促进了绿色创新",
        "证明了因果效应",
        "提升了12%",
        ORIGINALS[1] + "样本为2025家企业。",
        ORIGINALS[1] + "碳市场促进了绿色创新。",
        "未知来源 Zhang（2025）及 CC BY 3.0。",
        "Smith（2023）的文献结论尚待核实。",
    ],
)
def test_real_violations_remain_partial_after_repair(text):
    from hypoweaver.proposal.rendering import METHOD_DESCRIPTION_SECTIONS

    llm = NarrativeLLM(text)
    sections, _, record = asyncio.run(build_proposal(snapshot(), llm, "project", lambda _: None))
    assert record["narrative_status"] == "partial"
    assert llm.calls == ["write_proposal_sections"] * 2
    failed_sections = {e["section"] for e in record["narrative_errors"]}
    assert failed_sections
    # Conclusion-facing sections must not keep the violating draft.
    by_key = {s["key"]: s["markdown"] for s in sections if s["key"] in NARRATIVE}
    for key in failed_sections:
        assert by_key[key] != text
    # Method-description sections only fail on number/placeholder rules, not wording alone.
    wording_only = text in {"碳市场促进了绿色创新", "证明了因果效应"} or text.endswith("碳市场促进了绿色创新。")
    if wording_only:
        assert failed_sections.isdisjoint(METHOD_DESCRIPTION_SECTIONS)
        for key in METHOD_DESCRIPTION_SECTIONS:
            assert by_key[key] == text
    else:
        # Number or metadata violations still apply to every narrative section.
        assert METHOD_DESCRIPTION_SECTIONS <= failed_sections or failed_sections >= set(NARRATIVE) - METHOD_DESCRIPTION_SECTIONS



@pytest.mark.parametrize(
    "prefix", ["不作", "不据此作", "不宜作", "避免作", "不能作", "不足以支持", "无法作", "尚不能作"]
)
def test_negation_stays_within_clause(prefix):
    text = prefix + "因果解释。"
    assert check_wording(text, "associational")["valid"]
    assert not check_wording(text + "但碳市场促进了绿色创新。", "associational")["valid"]


@pytest.mark.parametrize("action", ["考虑", "开展"])
def test_future_causal_design_is_conditional(action):
    text = "待补齐数据并核实假设后再" + action + "因果识别设计。"
    assert check_wording(text, "associational")["valid"]
    assert not check_wording(text + "证明了因果效应。", "associational")["valid"]


@pytest.mark.parametrize("left,right", [("“", "”"), ("《", "》"), ('"', '"')])
def test_english_title_does_not_hide_authors_claim(left, right):
    text = "文献标题为" + left + "Industry Peer Effect of Corporate Green Innovation" + right + "。"
    assert check_wording(text, "associational")["valid"]
    assert not check_wording(text + "The policy causes innovation.", "associational")["valid"]
    assert not check_wording("This is the effect of policy.", "associational")["valid"]
    assert not check_wording('本文认为 "The policy causes innovation."', "associational")["valid"]


@pytest.mark.parametrize(
    "paragraph",
    [FINAL_TEXT, FINAL_TEXT + "仍需核对数据。", "在当前设定下，" + FINAL_TEXT + "仍需核对数据。", "需继续核对数据。"],
)
def test_interpretation_containing_final_text_is_not_duplicated(paragraph):
    llm = NarrativeLLM("继续核实文献。", paragraph)
    sections, _, record = asyncio.run(build_proposal(snapshot(empirical=True), llm, "project", lambda _: None))
    assert record["narrative_status"] == "complete"
    conclusion = next(s["markdown"] for s in sections if s["key"] == "results")
    expected = paragraph if FINAL_TEXT in paragraph else FINAL_TEXT + " " + paragraph
    conclusion = conclusion.split("### 结论强度与边界\n\n", 1)[1].split("\n\n### 局限与后续计划", 1)[0]
    assert conclusion == "采用强度：关联。" + expected
    assert conclusion.count(FINAL_TEXT) == 1


def test_edit_uses_saved_metadata_and_still_rejects_bare_numbers(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    llm = NarrativeLLM(ORIGINALS[1])
    saved_snapshot = snapshot()
    sections, _, _ = asyncio.run(build_proposal(saved_snapshot, llm, "project", lambda _: None))
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"title": "元数据编辑"}).json()["id"]
        with app.state.sessions() as db:
            proposal = Proposal(
                project_id=project, version=1, kind="plan_only", sections=sections, snapshot=saved_snapshot
            )
            db.add(proposal)
            db.commit()
            identifier = proposal.id
        url = f"/api/proposals/{identifier}/sections/datasets"
        text = ORIGINALS[1] + "仍需核实变量口径。"
        assert client.patch(url, json={"markdown": text}).status_code == 200
        assert client.patch(url, json={"markdown": text + "提升了12%"}).status_code == 400
        saved = client.get(f"/api/proposals/{identifier}").json()
        assert next(s["markdown"] for s in saved["sections"] if s["key"] == "datasets") == text


ACTUAL_BLOCKED_JOB_4193 = [
    "- H1：在双向固定效应面板模型中，行业同群碳市场暴露与绿色发明专利申请数之间是否可观察到条件关联；方向与大小不预设，不解释为因果。",
    "- H3：在事件研究设定中，暴露状态变化前后是否可观察到不同的关联模式；该模式仅作为动态关联线索，不解释为政策或同群效应因果。",
    "创新点不在于宣称新的因果机制，而在于把碳价研究中关于创新能力的异质性线索谨慎迁移到行业同群暴露场景。",
    "由于证据强度不足，上述数值仅作为待核验输出和不确定性边界，不用于判断关联方向或形成因果结论。",
    "本研究不主张因果关系，并非因果证据，不构成因果推断，无法识别因果效应。",
    "待检验的因果机制包括同群学习；是否存在因果关系仍需后续数据。",
]


@pytest.mark.parametrize("text", ACTUAL_BLOCKED_JOB_4193)
def test_job_4193_negated_or_hypothetical_causal_passes(text):
    assert check_wording(text, "associational")["valid"], check_wording(text, "associational")


@pytest.mark.parametrize(
    "text",
    [
        "碳市场导致绿色创新增加。",
        "结果证明了因果关系。",
        "因果效应为正。",
        "不解释为因果，但碳市场导致创新。",
        "是否存在因果关系已被证明，因果效应显著。",
    ],
)
def test_real_causal_assertions_still_blocked(text):
    assert not check_wording(text, "associational")["valid"]

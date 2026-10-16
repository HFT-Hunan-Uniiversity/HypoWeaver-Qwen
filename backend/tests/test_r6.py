import json
from pathlib import Path
import pytest
from hypoweaver.proposal.rendering import issues


@pytest.mark.parametrize(
    "text",
    [
        "需核查零值与缺失定义，并考虑零膨胀。",
        "暴露为二元指标，两类计数的口径待核实。",
        "两者采用单一口径，首次检查结果一致。",
        "结果使用 log1p(green1 + green2) 构造，控制使用 log(total_assets)。",
        "字段 patent2020 与 green_patent1 用于派生。",
        "说明公式 `log1p(x + 1)` 与 `field123`，以及 x + 1 的含义。",
        "固定效应模型本身不足以支持因果解释。",
        "现有证据不能据此推断因果关系。",
        "当前设计不支持直接的因果解释。",
        "本次结果无法确认两者存在因果关系。",
        "不能把当前关联解释为因果关系。",
        "仅有 log1p(绿色发明独立申请数 + 绿色发明联合申请数) 的定义。",
    ],
)
def test_nonquantitative_and_negated_causal_prose_passes(text):
    assert issues(text, {}, "associational") == []


@pytest.mark.parametrize(
    "text",
    [
        "样本一百家企业。",
        "得到五十条观测。",
        "持续三年。",
        "增加两倍。",
        "共十个组。",
        "样本有50家企业。",
        "占百分之五十。",
        "估计值为0.05。",
        "样本 two hundred firms。",
        "不能解释为因果，但是促进了创新。",
        "固定效应证明因果关系。",
        "无法核验数据，但具有因果效应。",
        "不能否认因果关系。",
        "无法排除因果效应。",
        "不足以支持因果解释，但政策驱动创新。",
        "log1p(x) 的系数为0.7，字段 x2020 来自2020年。",
    ],
)
def test_quantities_and_positive_causal_claims_still_fail(text):
    assert issues(text, {}, "associational")


@pytest.mark.parametrize(
    "paragraph",
    json.loads((Path(__file__).parent / "fixtures" / "r6_narrative_paragraphs.json").read_text()),
    ids=lambda p: p["section"],
)
def test_three_actual_failed_paragraphs_pass(paragraph):
    assert "零值" in paragraph["text"]
    assert issues(paragraph["text"], {}, "associational") == []


def test_narrative_failure_api_alias_grouping_and_legacy_rows(tmp_path):
    from fastapi.testclient import TestClient
    from hypoweaver.app import create_app
    from hypoweaver.config import Settings
    from hypoweaver.proposal.models import Proposal

    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"title": "兼容接口"}).json()["id"]
        errors = [
            {"section": "data", "rule": "数字须占位", "snippet": "样本100家"},
            {"section": "data", "rule": "因果超限", "snippet": "导致增长"},
            {"section": "data", "rule": "数字须占位", "snippet": "样本100家"},
            {"section": "gap", "rule": "章节缺失", "snippet": ""},
        ]
        with app.state.sessions() as db:
            proposal = Proposal(
                project_id=project,
                version=1,
                kind="plan_only",
                sections=[],
                snapshot={"project": {"title": "兼容接口"}},
                narrative_status="partial",
                narrative_errors=errors,
            )
            db.add(proposal)
            db.commit()
            identifier = proposal.id
        detail = client.get("/api/proposals/" + identifier).json()
        listing = client.get(f"/api/projects/{project}/proposals").json()[0]
        expected = [
            {"section": "data", "reason": "数字须占位：样本100家；因果超限：导致增长"},
            {"section": "gap", "reason": "章节缺失"},
        ]
        assert detail["narrative_failures"] == detail["narrative_errors"] == expected
        assert listing["narrative_failures"] == expected
        with app.state.sessions() as db:
            assert db.get(Proposal, identifier).narrative_errors == errors


def test_patch_validates_before_write_and_draft_expands_drop_controls(tmp_path):
    from fastapi.testclient import TestClient
    from hypoweaver.app import create_app
    from hypoweaver.config import Settings
    from test_plans import seed_selected, drain
    from hypoweaver.plans.models import StudyPlan
    from hypoweaver.plans.robustness import validate_plan
    from hypoweaver.errors import AppError
    from types import SimpleNamespace

    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        project, _ = seed_selected(client, app, case="carbon")
        client.post(f"/api/projects/{project}/plans")
        drain(client, app)
        plan = client.get(f"/api/projects/{project}/plans").json()[0]
        base = "/api/plans/" + plan["id"]
        drop = next(r for r in plan["robustness"] if r["kind"] == "drop_controls")
        assert drop["args"]["controls"] == ["log_assets", "leverage", "profitability"]
        original = client.get(base).json()
        for confirmed in [False, True]:
            if confirmed:
                assert client.post(base + ":confirm").status_code == 200
                original = client.get(base).json()
            invalid = {
                **plan,
                "robustness": [
                    *plan["robustness"],
                    {"id": "invalid", "kind": "alt_outcome", "change": "错误公式", "args": {"outcome": "unknown ** 2"}},
                ],
            }
            with app.state.sessions() as db:
                preview = SimpleNamespace(**{**invalid, "project_id": project})
                with pytest.raises(AppError) as caught:
                    validate_plan(db, preview)
            response = client.patch(base, json=invalid)
            assert response.status_code == 422
            assert response.json()["error"]["message"] == caught.value.message
            assert client.get(base).json() == original
            assert len(client.get(f"/api/projects/{project}/plans").json()) == 1
        # An empty drop specification submitted by an editor is normalized as well.
        plan["robustness"] = [{**r, "args": {}} if r["kind"] == "drop_controls" else r for r in plan["robustness"]]
        edited = client.patch(base, json=plan)
        assert edited.status_code == 200, edited.text
        fresh = edited.json()
        assert fresh["version"] == 2
        with app.state.sessions() as db:
            saved = db.get(StudyPlan, fresh["id"])
            assert next(r for r in saved.robustness if r["kind"] == "drop_controls")["args"]["controls"] == [
                "log_assets",
                "leverage",
                "profitability",
            ]


def test_actual_failed_sections_pass_generation_without_repair():
    import asyncio
    from hypoweaver.proposal.narrative import generate_sections
    from hypoweaver.proposal.rendering import NARRATIVE

    paragraphs = json.loads((Path(__file__).parent / "fixtures" / "r6_narrative_paragraphs.json").read_text())
    originals = {p["section"]: p["text"] for p in paragraphs}

    class CapturedNarrative:
        calls = 0

        async def generate(self, name, payload, schema, project_id=None):
            self.calls += 1
            return schema.model_validate(
                {"sections": [{"key": key, "markdown": originals.get(key, "继续核实研究材料。")} for key in NARRATIVE]}
            )

    llm = CapturedNarrative()
    accepted, errors = asyncio.run(generate_sections(llm, {"numbers": {}, "max_strength": "associational"}, "test"))
    assert llm.calls == 1 and errors == [] and len(accepted) == len(NARRATIVE)
    assert all(accepted[key].markdown == text for key, text in originals.items())


@pytest.mark.parametrize(
    "section,text",
    [
        ("techniques", "采用双向固定效应与事件研究，用于检验关联并估计处理效应。"),
        ("techniques", "双重差分用于识别因果效应的处理组—对照组差异，配套置换检验。"),
        ("experiments", "| 实验 | 目的 |\n|---|---|\n| 主模型 | 检验行业暴露与绿色发明的关联 |"),
        ("experiments", "事件研究用于评估政策冲击前后差异，不据此下因果结论。"),
        ("methods", "识别策略为面板固定效应；标准误在企业层面聚类，用于估计处理效应。"),
        ("methods", "在识别假设成立时可讨论谨慎的因果解释边界，主文仍报告关联。"),
    ],
)
def test_method_sections_allow_identification_terminology(section, text):
    assert issues(text, {}, "associational", section=section) == []


@pytest.mark.parametrize(
    "section",
    ["problem", "abstract", "title", "rationale", "datasets", None],
)
@pytest.mark.parametrize(
    "text",
    [
        "双重差分识别因果效应。",
        "碳市场促进了绿色创新。",
        "固定效应证明因果关系。",
    ],
)
def test_conclusion_sections_still_block_causal_wording(section, text):
    assert issues(text, {}, "associational", section=section)


def test_method_sections_still_require_number_placeholders():
    assert issues("样本有50家企业。", {}, "associational", section="techniques")
    assert issues("估计值为0.05。", {}, "associational", section="experiments")


def test_repair_rewrites_only_failed_sections():
    import asyncio
    from hypoweaver.proposal.narrative import generate_sections
    from hypoweaver.proposal.rendering import NARRATIVE

    class SelectiveLLM:
        def __init__(self):
            self.calls = 0
            self.payloads = []

        async def generate(self, name, payload, schema, project_id=None):
            self.calls += 1
            self.payloads.append(payload)
            if self.calls == 1:
                sections = []
                for key in NARRATIVE:
                    if key == "techniques":
                        md = "采用双重差分识别因果效应，配套事件研究。"
                    elif key == "problem":
                        md = "碳市场促进了绿色创新。"
                    else:
                        md = "结合已纳入文献与变量定义开展后续研究。"
                    sections.append({"key": key, "markdown": md, "evidence_ids": []})
                return schema.model_validate({"sections": sections})
            # Second pass: only repair_sections should matter; return fixed texts for all.
            assert "repair_sections" in payload
            assert "problem" in payload["repair_sections"]
            # techniques is method-description: first-pass causal jargon should already be accepted
            assert "techniques" not in payload["repair_sections"]
            assert "techniques" in payload["accepted_sections"]
            sections = []
            for key in NARRATIVE:
                if key == "problem":
                    md = "待检验命题：行业同群暴露与绿色发明是否存在条件关联。"
                elif key == "techniques":
                    md = "不应再被请求重写的技术手段正文。"
                else:
                    md = "结合已纳入文献与变量定义开展后续研究。"
                sections.append({"key": key, "markdown": md, "evidence_ids": []})
            return schema.model_validate({"sections": sections})

    llm = SelectiveLLM()
    accepted, errors = asyncio.run(
        generate_sections(llm, {"numbers": {}, "max_strength": "associational"}, "test")
    )
    assert llm.calls == 2
    assert errors == []
    assert accepted["techniques"].markdown == "采用双重差分识别因果效应，配套事件研究。"
    assert "待检验命题" in accepted["problem"].markdown
    assert "techniques" in llm.payloads[1]["accepted_sections"]
    assert "problem" in llm.payloads[1]["repair_sections"]


@pytest.mark.parametrize(
    "text",
    [
        "- 计数结果稳健变换：用于处理绿色发明申请的非负计数分布，检查敏感性。",
        "稳健性设定给出的系数分别为{{num:main.coef}}。",
        "按代理变量分组估计，或做分样本分析。",
    ],
)
def test_job_35c2_number_false_positives_pass(text):
    assert issues(text, {"main.coef": 1}, "associational") == []


def test_real_chinese_quantities_still_fail_after_phrase_fix():
    assert issues("约三分之一的企业", {}, "associational")
    assert issues("几分之几", {}, "associational")

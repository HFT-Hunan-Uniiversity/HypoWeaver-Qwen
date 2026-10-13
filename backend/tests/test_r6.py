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

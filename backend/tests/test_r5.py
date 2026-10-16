import asyncio
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from hypoweaver.app import create_app
from hypoweaver.config import Settings
from hypoweaver.datasets.service import register
from hypoweaver.binding.service import suggest
from hypoweaver.cases.carbon import COLUMNS, DOI
from hypoweaver.llm.service import get_llm
from hypoweaver.plans.models import PlanDraft
from hypoweaver.plans.robustness import compile_checks
from hypoweaver.stats.service import compile_spec
from hypoweaver.stats.engine import run_analysis
from hypoweaver.stats.reproduction import reproduce
from hypoweaver.claims.service import assess
from hypoweaver.errors import AppError
from hypoweaver.literature.service import save_cards, evidence
from hypoweaver.literature.models import LiteratureSearch
from hypoweaver.proposal.rendering import NARRATIVE
from test_plans import seed_selected, drain, PlanLLM, plan_payload
from test_stats import synthetic, specification
from test_proposal import ProposalLLM


class ContextLLM(PlanLLM):
    def __init__(self, ids):
        super().__init__(ids)
        self.payloads = {}

    async def generate(self, name, payload, schema, project_id=None):
        self.payloads[name] = payload
        if name == "suggest_bindings":
            return schema.model_validate({"bindings": []})
        return await super().generate(name, payload, schema, project_id)


def test_carbon_draft_context_prefill_confirm_suggest_and_inheritance(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        project, candidate = seed_selected(client, app, case="carbon")
        raw = pd.DataFrame({n: [1.0, 2.0] for n in COLUMNS.values()})
        raw["year"] = [2020, 2021]
        with app.state.sessions() as db:
            dataset = register(
                app.state.settings, db, raw, "碳市场企业面板 · Mendeley V1", {"doi": DOI}, unit="firm_id", time="year"
            )
            dataset_id = dataset.id
            dataset.profile = [
                {**f, "semantics": "peer_exposure", "level": "industry"} if f["name"] == "industry_peer_exposure" else f
                for f in dataset.profile
            ]
            db.commit()
        fake = ContextLLM(candidate["evidence_ids"])
        app.dependency_overrides[get_llm] = lambda: fake
        client.post(f"/api/projects/{project}/candidate-sets")
        drain(client, app)
        assert len(fake.payloads["generate_candidates"]["dataset_fields"]) == len(COLUMNS)
        client.post(f"/api/projects/{project}/plans")
        drain(client, app)
        plan = client.get(f"/api/projects/{project}/plans").json()[0]
        fields = fake.payloads["draft_plan"]["dataset_fields"]
        exposure = next(f for f in fields if f["name"] == "industry_peer_exposure")
        assert exposure["semantics"] == "peer_exposure" and exposure["level"] == "industry"
        assert set(exposure) == {"name", "label", "type", "semantics", "level", "missing_rate"}
        assert plan["method_family"] == "policy_causal"
        assert len(plan["variables"]) == len(plan["suggested_binding"]) == 7
        base = "/api/plans/" + plan["id"]
        prefill = client.get(base + "/bindings").json()
        assert prefill["dataset_id"] == dataset_id and prefill["confirmed"] is False
        assert prefill["bindings"] == plan["suggested_binding"]
        with app.state.sessions() as db:
            suggestions = asyncio.run(suggest(db, plan["id"], dataset_id, fake))
        assert {s["role_name"] for s in suggestions["bindings"]} == set(prefill["bindings"])
        assert fake.payloads["suggest_bindings"]["case_field_notes"]["industry_peer_exposure"]
        assert fake.payloads["suggest_bindings"]["fields"] == fields
        assert client.post(base + ":confirm").status_code == 200
        saved = client.put(base + "/bindings", json={**prefill, "confirmed": True})
        assert saved.status_code == 200, saved.text
        for new in [
            client.post(base + ":new-version"),
            client.patch(base, json={**plan, "boundary_notes": "新增边界"}),
        ]:
            assert new.status_code == 200, new.text
            inherited = client.get("/api/plans/" + new.json()["id"] + "/bindings").json()
            assert inherited["dataset_id"] == dataset_id
            assert inherited["bindings"] == saved.json()["bindings"]
            assert inherited["confirmed"] is False
            assert inherited["inherited_from"] == plan["id"]
            assert inherited["note"] == f"继承自 v{plan['version']}，请重新确认"
        new = client.post(base + ":new-version").json()
        new["robustness"][2]["args"]["outcome"] = "log1p(nonexistent)"
        bad = client.patch("/api/plans/" + new["id"], json=new)
        assert bad.status_code == 422 and "nonexistent" in bad.json()["error"]["message"]


def test_robustness_aliases_execute_and_reject_noop_or_invalid():
    payload = PlanDraft.model_validate(plan_payload()).model_dump()
    payload["variables"] += [
        {"name": "size", "role": "control", "definition": "规模"},
        {"name": "extra", "role": "mechanism", "definition": "额外变量"},
    ]
    payload["robustness"] = [
        {"id": "drop", "kind": "drop_controls", "change": "移除规模", "args": {"controls": ["size"]}},
        {"id": "add", "kind": "add_controls", "change": "新增控制", "args": {"controls": ["extra"]}},
        {"id": "alt", "kind": "alt_outcome", "change": "替代结果", "args": {"outcome": "patents + extra / 100"}},
    ]
    plan = SimpleNamespace(**payload)
    binding = SimpleNamespace(
        bindings={
            "patents": {"field": "y"},
            "exposure": {"field": "d"},
            "firm": {"field": "firm"},
            "year": {"field": "year"},
            "size": {"formula": "x + 1"},
            "extra": {"field": "z"},
        }
    )
    spec = compile_spec(plan, binding)
    assert spec.robustness[0].args["controls"] == ["x + 1"]
    assert spec.robustness[1].args["controls"] == ["z"]
    assert spec.robustness[2].args["outcome"] == "y + z / 100"
    result = run_analysis(spec, synthetic(n_units=60))
    assert all(r["status"] == "succeeded" for r in result["robustness"])
    assert reproduce(spec, synthetic(n_units=60), result)["consistent"]
    plan.robustness[1]["args"]["controls"] = ["size"]
    with pytest.raises(AppError, match="空检验") as exc:
        compile_checks(plan, binding.bindings, set(synthetic().columns))
    assert exc.value.status == 422
    plan.robustness[1]["args"]["controls"] = ["unknown"]
    with pytest.raises(AppError, match="不存在"):
        compile_checks(plan, binding.bindings, set(synthetic().columns))
    plan.robustness[1]["args"]["controls"] = ["__import__('os')"]
    with pytest.raises(AppError, match="只允许"):
        compile_checks(plan, binding.bindings)


def test_failed_robustness_does_not_poison_main_reproduction_or_claim():
    spec = specification()
    # Historical/previously accepted check can fail at runtime, independently of main.
    spec.robustness[1].args = {"years": [1900]}
    raw = synthetic(seed=2025)
    result = run_analysis(spec, raw)
    report = reproduce(spec, raw, result)
    assert report["main_consistent"] is True and report["consistent"] is True
    failure = next(r for r in report["rows"] if r["id"] == "year")
    assert failure["status"] == "failed" and failure["origin"] == "analysis"
    plan = PlanDraft.model_validate(plan_payload()).model_dump()
    plan["treatment_is_real_assignment"] = False
    assert assess(plan, result, report)[0]["max_strength"] == "associational"
    # Successful robustness with a reproducibility mismatch still flags aggregate.
    result["robustness"][0]["coef"] += 1
    mismatch = reproduce(spec, raw, result)
    assert mismatch["main_consistent"] and not mismatch["consistent"]
    assert assess(plan, result, mismatch)[0]["max_strength"] == "associational"
    mismatch["main_consistent"] = False
    assert assess(plan, result, mismatch)[0]["max_strength"] == "insufficient"


def test_partial_narrative_retains_good_sections_and_returns_reasons(tmp_path):
    class PartialLLM(ProposalLLM):
        async def generate(self, name, payload, schema, project_id=None):
            if name == "write_proposal_sections":
                self.calls.append(payload)
                return schema.model_validate(
                    {
                        "sections": [
                            {
                                "key": k,
                                "markdown": "样本年份为2010。" if k == "datasets" else "已通过的文献讨论，后续继续核实。",
                            }
                            for k in NARRATIVE
                            if len(self.calls) == 1 or k == "datasets"
                        ]
                    }
                )
            return await super().generate(name, payload, schema, project_id)

    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        project, candidate = seed_selected(client, app)
        client.post(f"/api/projects/{project}/plans")
        drain(client, app)
        fake = PartialLLM(candidate["evidence_ids"])
        app.dependency_overrides[get_llm] = lambda: fake
        client.post(f"/api/projects/{project}/proposals")
        drain(client, app)
        proposal = client.get(f"/api/projects/{project}/proposals").json()[0]
        assert proposal["narrative_status"] == "partial"
        assert {e["section"] for e in proposal["narrative_errors"]} == {"datasets"}
        assert fake.calls[1]["rewrite_reasons"][0] == {
            "section": "datasets",
            "snippet": "样本年份为2010。",
            "rule": "所有数字须使用给定占位符",
        }
        for section in proposal["sections"]:
            if section["key"] in NARRATIVE and section["key"] != "datasets":
                assert section["markdown"] == "已通过的文献讨论，后续继续核实。"
        assert "2010" not in proposal["markdown"] and "部分叙述未通过校验" in proposal["markdown"]


def test_search_top_forty_preserves_manual_selection(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"title": "文献限额"}).json()["id"]
        with app.state.sessions() as db:
            search = LiteratureSearch(project_id=project, queries=[])
            db.add(search)
            db.commit()
            cards = [
                {"title": f"Paper {i}", "source": "crossref", "sources": ["crossref"], "_relevance": i}
                for i in range(55)
            ]
            save_cards(db, project, cards, search.id)
            rows = evidence(db, project)
            assert sum(c.included for c in rows) == 40
            low = next(c for c in rows if c.title == "Paper 0")
            high = next(c for c in rows if c.title == "Paper 54")
            assert not low.included and high.included
            low.included, high.included = True, False
            db.commit()
            save_cards(db, project, cards, search.id)
            assert low.included and not high.included


def test_dataset_year_placeholders_and_identical_conclusion_not_duplicated():
    from hypoweaver.proposal.service import build_proposal

    text = "两者存在条件关联。"

    class NarrativeLLM:
        async def generate(self, name, payload, schema, project_id=None):
            if name == "interpret_results":
                return schema.model_validate({"paragraphs": [{"claim_id": "main", "text": text}]})
            assert payload["numbers"]["dataset.year_min"] == 2010
            assert payload["numbers"]["dataset.year_max"] == 2021
            assert payload["numbers"]["dataset.n_units"] == 180
            return schema.model_validate(
                {
                    "sections": [
                        {
                            "key": k,
                            "markdown": "样本起止年份为{{num:dataset.year_min}}至{{num:dataset.year_max}}，"
                            "企业数为{{num:dataset.n_units}}。"
                            if k == "datasets"
                            else "继续核实文献。",
                        }
                        for k in NARRATIVE
                    ]
                }
            )

    result = run_analysis(specification(), synthetic(seed=2025))
    snapshot = {
        "run": {"id": "run", "result": result},
        "claims": [
            {"claim_id": "main", "chosen_strength": "associational", "user_decision": "accepted", "final_text": text}
        ],
        "candidate": {"evidence_ids": []},
        "plan": {"id": "plan"},
        "evidence": [],
        "dataset": {"n_rows": 2160, "panel": {"time_min": "2010", "time_max": "2021", "n_units": 180}, "source": {}},
        "readiness": {"data_plan": []},
        "binding": None,
    }
    sections, _, metadata = asyncio.run(build_proposal(snapshot, NarrativeLLM(), "project", lambda _: None))
    assert metadata["narrative_status"] == "complete"
    conclusions = next(s for s in sections if s["key"] == "results")
    assert conclusions["markdown"].count(text) == 1


def test_registered_carbon_defaults_run_and_reproduce():
    from test_stats import registered_carbon_path
    from hypoweaver.cases.carbon import plan_defaults

    raw = pd.read_csv(registered_carbon_path())
    sample = raw.loc[raw["firm_id"].isin(raw["firm_id"].unique()[:120])]
    data = plan_defaults(PlanDraft.model_validate(plan_payload()).model_dump())
    data["permutation"] = {"n": 39, "seed": 42}
    plan = SimpleNamespace(**data)
    spec = compile_spec(plan, SimpleNamespace(bindings=data["suggested_binding"]))
    result = run_analysis(spec, sample)
    assert result["main"]["n_units"] == 120
    assert len(result["robustness"]) == 4
    assert all(r["status"] == "succeeded" for r in result["robustness"]), result["robustness"]
    assert reproduce(spec, sample, result)["consistent"]


def test_interpretation_failure_is_partial_and_preserves_other_claims():
    from hypoweaver.proposal.narrative import generate_interpretations

    class Fake:
        async def generate(self, name, payload, schema, project_id=None):
            return schema.model_validate(
                {
                    "paragraphs": [
                        {"claim_id": "good", "text": "两者存在条件关联。"},
                        {"claim_id": "bad", "text": "产生了90%的增长。"},
                    ]
                }
            )

    claims = [{"claim_id": key, "chosen_strength": "associational"} for key in ["good", "bad"]]
    accepted, errors = asyncio.run(generate_interpretations(Fake(), claims, {}, "project"))
    assert accepted == {"good": "两者存在条件关联。"}
    assert errors[0]["section"] == "results" and errors[0]["claim_id"] == "bad"

import numpy as np
import pandas as pd
import pytest
from hypoweaver.errors import AppError
from hypoweaver.stats.models import AnalysisSpec
from hypoweaver.stats.service import run_analysis


def synthetic(tau=0.3, seed=2026, n_units=180):
    rng = np.random.default_rng(seed)
    unit = np.repeat(np.arange(n_units), 12)
    period = np.tile(np.arange(12), n_units)
    cohort = np.repeat(np.where(np.arange(n_units) % 4 == 3, 99, 4 + 2 * (np.arange(n_units) % 3)), 12)
    treatment = (period >= cohort).astype(float)
    x = rng.normal(size=len(unit))
    z = rng.normal(size=len(unit))
    alpha = np.repeat(rng.normal(size=n_units), 12)
    y = alpha + 0.03 * period + 0.2 * x + tau * treatment + rng.normal(scale=0.12, size=len(unit))
    return pd.DataFrame(
        {
            "firm": unit,
            "year": 2010 + period,
            "y": y,
            "d": treatment,
            "x": x,
            "z": z,
            "y_alt": y + rng.normal(scale=0.02, size=len(unit)),
        }
    )


def specification():
    return AnalysisSpec(
        method_family="policy_causal",
        unit="firm",
        time="year",
        outcome="y",
        treatment="d",
        controls=["x"],
        event={"bins": [-3, -2, 0, 1, 2, 3, 4]},
        permutation={"n": 199, "seed": 42},
        robustness=[
            {"id": "without", "change": "不含控制", "kind": "drop_controls"},
            {"id": "year", "change": "剔除末年", "kind": "exclude_years", "args": {"years": [2021]}},
            {"id": "mono", "change": "单调路径", "kind": "monotone_only"},
            {"id": "outcome", "change": "替代结果", "kind": "alt_outcome", "args": {"outcome": "y_alt"}},
            {"id": "more", "change": "增加控制", "kind": "add_controls", "args": {"controls": ["z"]}},
        ],
    )


def test_known_effect_events_robustness_and_permutation():
    result = run_analysis(specification(), synthetic())
    assert abs(result["main"]["coef"] - 0.3) < 2 * result["main"]["se"], result["main"]
    assert result["permutation"]["p"] < 0.05, result["permutation"]["p"]
    assert result["permutation"]["n"] == 199
    assert len(result["robustness"]) == 5 and all(r["status"] == "succeeded" for r in result["robustness"])
    assert result["event"]["reference"] == -1
    assert -1 not in [r["k"] for r in result["event"]["terms"]]
    assert result["event"]["pretrend_wald"]["p"] is not None
    null = run_analysis(specification(), synthetic(tau=0))
    assert null["permutation"]["p"] >= 0.05, null["permutation"]["p"]


def test_association_mechanism_and_readable_failures():
    data = synthetic()
    association = specification().model_copy(update={"method_family": "panel_association", "robustness": []})
    result = run_analysis(association, data)
    assert result["event"] is None and result["steps"]["event_study"]["status"] == "not_applicable"
    data["moderator"] = np.random.default_rng(88).normal(size=len(data))
    data["y"] = data["y"] + 0.6 * data["d"] * data["moderator"]
    spec = association.model_copy(update={"method_family": "mechanism_boundary", "moderator": "moderator"})
    result = run_analysis(spec, data)
    from hypoweaver.stats.estimation import estimate

    no_controls, _, _ = estimate(spec.model_copy(update={"controls": []}), data)
    assert abs(result["permutation"]["observed"] - no_controls["coef"]) < 1e-9
    assert result["main"]["target"] == "interaction"
    assert abs(result["main"]["coef"] - 0.6) < 2 * result["main"]["se"]
    with pytest.raises(AppError, match="不存在"):
        run_analysis(spec.model_copy(update={"unit": "missing"}), data)
    with pytest.raises(AppError, match="重复"):
        run_analysis(spec, pd.concat([data, data.iloc[[0]]]))


def registered_carbon_path():
    import sqlite3
    import json
    from contextlib import closing
    from pathlib import Path
    from hypoweaver.config import Settings
    from hypoweaver.cases.carbon import DOI, COLUMNS

    storage = Settings().storage_dir().resolve()
    database = storage / "hypoweaver.sqlite"
    if not database.exists():
        pytest.skip("DATA_DIR 尚无登记数据库，请先运行 carbon prepare")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
        rows = db.execute(
            "SELECT id, file_path, selected_columns FROM datasets WHERE json_extract(source, '$.doi') = ? "
            "ORDER BY created_at DESC",
            (DOI,),
        )
        row = next((row for row in rows if set(json.loads(row[2])) == set(COLUMNS.values())), None)
    if row is None:
        pytest.skip("DATA_DIR 尚无已登记碳市场资产，请先运行 carbon prepare")
    path = storage / "datasets" / (row[0] + ".csv")
    assert Path(row[1]).resolve() == path.resolve(), "登记资产路径与 DATA_DIR/datasets 不一致"
    assert path.is_file(), "已登记碳市场文件缺失，请检查资产；不能跳过此失败"
    return path


def test_carbon_small_sample_when_available():
    raw = pd.read_csv(registered_carbon_path())
    sample = raw.loc[raw["firm_id"].isin(raw["firm_id"].unique()[:120])]
    spec = AnalysisSpec(
        method_family="policy_causal",
        unit="firm_id",
        time="year",
        outcome="log1p(green_invention_independent+green_invention_joint)",
        treatment="industry_peer_exposure",
        controls=["log(total_assets)", "leverage", "return_on_assets"],
        permutation={"n": 39, "seed": 42},
    )
    result = run_analysis(spec, sample)
    assert result["main"]["n_units"] == 120
    assert result["main"]["se"] > 0


def test_independent_reproduction_balanced_unbalanced_and_interaction():
    from hypoweaver.stats.service import reproduce

    for missing in [False, True]:
        raw = synthetic(n_units=60)
        if missing:
            raw = raw.drop(index=raw.index[::37])
        spec = specification()
        result = run_analysis(spec, raw)
        report = reproduce(spec, raw, result)
        assert report["consistent"], report
        assert report["max_relative_diff"] < 1e-6
    raw["moderator"] = np.random.default_rng(1).normal(size=len(raw))
    spec = spec.model_copy(update={"method_family": "mechanism_boundary", "moderator": "moderator", "robustness": []})
    assert reproduce(spec, raw, run_analysis(spec, raw))["consistent"]


def test_registered_carbon_lookup_respects_data_dir(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from hypoweaver.app import create_app
    from hypoweaver.config import Settings
    from hypoweaver.datasets.service import register
    from hypoweaver.cases.carbon import DOI, COLUMNS

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app(Settings())
    with TestClient(app):
        with app.state.sessions() as db:
            frame = pd.DataFrame({name: [1, 2] for name in COLUMNS.values()})
            asset = register(app.state.settings, db, frame, "路径回归测试数据", {"doi": DOI})
            register(app.state.settings, db, pd.DataFrame({"Symbol": [1, 2]}), "同 DOI 原始列测试", {"doi": DOI})
            expected = tmp_path / "datasets" / (asset.id + ".csv")
        # An unrelated CSV never substitutes for the database registration.
        (tmp_path / "datasets" / "unregistered.csv").write_text("unused\n1\n")
        assert registered_carbon_path() == expected

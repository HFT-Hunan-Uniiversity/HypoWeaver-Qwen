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

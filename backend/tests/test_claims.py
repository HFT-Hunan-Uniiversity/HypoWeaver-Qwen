import copy
import pytest
from hypoweaver.claims.service import assess,check_wording
from hypoweaver.plans.models import DecisionRules

@pytest.mark.parametrize('change,verdict,strength',[
    ({},'supportive','associational'),({'pre':.01},'mixed','preliminary'),
    ({'coef':-.3},'not_supportive','insufficient'),({'consistent':False},'insufficient','insufficient'),
    ({'real':True},'supportive','causal_cautious'),({'real':True,'family':'panel_association'},'supportive','associational')])
def test_assessment(change,verdict,strength):
    plan={'decision_rules':DecisionRules().model_dump(),'method_family':change.get('family','policy_causal'),'treatment_is_real_assignment':change.get('real',False),'claims_planned':[{'id':'main','type':'main'}]}
    result={'main':{'coef':change.get('coef',.3),'p':.01},'event':{'pretrend_wald':{'p':change.get('pre',.4)}},'robustness':[{'coef':.2,'status':'succeeded'} for _ in range(4)],'permutation':{'p':.01}}
    claim=assess(plan,result,{'consistent':change.get('consistent',True)})[0]
    assert (claim['verdict'],claim['max_strength'])==(verdict,strength)

@pytest.mark.parametrize('text,valid',[('与绿色创新存在关联',True),('碳市场促进了创新',False),('不能解释为因果',True),('不能解释为因果，但是促进了创新',False),('The exposure causes innovation.',False),('This does not establish causality.',True)])
def test_wording(text,valid):
    assert check_wording(text,'associational')['valid']==valid

import numpy as np
import pandas as pd
import pytest
from hypoweaver.errors import AppError
from hypoweaver.stats.models import AnalysisSpec
from hypoweaver.stats.service import run_analysis


def synthetic(tau=.3, seed=2026, n_units=180):
    rng=np.random.default_rng(seed)
    unit=np.repeat(np.arange(n_units),12)
    period=np.tile(np.arange(12),n_units)
    cohort=np.repeat(np.where(np.arange(n_units)%4==3,99,4+2*(np.arange(n_units)%3)),12)
    treatment=(period>=cohort).astype(float)
    x=rng.normal(size=len(unit));z=rng.normal(size=len(unit))
    alpha=np.repeat(rng.normal(size=n_units),12)
    y=alpha+.03*period+.2*x+tau*treatment+rng.normal(scale=.12,size=len(unit))
    return pd.DataFrame({'firm':unit,'year':2010+period,'y':y,'d':treatment,'x':x,'z':z,'y_alt':y+rng.normal(scale=.02,size=len(unit))})


def specification():
    return AnalysisSpec(method_family='policy_causal',unit='firm',time='year',outcome='y',treatment='d',controls=['x'],
                        event={'bins':[-3,-2,0,1,2,3,4]},permutation={'n':199,'seed':42},robustness=[
                            {'id':'without','change':'不含控制','kind':'drop_controls'},
                            {'id':'year','change':'剔除末年','kind':'exclude_years','args':{'years':[2021]}},
                            {'id':'mono','change':'单调路径','kind':'monotone_only'},
                            {'id':'outcome','change':'替代结果','kind':'alt_outcome','args':{'outcome':'y_alt'}},
                            {'id':'more','change':'增加控制','kind':'add_controls','args':{'controls':['z']}}])


def test_known_effect_events_robustness_and_permutation():
    result=run_analysis(specification(),synthetic())
    assert abs(result['main']['coef']-.3)<2*result['main']['se'],result['main']
    assert result['permutation']['p']<.05,result['permutation']['p']
    assert result['permutation']['n']==199
    assert len(result['robustness'])==5 and all(r['status']=='succeeded' for r in result['robustness'])
    assert result['event']['reference']==-1
    assert -1 not in [r['k'] for r in result['event']['terms']]
    assert result['event']['pretrend_wald']['p'] is not None
    null=run_analysis(specification(),synthetic(tau=0))
    assert null['permutation']['p']>=.05,null['permutation']['p']


def test_association_mechanism_and_readable_failures():
    data=synthetic()
    association=specification().model_copy(update={'method_family':'panel_association','robustness':[]})
    result=run_analysis(association,data)
    assert result['event'] is None and result['steps']['event_study']['status']=='not_applicable'
    data['moderator']=np.random.default_rng(88).normal(size=len(data))
    data['y']=data['y']+.6*data['d']*data['moderator']
    spec=association.model_copy(update={'method_family':'mechanism_boundary','moderator':'moderator'})
    result=run_analysis(spec,data)
    from hypoweaver.stats.estimation import estimate
    no_controls,_,_=estimate(spec.model_copy(update={'controls':[]}),data)
    assert abs(result['permutation']['observed']-no_controls['coef'])<1e-9
    assert result['main']['target']=='interaction'
    assert abs(result['main']['coef']-.6)<2*result['main']['se']
    with pytest.raises(AppError,match='不存在'):
        run_analysis(spec.model_copy(update={'unit':'missing'}),data)
    with pytest.raises(AppError,match='重复'):
        run_analysis(spec,pd.concat([data,data.iloc[[0]]]))


def test_carbon_small_sample_when_available():
    from pathlib import Path
    from hypoweaver.config import ROOT
    paths=list((ROOT/'var/datasets').glob('*.csv'))[:30]
    raw=None
    for path in paths:
        columns=pd.read_csv(path,nrows=0).columns
        if {'industry_peer_exposure','green_invention_independent','total_assets'} <= set(columns):
            raw=pd.read_csv(path);break
    if raw is None:
        pytest.skip('本机无公开碳市场数据')
    sample=raw.loc[raw['firm_id'].isin(raw['firm_id'].unique()[:120])]
    spec=AnalysisSpec(method_family='policy_causal',unit='firm_id',time='year',outcome='log1p(green_invention_independent+green_invention_joint)',treatment='industry_peer_exposure',controls=['log(total_assets)','leverage','return_on_assets'],permutation={'n':39,'seed':42})
    result=run_analysis(spec,sample)
    assert result['main']['n_units']==120
    assert result['main']['se']>0

"""One end-to-end API seam; all network/model dependencies are explicit test doubles."""
import httpx
from fastapi.testclient import TestClient
from hypoweaver.app import create_app
from hypoweaver.config import Settings
from hypoweaver.literature.sources import LiteratureClient
from hypoweaver.llm.service import get_llm
from test_proposal import ProposalLLM
from test_plans import drain
from test_stats import synthetic

class FlowLLM(ProposalLLM):
    async def generate(self,name,payload,schema,project_id=None):
        if name=='suggest_queries':
            return schema.model_validate({'queries':[{'text':t} for t in ['green innovation','peer exposure','企业创新']]})
        if name=='generate_candidates':self.ids=[c['id'] for c in payload['evidence']]
        return await super().generate(name,payload,schema,project_id)


def test_complete_api_flow_and_stale_preservation(tmp_path):
    app=create_app(Settings(data_dir=tmp_path))
    def respond(request):
        if request.url.host=='api.openalex.org':return httpx.Response(200,json={'results':[{'title':'Innovation evidence','doi':'https://doi.org/10.123/one','publication_year':2024}]})
        return httpx.Response(200,json={'message':{'items':[{'title':['同群关联'],'DOI':'10.123/two','issued':{'date-parts':[[2023]]}}]}})
    app.state.literature_client=LiteratureClient(app.state.settings,httpx.MockTransport(respond))
    fake=FlowLLM([]);app.dependency_overrides[get_llm]=lambda:fake
    with TestClient(app) as client:
        def complete(response):
            assert response.status_code==200,response.text
            job=response.json()['job_id'];drain(client,app)
            record=client.get('/api/jobs/'+job).json()
            assert record['status']=='succeeded',record
            return record['result']
        p=client.post('/api/projects',json={'title':'完整流程验证','direction':{'text':'行业同群暴露与企业创新'}}).json()['id']
        path='/api/projects/'+p
        queries=client.post(path+'/queries:suggest').json()
        complete(client.post(path+'/searches',json=queries))
        assert len(client.get(path+'/evidence').json())==2
        complete(client.post(path+'/candidate-sets'))
        assert next(s for s in client.get(path+'/overview').json()['stages'] if s['key']=='candidates')['status']=='awaiting_selection'
        candidate=client.get(path+'/candidate-sets').json()[0]['candidates'][0]
        assert client.post('/api/candidates/'+candidate['id']+':select').status_code==200
        plan_id=complete(client.post(path+'/plans'))['plan_id']
        plan=client.get('/api/plans/'+plan_id).json()
        plan['robustness'][-1]['args']={'outcome':'y_alt'}
        assert client.patch('/api/plans/'+plan_id,json=plan).status_code==200
        assert client.post('/api/plans/'+plan_id+':confirm').status_code==200
        frame=synthetic(n_units=60)
        inspected=client.post('/api/datasets:inspect',files={'file':('panel.csv',frame.to_csv(index=False).encode(),'text/csv')}).json()
        dataset=complete(client.post('/api/datasets',json={'upload_id':inspected['upload_id'],'project_id':p,'name':'合成真值面板','columns':list(frame.columns),'unit':'firm','time':'year'}))['dataset_id']
        bound={'dataset_id':dataset,'confirmed':True,'bindings':{name:{'field':field} for name,field in [('patents','y'),('exposure','d'),('firm','firm'),('year','year')]}}
        assert client.put('/api/plans/'+plan_id+'/bindings',json=bound).status_code==200
        assert client.get('/api/plans/'+plan_id+'/readiness').json()['status']=='ready'
        run_id=complete(client.post('/api/plans/'+plan_id+'/runs'))['run_id']
        run=client.get('/api/runs/'+run_id).json()
        assert run['reproduction']['consistent'] and all(s['status']=='succeeded' for s in run['steps'].values())
        claim=client.get('/api/runs/'+run_id+'/claims').json()[0]
        assert client.patch('/api/claims/'+run_id+'/'+claim['claim_id'],json={'user_decision':'accepted','chosen_strength':claim['max_strength'],'final_text':claim['allowed_wording']}).status_code==200
        proposal_id=complete(client.post(path+'/proposals'))['proposal_id']
        before=client.get('/api/proposals/'+proposal_id).json()
        assert before['kind']=='empirical' and not before['stale']
        assert all(s['status']=='completed' for s in client.get(path+'/overview').json()['stages'])
        # A global shared asset has no owner but must invalidate every referencing project.
        from hypoweaver.datasets.models import Dataset
        with app.state.sessions() as db:
            db.get(Dataset,dataset).project_id=None;db.commit()
        client.patch('/api/datasets/'+dataset,json={'source':{'citation':'修改来源核对信息'}})
        assert client.get('/api/runs/'+run_id).json()['stale']
        assert client.get('/api/proposals/'+proposal_id).json()['stale']
        fresh_run=complete(client.post('/api/plans/'+plan_id+'/runs'))['run_id']
        assert not client.get('/api/runs/'+fresh_run).json()['stale']
        changed=client.patch(path,json={'direction':{'text':'改为机制边界问题'}}).json()
        assert {'candidate_sets','study_plans','proposals'}<=set(changed['affected'])
        assert client.get('/api/runs/'+fresh_run).json()['stale']
        states={s['key']:s['status'] for s in client.get(path+'/overview').json()['stages']}
        assert all(states[k]=='stale' for k in ['candidates','plan','proposal'])
        after=client.get('/api/proposals/'+proposal_id).json()
        assert after['sections']==before['sections']
        assert client.get('/api/plans/'+plan_id).json()['stale']
        assert client.get('/api/proposals/'+proposal_id+'.md').status_code==200
        assert client.post(path+'/proposals').status_code==400

import asyncio
import httpx
from fastapi.testclient import TestClient
from hypoweaver.app import create_app
from hypoweaver.config import Settings
from hypoweaver.literature.sources import LiteratureClient


def test_joint_search_deduplicates_and_preserves_source_failure(tmp_path):
    settings = Settings(data_dir=tmp_path)
    state = {'fail':False}

    def respond(request):
        if request.url.host == 'api.openalex.org':
            if state['fail']:
                return httpx.Response(503)
            return httpx.Response(200,json={'results':[{'title':'Carbon Innovation','doi':'https://doi.org/10.123/ABC','publication_year':2024,'abstract_inverted_index':{'green':[0],'innovation':[1]}}]})
        return httpx.Response(200,json={'message':{'items':[{'title':['Carbon Innovation'],'DOI':'10.123/abc','issued':{'date-parts':[[2024]]},'abstract':'<jats:p>green innovation</jats:p>'},{'title':['碳市场与绿色创新'],'DOI':'10.123/xyz','issued':{'date-parts':[[2023]]}}]}})

    app = create_app(settings)
    app.state.literature_client = LiteratureClient(settings, httpx.MockTransport(respond))
    with TestClient(app) as client:
        project_id=client.post('/api/projects',json={'title':'联合调研'}).json()['id']
        path=f'/api/projects/{project_id}'
        for failing in [False,True]:
            state['fail']=failing
            job_id=client.post(path+'/searches',json={'queries':[{'text':'carbon innovation'}]}).json()['job_id']
            async def drain():
                await asyncio.gather(*list(app.state.tasks))
            client.portal.call(drain)
            assert client.get('/api/jobs/'+job_id).json()['status']=='succeeded'
            cards=client.get(path+'/evidence').json()
            assert len(cards)==2
            merged=next(c for c in cards if c['doi']=='10.123/abc')
            assert merged['sources']==['crossref','openalex']
            assert merged['abstract']=='green innovation'
            record=client.get(path+'/searches').json()[0]
            assert record['per_source_status']['openalex']['status']==('failed' if failing else 'ok')
            assert record['per_source_status']['crossref']['status']=='ok'
            if failing:
                assert '503' in record['per_source_status']['openalex']['reason']
        response=client.patch('/api/evidence/'+cards[0]['id'],json={'included':False})
        assert response.json()['included'] is False


def test_empty_search_is_completed_and_interrupted_search_recovers(tmp_path):
    from hypoweaver.literature.models import LiteratureSearch
    settings=Settings(data_dir=tmp_path)
    app=create_app(settings)
    def empty(request):
        return httpx.Response(200,json={'results':[],'message':{'items':[]}})
    app.state.literature_client=LiteratureClient(settings,httpx.MockTransport(empty))
    with TestClient(app) as client:
        p=client.post('/api/projects',json={'title':'空结果'}).json()['id']
        job=client.post(f'/api/projects/{p}/searches',json={'queries':[{'text':'no matches'}]}).json()['job_id']
        async def drain():
            await asyncio.gather(*list(app.state.tasks))
        client.portal.call(drain)
        assert client.get('/api/jobs/'+job).json()['status']=='succeeded'
        assert client.get(f'/api/projects/{p}/searches').json()[0]['status']=='completed'
        with app.state.sessions() as db:
            db.add(LiteratureSearch(project_id=p,queries=[],status='running'))
            db.commit()
    with TestClient(create_app(settings)) as client:
        records=client.get(f'/api/projects/{p}/searches').json()
        assert not any(s['status']=='running' for s in records)
        assert any(s['status']=='failed' and 'system' in s['per_source_status'] for s in records)

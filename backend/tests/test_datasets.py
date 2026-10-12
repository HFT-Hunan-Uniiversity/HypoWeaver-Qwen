import asyncio
import pandas as pd
import pyreadstat
from fastapi.testclient import TestClient
from hypoweaver.app import create_app
from hypoweaver.config import Settings
from hypoweaver.datasets import service


def test_import_csv_excel_stata_selected_columns_and_profiles(tmp_path):
    frame=pd.DataFrame({'firm_id':[1,1,2,2],'year':[2020,2021,2020,2021],'outcome':[1.,None,3.,4.],'unused':[9,8,7,6]})
    csv=tmp_path/'sample.csv'; frame.to_csv(csv,index=False)
    excel=tmp_path/'sample.xlsx'
    with pd.ExcelWriter(excel) as writer:
        frame[['unused']].to_excel(writer,index=False,sheet_name='说明')
        frame.to_excel(writer,index=False,sheet_name='面板')
    stata=tmp_path/'sample.dta'; pyreadstat.write_dta(frame,stata,column_labels={'firm_id':'企业代码','year':'年份','outcome':'结果变量','unused':'不用的字段'})
    app=create_app(Settings(data_dir=tmp_path/'store'))
    with TestClient(app) as client:
        p=client.post('/api/projects',json={'title':'数据验收'}).json()['id']
        for path in [csv,excel,stata]:
            inspected=client.post('/api/datasets:inspect',files={'file':(path.name,path.read_bytes())})
            assert inspected.status_code==200,inspected.text
            info=inspected.json()
            if path==excel:
                assert info['sheets']==['说明','面板']
                info=client.get('/api/dataset-uploads/'+info['upload_id'],params={'sheet':'面板'}).json()
            if path==stata:
                assert next(c for c in info['columns'] if c['name']=='outcome')['label']=='结果变量'
            response=client.post('/api/datasets',json={'upload_id':info['upload_id'],'project_id':p,'name':path.name,'columns':['firm_id','year','outcome'],'sheet':info['sheet'],'source':{'license':'测试数据'}})
            assert response.status_code==200,response.text
            async def drain():
                await asyncio.gather(*list(app.state.tasks))
            client.portal.call(drain)
            job=client.get('/api/jobs/'+response.json()['job_id']).json()
            assert job['status']=='succeeded',job
            dataset=client.get('/api/datasets/'+job['result']['dataset_id']).json()
            assert dataset['n_rows']==4 and dataset['n_cols']==3
            assert 'file_path' not in dataset
            assert dataset['panel']['n_units']==2 and dataset['panel']['n_periods']==2
            assert dataset['panel']['duplicates']==0 and dataset['panel']['balanced'] is True
            profile=next(f for f in dataset['profile'] if f['name']=='outcome')
            assert profile['missing_rate']==.25 and profile['min']==1 and profile['max']==4
            with app.state.sessions() as db:
                imported=service.frame(db,dataset['id'])
                assert len(imported)==4 and 'unused' not in imported
            updated=client.patch('/api/datasets/'+dataset['id'],json={'source':{'doi':'10.123/test','license':'CC BY 4.0'}})
            assert updated.json()['source']['doi']=='10.123/test'
        # Multiple imports can reuse one staged original; there is no permanent ten-file lockout.
        prior=client.get('/api/dataset-uploads').json()
        assert len(prior)==3 and all('file_path' not in x for x in prior)
        for i in range(8):
            assert client.post('/api/datasets:inspect',files={'file':(f'tiny{i}.csv',b'id,year,value\n1,2020,2\n')}).status_code==200
        assert len(client.get('/api/dataset-uploads').json())==11
        assert len(client.get('/api/datasets').json())==3
        assert len(client.get(f'/api/projects/{p}/jobs?kind=dataset').json())==3

import os
os.environ['GIVEAWAY_TOKEN']='test-secret'
from fastapi.testclient import TestClient
from app import main

def test_workflow(tmp_path):
    main.DB=tmp_path/'test.sqlite3'
    with TestClient(main.app) as client:
        assert client.get('/api/health').status_code==200
        assert client.get('/api/giveaways').status_code==401
        headers={'X-Admin-Token':'test-secret'}
        payload={'title':'Тестовий розіграш','source_url':'https://example.org/giveaway/1','tasks':['Підписатися','Натиснути кнопку']}
        r=client.post('/api/giveaways',json=payload,headers=headers)
        assert r.status_code==201,r.text
        assert client.post('/api/giveaways',json=payload,headers=headers).status_code==409
        items=client.get('/api/giveaways',headers=headers).json()
        assert len(items)==1 and len(items[0]['tasks'])==2
        task_id=items[0]['tasks'][0]['id']
        assert client.patch(f'/api/tasks/{task_id}/progress',json={'completed':True},headers=headers).status_code==200
        assert client.patch(f"/api/giveaways/{items[0]['id']}/status",json={'status':'ENTERED'},headers=headers).status_code==200
        item=client.get('/api/giveaways',headers=headers).json()[0]
        assert item['tasks'][0]['completed']==1
        assert item['participation_status']=='ENTERED'

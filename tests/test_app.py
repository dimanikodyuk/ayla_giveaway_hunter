import os
os.environ['AUTH_MODE']='local'
from fastapi.testclient import TestClient
from app import main
from app.engine import analyze,normalize_url

def test_workflow(tmp_path):
    main.DB=tmp_path/'test.sqlite3'
    with TestClient(main.app,client=('127.0.0.1',1234)) as client:
        assert client.get('/api/health').status_code==200
        assert client.get('/').status_code==200
        data={'title':'Тестовий розіграш','source_url':'t.me/test_channel/12','tasks':['Підписатися','Натиснути кнопку']}
        r=client.post('/api/giveaways',json=data);assert r.status_code==201,r.text
        assert client.post('/api/giveaways',json=data).status_code==409
        items=client.get('/api/giveaways').json();assert len(items)==1
        assert items[0]['source_url']=='https://t.me/test_channel/12'
        assert client.patch('/api/tasks/'+str(items[0]['tasks'][0]['id'])+'/progress',json={'completed':True}).status_code==200
        assert client.patch('/api/giveaways/'+str(items[0]['id'])+'/status',json={'status':'ENTERED'}).status_code==200
        assert client.get('/api/giveaways').json()[0]['tasks'][0]['completed']==1
        assert client.post('/api/sources',json={'type':'telegram','title':'Test','url':'t.me/test_channel'}).status_code==201
        assert len(client.get('/api/sources').json())==1
        assert client.get('/api/diagnostics').json()['giveaways']==1
    with TestClient(main.app,client=('127.0.0.1',1234)) as client:
        assert len(client.get('/api/giveaways').json())==1

def test_classifier():
    assert analyze('Розіграш навушників! Підписатися на канал')['candidate']
    assert analyze('Giveaway! deposit required')['review_status']=='REJECTED'
    assert not analyze('Погода сьогодні сонячна')['candidate']

def test_auth_rejects_non_loopback(tmp_path):
    main.DB=tmp_path/'test.sqlite3'
    with TestClient(main.app,client=('192.168.1.5',1234)) as client:
        assert client.get('/api/giveaways').status_code==401

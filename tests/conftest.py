import os, re, sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import main
from app.models import Base

@pytest.fixture
def env(tmp_path, monkeypatch):
    engine=create_engine(f'sqlite:///{tmp_path}/test.db',connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine,expire_on_commit=False)
    monkeypatch.setattr(main,'Factory',factory)
    main.app.state.outbox.clear()
    monkeypatch.setenv('MAIL_MODE','log')
    c=TestClient(main.app)
    def login(email,name=None):
        c.post('/api/auth/request',json={'email':email}).raise_for_status()
        mail=main.app.state.outbox[-1]['body']
        token=re.search(r'\?login=([A-Za-z0-9_-]+)',mail).group(1)
        r=c.post('/api/auth/consume',json={'token':token});r.raise_for_status()
        c.cookies.set('giftcircle_session',r.cookies['giftcircle_session'])
        if name:c.patch('/api/me',json={'name':name,'notify_email':True}).raise_for_status()
        return c.get('/api/me').json()
    def invite(fid,email):
        r=c.post(f'/api/families/{fid}/invites',json={'email':email});r.raise_for_status()
        return re.search(r'\?invite=([A-Za-z0-9_-]+)',main.app.state.outbox[-1]['body']).group(1)
    def accept(token,email,name):
        user=login(email,name)
        r=c.post('/api/invites/accept',json={'token':token});r.raise_for_status()
        return user
    return c,login,invite,accept,factory

@pytest.fixture
def group(env):
    c,login,invite,accept,factory=env
    alice=login('alice@example.com','Alice')
    f=c.post('/api/families',json={'name':'The Family'}).json()['id']
    token_b=invite(f,'bob@example.com')
    token_c=invite(f,'carol@example.com')
    bob=accept(token_b,'bob@example.com','Bob')
    carol=accept(token_c,'carol@example.com','Carol')
    login('alice@example.com')
    eid=c.post(f'/api/families/{f}/exchanges',json={'name':'Christmas 2026','budget':50,'exchange_date':'2026-12-25'}).json()['id']
    return {'c':c,'login':login,'invite':invite,'accept':accept,'factory':factory,'family':f,'eid':eid,'alice':alice,'bob':bob,'carol':carol}

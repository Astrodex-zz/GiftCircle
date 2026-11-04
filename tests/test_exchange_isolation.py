from sqlalchemy import select
from app.models import Assignment

def test_lists_and_mutations_are_exchange_scoped(group):
    g=group;c=g['c'];first=g['eid'];alice=g['alice']['id'];bob=g['bob']['id'];carol=g['carol']['id']
    second=c.post(f'/api/families/{g["family"]}/exchanges',json={'name':'Birthday exchange','exchange_date':'2027-06-01'}).json()['id']
    c.put(f'/api/exchanges/{first}/reservation-settings',json={'mode':'surprise'}).raise_for_status()
    wishes={}
    for person in ('alice','bob','carol'):
        g['login'](person+'@example.com')
        for eid in (first,second):
            wid=c.post(f'/api/exchanges/{eid}/wishes',json={'title':f'{person} gift for {eid}'}).json()['id']
            wishes[eid,person]=wid
        uid=g[person]['id']
        for eid in (first,second):
            assert [w['id'] for w in c.get(f'/api/exchanges/{eid}/wishes/{uid}').json()]==[wishes[eid,person]]
    g['login']('alice@example.com')
    # Force different recipients in the two exchanges without exposing assignments.
    for eid,blocked in ((first,carol),(second,bob)):
        assert c.put(f'/api/exchanges/{eid}/exclusions',json={'pairs':[{'giver_id':alice,'recipient_id':blocked}]}).status_code==200
        assert c.post(f'/api/exchanges/{eid}/draw').status_code==200
    for eid,recipient,other in ((first,bob,carol),(second,carol,bob)):
        detail=c.get(f'/api/exchanges/{eid}').json()
        assert detail['my_assignment']['recipient_id']==recipient
        assert c.get(f'/api/exchanges/{eid}/wishes/{other}').status_code==403
        name='bob' if recipient==bob else 'carol'
        rows=c.get(f'/api/exchanges/{eid}/wishes/{recipient}').json()
        assert [w['id'] for w in rows]==[wishes[eid,name]]
    wrong=wishes[first,'bob']
    for action in ('reserve','purchase'):
        assert c.post(f'/api/exchanges/{second}/wishes/{wrong}/{action}').status_code==404
    assert c.delete(f'/api/exchanges/{second}/wishes/{wishes[first,"alice"]}').status_code==404
    assert c.delete(f'/api/exchanges/{first}/wishes/{wrong}').status_code==403
    # Reservations and purchases affect only the chosen exchange.
    assert c.post(f'/api/exchanges/{first}/wishes/{wrong}/reserve').status_code==200
    assert c.post(f'/api/exchanges/{first}/wishes/{wrong}/purchase').status_code==200
    assert not c.get(f'/api/exchanges/{second}/wishes/{carol}').json()[0]['reserved']
    assignment=c.get(f'/api/exchanges/{first}').json()['my_assignment']['assignment_id']
    assert c.get(f'/api/exchanges/{second}/messages/{assignment}').status_code==404
    assert c.post(f'/api/exchanges/{second}/messages/{assignment}',json={'content':'Wrong exchange'}).status_code==404
    assert c.post(f'/api/exchanges/{first}/group-messages',json={'content':'Only first exchange'}).status_code==200
    assert c.get(f'/api/exchanges/{second}/group-messages').json()==[]
    g['login']('bob@example.com')
    # Owners cannot infer reservation status from the list OR from deletion errors.
    own=c.get(f'/api/exchanges/{first}/wishes/{bob}').json()[0]
    assert 'reserved' not in own and 'purchased_by_me' not in own
    assert c.delete(f'/api/exchanges/{first}/wishes/{wrong}').status_code==200
    assert c.delete(f'/api/exchanges/{second}/wishes/{wishes[second,"bob"]}').status_code==200
    g['login']('outsider@example.com')
    assert c.get(f'/api/exchanges/{first}').status_code==404
    assert c.get(f'/api/exchanges/{first}/wishes/{alice}').status_code==404

def test_request_security_and_smtp_capture(env,monkeypatch):
    from app import main
    c,login,*_=env
    assert c.post('/api/auth/request',json={'email':'test@example.com'},headers={'Origin':'https://untrusted.example'}).status_code==403
    login('test@example.com')
    assert c.get('/api/me').headers['cache-control']=='no-store'
    assert c.get('/').headers['referrer-policy']=='no-referrer'
    monkeypatch.setenv('MAIL_MODE','smtp')
    monkeypatch.setenv('SMTP_HOST','')
    before=len(main.app.state.outbox)
    import pytest
    with pytest.raises(RuntimeError):main.email_send('test@example.com','Test','Private token')
    assert len(main.app.state.outbox)==before

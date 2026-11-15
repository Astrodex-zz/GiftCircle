import re
from datetime import timedelta
from fastapi.testclient import TestClient
from sqlalchemy import select
from app import main
from app.models import Assignment, Message, MessageReadState, RevealAccess, RevealToken, utcnow


def overview(c,eid):
    r=c.get(f'/api/exchanges/{eid}/organiser-overview');r.raise_for_status()
    return r.json()['participants']


def test_organiser_only_status_and_unread_match_each_participant(group):
    g=group;c=g['c'];eid=g['eid']
    # No private channels exist before the draw; group chat already works.
    assert all(p['unread']=={'giver':None,'santa':None,'group':0} for p in overview(c,eid))
    c.post(f'/api/exchanges/{eid}/draw').raise_for_status()
    for name in ('alice','bob','carol'):
        g['login'](g[name]['email'])
        c.post(f'/api/exchanges/{eid}/wishes',json={'title':'PRIVATE-GIFT-'+name,'details':'PRIVATE-NOTE'}).raise_for_status()
    c.post(f'/api/exchanges/{eid}/wish-list/finalise').raise_for_status()
    with g['factory']() as s:
        assignments=list(s.scalars(select(Assignment).where(Assignment.exchange_id==eid)))
        for a in assignments:
            s.add_all([Message(exchange_id=eid,assignment_id=a.id,sender_id=a.giver_id,kind='private',content='PRIVATE-MESSAGE'),Message(exchange_id=eid,assignment_id=a.id,sender_id=a.recipient_id,kind='private',content='PRIVATE-REPLY')])
        s.add(Message(exchange_id=eid,sender_id=g['alice']['id'],kind='group',content='PRIVATE-GROUP'))
        s.flush()
        incoming=next(a for a in assignments if a.recipient_id==g['bob']['id'])
        mid=s.scalar(select(Message.id).where(Message.assignment_id==incoming.id,Message.sender_id!=g['bob']['id']))
        s.add(MessageReadState(exchange_id=eid,user_id=g['bob']['id'],channel='santa',last_message_id=mid))
        s.commit()
    expected={}
    for name in ('alice','bob','carol'):
        g['login'](g[name]['email'])
        expected[g[name]['id']]=c.get('/api/messages/unread').json()['exchanges'][str(eid)]
        if name!='alice':assert c.get(f'/api/exchanges/{eid}/organiser-overview').status_code==403
    g['login']('alice@example.com')
    rows=overview(c,eid)
    for row in rows:
        assert set(row)=={'id','name','reveal_used','wish_count','list_status','unread'}
        assert set(row['unread'])=={'giver','santa','group'}
        assert row['unread']=={k:expected[row['id']][k] for k in ('giver','santa','group')}
        assert row['wish_count']==1
        assert row['list_status']==('finalised' if row['id']==g['carol']['id'] else 'draft')
    assert 'PRIVATE-' not in str(rows)
    other=c.post(f"/api/families/{g['family']}/exchanges",json={'name':'Separate exchange'}).json()['id']
    assert all(p['wish_count']==0 and p['list_status']=='draft' and not p['reveal_used'] for p in overview(c,other))
    g['login']('carol@example.com')
    c.post(f'/api/exchanges/{eid}/wishes',json={'title':'Edited list'}).raise_for_status()
    g['login']('alice@example.com')
    assert next(p for p in overview(c,eid) if p['id']==g['carol']['id'])['list_status']=='draft'
    g['login']('outsider@example.com')
    assert c.get(f'/api/exchanges/{eid}/organiser-overview').status_code==404
    c.post('/api/auth/logout')
    assert c.get(f'/api/exchanges/{eid}/organiser-overview').status_code==401


def test_reveal_use_recorded_only_on_success_and_is_idempotent(group):
    g=group;c=g['c'];eid=g['eid']
    c.post(f'/api/exchanges/{eid}/draw').raise_for_status()
    links={m['to']:re.search(r'#reveal=([A-Za-z0-9_-]+)',m['body']).group(1) for m in main.app.state.outbox if '#reveal=' in m['body']}
    assert not any(p['reveal_used'] for p in overview(c,eid))
    # Viewing the signed-in exchange is not the same as using a reveal link.
    c.get(f'/api/exchanges/{eid}').raise_for_status()
    anon=TestClient(main.app)
    assert anon.post('/api/reveal',json={'token':'x'*43}).status_code==404
    with g['factory']() as s:
        token=s.scalar(select(RevealToken).where(RevealToken.digest==main.digest(links['carol@example.com'])))
        token.expires_at=utcnow()-timedelta(seconds=1);s.commit()
    assert anon.post('/api/reveal',json={'token':links['carol@example.com']}).status_code==404
    for _ in range(2):anon.post('/api/reveal',json={'token':links['bob@example.com']}).raise_for_status()
    rows=overview(c,eid)
    assert {p['id'] for p in rows if p['reveal_used']}=={g['bob']['id']}
    with g['factory']() as s:assert len(list(s.scalars(select(RevealAccess))))==1
    assert anon.get('/api/me').status_code==401
    c.delete(f'/api/exchanges/{eid}').raise_for_status()
    with g['factory']() as s:assert not list(s.scalars(select(RevealAccess)))


def test_group_deletion_cleans_reveal_activity(group):
    g=group;c=g['c'];eid=g['eid']
    with g['factory']() as s:
        s.add(RevealAccess(exchange_id=eid,user_id=g['alice']['id']));s.commit()
    c.delete(f"/api/families/{g['family']}").raise_for_status()
    with g['factory']() as s:assert not list(s.scalars(select(RevealAccess)))

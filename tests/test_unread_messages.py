from sqlalchemy import select
from app.models import Assignment, MessageReadState


def counts(c,eid):
    r=c.get('/api/messages/unread');r.raise_for_status()
    return r.json()['exchanges'].get(str(eid),{'giver':0,'santa':0,'group':0,'total':0})


def test_unread_is_per_user_channel_and_exchange(group):
    g=group;c=g['c'];eid=g['eid']
    c.post(f'/api/exchanges/{eid}/draw').raise_for_status()
    with g['factory']() as s:
        outgoing=s.scalar(select(Assignment).where(Assignment.exchange_id==eid,Assignment.giver_id==g['alice']['id']))
        incoming=s.scalar(select(Assignment).where(Assignment.exchange_id==eid,Assignment.recipient_id==g['alice']['id']))
    emails={g[k]['id']:g[k]['email'] for k in ['alice','bob','carol']}
    g['login'](emails[outgoing.recipient_id])
    c.post(f'/api/exchanges/{eid}/messages/{outgoing.id}',json={'content':'A reply from my recipient'}).raise_for_status()
    g['login'](emails[incoming.giver_id])
    c.post(f'/api/exchanges/{eid}/messages/{incoming.id}',json={'content':'A question from my giver'}).raise_for_status()
    c.post(f'/api/exchanges/{eid}/group-messages',json={'content':'Hello group'}).raise_for_status()
    g['login']('alice@example.com')
    c.post(f'/api/exchanges/{eid}/group-messages',json={'content':'My own message'}).raise_for_status()
    assert counts(c,eid)=={'giver':1,'santa':1,'group':1,'total':3}
    # Reading via GET alone (prefetch, background tab) must not clear anything.
    outgoing_messages=c.get(f'/api/exchanges/{eid}/messages/{outgoing.id}').json()['messages']
    assert counts(c,eid)['total']==3
    mid=outgoing_messages[-1]['id']
    c.post(f'/api/exchanges/{eid}/messages/read/giver',json={'through_id':mid}).raise_for_status()
    assert counts(c,eid)=={'giver':0,'santa':1,'group':1,'total':2}
    # A new login retains the server-side read position.
    c.post('/api/auth/logout');g['login']('alice@example.com')
    assert counts(c,eid)['giver']==0
    other=c.post(f"/api/families/{g['family']}/exchanges",json={'name':'Another exchange'}).json()['id']
    assert counts(c,other)['total']==0
    g['login']('outsider@example.com')
    assert c.get('/api/messages/unread').json()=={'total':0,'exchanges':{}}
    assert c.post(f'/api/exchanges/{eid}/messages/read/giver',json={'through_id':mid}).status_code in (403,404)
    c.post('/api/auth/logout')
    assert c.get('/api/messages/unread').status_code==401


def test_read_cursor_does_not_skip_new_messages_or_move_backwards(group):
    g=group;c=g['c'];eid=g['eid']
    g['login']('bob@example.com')
    c.post(f'/api/exchanges/{eid}/group-messages',json={'content':'First'}).raise_for_status()
    g['login']('alice@example.com')
    first=c.get(f'/api/exchanges/{eid}/group-messages').json()[-1]['id']
    g['login']('bob@example.com')
    c.post(f'/api/exchanges/{eid}/group-messages',json={'content':'Arrived after fetch'}).raise_for_status()
    g['login']('alice@example.com')
    second=c.get(f'/api/exchanges/{eid}/group-messages').json()[-1]['id']
    endpoint=f'/api/exchanges/{eid}/messages/read/group'
    c.post(endpoint,json={'through_id':first}).raise_for_status()
    assert counts(c,eid)['group']==1
    c.post(endpoint,json={'through_id':second}).raise_for_status()
    c.post(endpoint,json={'through_id':first}).raise_for_status()
    assert counts(c,eid)['total']==0
    assert c.post(endpoint,json={'through_id':second+1000}).status_code==404
    assert c.post(endpoint,json={'through_id':0}).status_code==422
    assert c.post(f'/api/exchanges/{eid}/messages/read/giver',json={'through_id':first}).status_code==404
    assert c.post(f'/api/exchanges/{eid}/messages/read/invalid',json={'through_id':first}).status_code==422
    # Another reader's state is independent, and announcements count as group messages.
    c.post(f'/api/exchanges/{eid}/announcements',json={'content':'Announcement'}).raise_for_status()
    g['login']('carol@example.com')
    assert counts(c,eid)['group']==3


def test_read_receipts_are_cleaned_with_exchange_and_group(group):
    g=group;c=g['c'];eid=g['eid'];fid=g['family']
    ids=[eid,c.post(f'/api/families/{fid}/exchanges',json={'name':'Second event'}).json()['id']]
    for event in ids:
        c.post(f'/api/exchanges/{event}/group-messages',json={'content':'Hello'}).raise_for_status()
        mid=c.get(f'/api/exchanges/{event}/group-messages').json()[-1]['id']
        c.post(f'/api/exchanges/{event}/messages/read/group',json={'through_id':mid}).raise_for_status()
    c.delete(f'/api/exchanges/{eid}').raise_for_status()
    with g['factory']() as s:assert [r.exchange_id for r in s.scalars(select(MessageReadState))]==[ids[1]]
    c.delete(f'/api/families/{fid}').raise_for_status()
    with g['factory']() as s:assert list(s.scalars(select(MessageReadState)))==[]


def test_cannot_acknowledge_another_conversation_or_exchange(group):
    g=group;c=g['c'];eid=g['eid']
    c.post(f'/api/exchanges/{eid}/draw').raise_for_status()
    aid=c.get(f'/api/exchanges/{eid}').json()['my_assignment']['assignment_id']
    c.post(f'/api/exchanges/{eid}/messages/{aid}',json={'content':'Private'}).raise_for_status()
    mid=c.get(f'/api/exchanges/{eid}/messages/{aid}').json()['messages'][-1]['id']
    assert c.post(f'/api/exchanges/{eid}/messages/read/santa',json={'through_id':mid}).status_code==404
    assert c.post(f'/api/exchanges/{eid}/messages/read/group',json={'through_id':mid}).status_code==404
    other=c.post(f"/api/families/{g['family']}/exchanges",json={'name':'Second event'}).json()['id']
    assert c.post(f'/api/exchanges/{other}/messages/read/group',json={'through_id':mid}).status_code==404

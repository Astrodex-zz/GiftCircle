import re
from datetime import timedelta
from app.models import Assignment, Session, Wish, AuthToken, utcnow
from app import main
from sqlalchemy import select

def test_complete_journey(group):
 g=group;c=g['c'];eid=g['eid'];alice=g['alice'];bob=g['bob'];carol=g['carol']
 c.put(f'/api/exchanges/{eid}/reservation-settings',json={'mode':'surprise'}).raise_for_status()
 assert c.get('/api/exchanges').json()[0]['name']=='Christmas 2026'
 # Each person creates a wish before the draw.
 for name,email in [('Alice','alice@example.com'),('Bob','bob@example.com'),('Carol','carol@example.com')]:
  g['login'](email)
  r=c.post(f'/api/exchanges/{eid}/wishes',json={'title':f'{name} gift','details':'Something thoughtful','url':'https://example.com/item','price':'$20'})
  assert r.status_code==200,r.text
 g['login']('alice@example.com')
 r=c.post(f'/api/exchanges/{eid}/exclusions',json={'giver_id':alice['id'],'recipient_id':bob['id']}); assert r.status_code==200
 r=c.post(f'/api/exchanges/{eid}/draw');assert r.status_code==200,r.text
 assert r.json()['count']==3
 # All three have different recipients, the exclusion is enforced.
 with g['factory']() as s:
  assignments=s.scalars(select(Assignment).where(Assignment.exchange_id==eid)).all()
  assert len(assignments)==3
  assert {a.giver_id for a in assignments}=={a.recipient_id for a in assignments}
  assert all(a.giver_id!=a.recipient_id for a in assignments)
  assert not any(a.giver_id==alice['id'] and a.recipient_id==bob['id'] for a in assignments)
 # Nobody, even the organiser, sees all assignments through exchange detail.
 alice_view=c.get(f'/api/exchanges/{eid}').json()
 assert 'assignments' not in alice_view and 'exclusions' in alice_view
 assert len(alice_view['exclusions'])==0
 own=alice_view['my_assignment'];recipient_id=own['recipient_id']
 r=c.get(f'/api/exchanges/{eid}/wishes/{recipient_id}');assert r.status_code==200
 wid=r.json()[0]['id'];assert not r.json()[0]['reserved']
 r=c.post(f'/api/exchanges/{eid}/wishes/{wid}/reserve');assert r.status_code==200
 r=c.post(f'/api/exchanges/{eid}/wishes/{wid}/purchase');assert r.json()['purchased']
 a_id=own['assignment_id']
 r=c.post(f'/api/exchanges/{eid}/messages/{a_id}',json={'content':'Would you prefer blue or red?'});assert r.status_code==200
 # Receiver can respond, but does not learn the giver's identity.
 rec_email={alice['id']:'alice@example.com',bob['id']:'bob@example.com',carol['id']:'carol@example.com'}[recipient_id]
 g['login'](rec_email)
 rv=c.get(f'/api/exchanges/{eid}').json()
 assert rv['my_santa_conversation']==a_id
 assert 'Alice' not in str(rv['my_santa_conversation'])
 msg=c.get(f'/api/exchanges/{eid}/messages/{a_id}').json()
 assert msg['label']=='Your Mystery Gifter'
 assert msg['messages'][0]['content']=='Would you prefer blue or red?'
 assert msg['messages'][0]['mine'] is False
 assert 'sender_id' not in str(msg)
 c.post(f'/api/exchanges/{eid}/messages/{a_id}',json={'content':'Blue would be lovely!'}).raise_for_status()
 own_wishes=c.get(f'/api/exchanges/{eid}/wishes/{recipient_id}').json()
 assert 'reserved' not in str(own_wishes)
 # Full two-way message round trip, notifications remain anonymous.
 g['login']('alice@example.com')
 m=c.get(f'/api/exchanges/{eid}/messages/{a_id}').json()['messages']
 assert [x['mine'] for x in m]==[True,False]
 emails=[m for m in main.app.state.outbox if m['subject']=='New anonymous message']
 assert emails and all('sender' not in em['body'].lower() and 'Alice' not in em['body'] for em in emails)
 # Another unrelated participant cannot snoop into this thread.
 outsider=next(x for x in (alice,bob,carol) if x['id'] not in (alice['id'],recipient_id))
 g['login'](outsider['email'])
 assert c.get(f'/api/exchanges/{eid}/messages/{a_id}').status_code==403
 assert c.get(f'/api/exchanges/{eid}/wishes/{recipient_id}').status_code==403
 assert c.post(f'/api/exchanges/{eid}/wishes/{wid}/reserve').status_code==403

def test_login_one_use_expiry_and_logout(env):
 c,login,_,_,factory=env
 c.post('/api/auth/request',json={'email':'test@example.com'}).raise_for_status()
 token=re.search(r'\?login=([A-Za-z0-9_-]+)',main.app.state.outbox[-1]['body']).group(1)
 assert c.post('/api/auth/consume',json={'token':token}).status_code==200
 assert c.post('/api/auth/consume',json={'token':token}).status_code==400
 c.post('/api/auth/request',json={'email':'test@example.com'}).raise_for_status()
 token2=re.search(r'\?login=([A-Za-z0-9_-]+)',main.app.state.outbox[-1]['body']).group(1)
 with factory() as s:
  t=s.scalar(select(AuthToken).where(AuthToken.digest==main.digest(token2)));t.expires_at=utcnow()-timedelta(minutes=1);s.commit()
 assert c.post('/api/auth/consume',json={'token':token2}).status_code==400
 login('test@example.com');assert c.get('/api/me').status_code==200
 c.post('/api/auth/logout',json={}).raise_for_status();assert c.get('/api/me').status_code==401

def test_invitation_bound_to_email_and_no_duplicate_join(env):
 c,login,invite,accept,factory=env
 login('admin@example.com','Admin');fid=c.post('/api/families',json={'name':'Welcome'}).json()['id']
 token=invite(fid,'target@example.com')
 login('attacker@example.com','Attacker')
 assert c.post('/api/invites/accept',json={'token':token}).status_code==403
 accept(token,'target@example.com','Target')
 assert c.post('/api/invites/accept',json={'token':token}).status_code==400
 assert len(c.get(f'/api/families/{fid}').json()['members'])==2

def test_impossible_exclusion_cannot_draw(group):
 g=group;c=g['c'];eid=g['eid'];a=g['alice'];b=g['bob'];d=g['carol']
 for giver in [a,b,d]:
  for recip in [a,b,d]:
   if giver['id']!=recip['id']:
    r=c.post(f'/api/exchanges/{eid}/exclusions',json={'giver_id':giver['id'],'recipient_id':recip['id']})
    assert r.status_code==200
 assert c.post(f'/api/exchanges/{eid}/draw').status_code==422
 assert not c.get(f'/api/exchanges/{eid}').json()['drawn']

def test_permissions_announcements_and_urls(group):
 g=group;c=g['c'];eid=g['eid'];fid=g['family']
 g['login']('bob@example.com')
 assert c.post(f'/api/exchanges/{eid}/draw').status_code==403
 assert c.post(f'/api/exchanges/{eid}/announcements',json={'content':'Hi'}).status_code==403
 assert c.post(f'/api/families/{fid}/invites',json={'email':'x@example.com'}).status_code==403
 assert c.post(f'/api/exchanges/{eid}/wishes',json={'title':'bad','url':'javascript:alert(1)'}).status_code==400
 assert c.post(f'/api/exchanges/{eid}/group-messages',json={'content':'Hello group!'}).status_code==200
 g['login']('alice@example.com')
 assert c.post(f'/api/exchanges/{eid}/announcements',json={'content':'Please add your lists'}).status_code==200
 m=c.get(f'/api/exchanges/{eid}/group-messages').json()
 assert [x['kind'] for x in m]==['group','announcement']
 g['login']('bob@example.com')
 assert any(n['title'].startswith('Announcement') for n in c.get('/api/notifications').json())
 # Recipients can never list member wishes outside their own assignment.
 assert c.get(f'/api/exchanges/{eid}/wishes/{g["carol"]["id"]}').status_code==403

def test_late_invitee_before_draw_and_rejected_after_draw(group):
 g=group;c=g['c'];eid=g['eid'];fid=g['family'];g['login']('alice@example.com')
 token=g['invite'](fid,'dan@example.com')
 dan=g['accept'](token,'dan@example.com','Dan')
 assert len(c.get(f'/api/exchanges/{eid}').json()['participants'])==4
 g['login']('alice@example.com')
 assert c.post(f'/api/exchanges/{eid}/draw').status_code==200
 token=g['invite'](fid,'eve@example.com')
 g['accept'](token,'eve@example.com','Eve')
 # Eve is in the family but not included in already drawn exchanges.
 assert c.get('/api/exchanges').json()==[]
 assert c.get(f'/api/exchanges/{eid}').status_code==403


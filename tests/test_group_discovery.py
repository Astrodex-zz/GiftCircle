def test_groups_visible_without_exchanges(env):
    c,login,invite,accept,factory=env
    login('owner@example.com')
    a=c.post('/api/families',json={'name':'First group'}).json()['id']
    b=c.post('/api/families',json={'name':'Second group'}).json()['id']
    assert {x['id'] for x in c.get('/api/families').json()}=={a,b}
    assert c.get('/api/exchanges').json()==[]

def test_invitation_survives_fresh_sign_in_and_clears_pending(env):
    c,login,invite,accept,factory=env
    login('owner@example.com')
    fid=c.post('/api/families',json={'name':'Our group'}).json()['id']
    invite(fid,'guest@example.com')
    invite(fid,'guest@example.com')
    login('stranger@example.com')
    assert c.get('/api/invites').json()==[]
    login('guest@example.com')
    invitations=c.get('/api/invites').json()
    assert len(invitations)==2
    iid=invitations[0]['id']
    login('stranger@example.com')
    assert c.post(f'/api/invites/{iid}/accept',json={}).status_code==404
    login('guest@example.com')
    assert c.post(f'/api/invites/{iid}/accept',json={}).status_code==200
    assert c.post(f'/api/invites/{iid}/accept',json={}).status_code==200
    assert c.get('/api/invites').json()==[]
    assert c.get('/api/families').json()[0]['id']==fid
    login('owner@example.com')
    detail=c.get(f'/api/families/{fid}').json()
    assert detail['pending']==[]
    assert len(detail['members'])==2

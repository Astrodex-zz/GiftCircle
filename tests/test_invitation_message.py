from app import main


def test_custom_invitation_and_exchange_validation(env):
    c,login,invite,accept,_=env
    login('owner@example.com','Organiser')
    fid=c.post('/api/families',json={'name':'Game night'}).json()['id']
    message='Bring your best shark costume!\nGifts after laser tag.'
    eid=c.post(f'/api/families/{fid}/exchanges',json={'name':'Tag the shark','invitation_message':message}).json()['id']
    assert c.get('/api/exchanges').json()[0]['invitation_message']==message
    response=c.post(f'/api/families/{fid}/invites',json={'email':'guest@example.com','exchange_id':eid})
    assert response.status_code==200
    mail=main.app.state.outbox[-1]['body']
    assert message in mail and 'Tag the shark' in mail and '?invite=' in mail
    assert 'Organiser invited you to join' not in mail
    other=c.post('/api/families',json={'name':'Different group'}).json()['id']
    assert c.post(f'/api/families/{other}/invites',json={'email':'other@example.com','exchange_id':eid}).status_code==400
    token=invite(fid,'member@example.com')
    accept(token,'member@example.com','Member')
    assert c.post(f'/api/families/{fid}/invites',json={'email':'other@example.com','exchange_id':eid}).status_code==403
    login('owner@example.com')
    assert c.delete(f'/api/families/{fid}').status_code==200

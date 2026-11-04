from sqlalchemy import select,func
from app.models import (Exchange,Membership,Invitation,Participant,Wish,WishListState,WishAvailability,ReservationPolicy,ExchangeInvitationText,Assignment,Message,Notification,Exclusion,PreviousDrawRule,User)


def test_deleting_group_cleans_every_exchange_and_revokes_all_members(group):
    g=group;c=g['c'];fid=g['family'];first=g['eid'];alice=g['alice']['id']
    wid=c.post(f'/api/exchanges/{first}/wishes',json={'title':'A book'}).json()['id']
    c.post(f'/api/exchanges/{first}/wishes/{wid}/availability').raise_for_status()
    c.post(f'/api/exchanges/{first}/wish-list/finalise').raise_for_status()
    c.put(f'/api/exchanges/{first}/reservation-settings',json={'mode':'show'}).raise_for_status()
    c.post(f'/api/exchanges/{first}/draw').raise_for_status()
    aid=c.get(f'/api/exchanges/{first}').json()['my_assignment']['assignment_id']
    c.post(f'/api/exchanges/{first}/messages/{aid}',json={'content':'Private hello'}).raise_for_status()
    c.post(f'/api/exchanges/{first}/group-messages',json={'content':'Group hello'}).raise_for_status()
    second=c.post(f'/api/families/{fid}/exchanges',json={'name':'Next year','exchange_date':'2027-12-25','invitation_message':'Join us!'}).json()['id']
    c.put(f'/api/exchanges/{second}/exclusions',json={'previous_draw_id':first,'pairs':[{'giver_id':alice,'recipient_id':g['bob']['id']}]}).raise_for_status()
    old_token=g['invite'](fid,'pending@example.com')
    keep=c.post('/api/families',json={'name':'Unrelated group'}).json()['id']
    kept_exchange=c.post(f'/api/families/{keep}/exchanges',json={'name':'Keep exchange'}).json()['id']
    c.delete(f'/api/families/{fid}').raise_for_status()
    for email in ['alice@example.com','bob@example.com','carol@example.com']:
        g['login'](email)
        assert fid not in [f['id'] for f in c.get('/api/families').json()]
        assert not {first,second}&{e['id'] for e in c.get('/api/exchanges').json()}
        assert c.get(f'/api/families/{fid}').status_code==404
        for eid in [first,second]:
            assert c.get(f'/api/exchanges/{eid}').status_code==404
            assert c.get(f'/api/exchanges/{eid}/wishes/{alice}').status_code==404
            assert c.post(f'/api/exchanges/{eid}/group-messages',json={'content':'Gone'}).status_code==404
        assert not c.get('/api/notifications').json()
        assert c.get('/api/me').status_code==200
    g['login']('pending@example.com')
    assert c.get('/api/invites').json()==[]
    assert c.post('/api/invites/accept',json={'token':old_token}).status_code==400
    with g['factory']() as s:
        for model in [Participant,Wish,WishListState,WishAvailability,ReservationPolicy,ExchangeInvitationText,Assignment,Message,Notification,Exclusion,PreviousDrawRule]:
            assert s.scalar(select(func.count()).select_from(model).where(model.exchange_id.in_([first,second])))==0,model.__name__
        for model in [Exchange,Membership,Invitation]:
            assert s.scalar(select(func.count()).select_from(model).where(model.family_id==fid))==0
        assert s.get(Exchange,kept_exchange)
        assert s.get(User,alice)


def test_blank_inputs_and_invalid_calendar_dates(group):
    g=group;c=g['c'];eid=g['eid'];fid=g['family']
    assert c.post('/api/families',json={'name':'   '}).status_code==422
    assert c.post(f'/api/families/{fid}/exchanges',json={'name':'   '}).status_code==422
    assert c.post(f'/api/families/{fid}/exchanges',json={'name':'Invalid date','exchange_date':'2027-02-30'}).status_code==400
    assert c.post(f'/api/exchanges/{eid}/wishes',json={'title':'   '}).status_code==422
    assert c.post(f'/api/exchanges/{eid}/group-messages',json={'content':'   '}).status_code==422

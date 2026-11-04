from sqlalchemy import select
from app.models import Assignment,Notification,WishListState

def test_finalise_after_draw_notifies_only_giver_once_and_edits_reset(group):
    g=group;c=g['c'];eid=g['eid'];owner=g['alice']['id']
    assert c.post(f'/api/exchanges/{eid}/wish-list/finalise',json={}).status_code==400
    wish=c.post(f'/api/exchanges/{eid}/wishes',json={'title':'Book'}).json()['id']
    c.post(f'/api/exchanges/{eid}/draw',json={}).raise_for_status()
    c.post(f'/api/exchanges/{eid}/wish-list/finalise',json={}).raise_for_status()
    c.post(f'/api/exchanges/{eid}/wish-list/finalise',json={}).raise_for_status()
    with g['factory']() as s:
        giver=s.scalar(select(Assignment).where(Assignment.exchange_id==eid,Assignment.recipient_id==owner)).giver_id
        notes=s.scalars(select(Notification).where(Notification.title=='Your recipient’s wish list is finalised')).all()
        assert len(notes)==1 and notes[0].user_id==giver
    assert c.get(f'/api/exchanges/{eid}/wish-list/{owner}').json()['status']=='finalised'
    c.post(f'/api/exchanges/{eid}/wishes',json={'title':'Chocolate'}).raise_for_status()
    assert c.get(f'/api/exchanges/{eid}/wish-list/{owner}').json()['status']=='draft'
    c.post(f'/api/exchanges/{eid}/wish-list/finalise',json={}).raise_for_status()
    c.delete(f'/api/exchanges/{eid}/wishes/{wish}').raise_for_status()
    assert c.get(f'/api/exchanges/{eid}/wish-list/{owner}').json()['status']=='draft'
    c.post(f'/api/exchanges/{eid}/wish-list/finalise',json={}).raise_for_status()
    c.post(f'/api/exchanges/{eid}/wish-list/draft',json={}).raise_for_status()
    assert c.get(f'/api/exchanges/{eid}/wish-list/{owner}').json()['status']=='draft'

def test_finalise_before_draw_is_scoped_private_and_notified_at_draw(group):
    g=group;c=g['c'];eid=g['eid'];owner=g['alice']['id']
    c.post(f'/api/exchanges/{eid}/wishes',json={'title':'Book'}).raise_for_status()
    c.post(f'/api/exchanges/{eid}/wish-list/finalise',json={}).raise_for_status()
    other=c.post(f'/api/families/{g["family"]}/exchanges',json={'name':'Birthday'}).json()['id']
    assert c.get(f'/api/exchanges/{other}/wish-list/{owner}').json()['status']=='draft'
    with g['factory']() as s:
        assert not s.scalar(select(Notification).where(Notification.title=='Your recipient’s wish list is finalised'))
    g['login']('bob@example.com')
    assert c.get(f'/api/exchanges/{eid}/wish-list/{owner}').status_code==403
    g['login']('alice@example.com')
    c.post(f'/api/exchanges/{eid}/draw',json={}).raise_for_status()
    with g['factory']() as s:
        giver=s.scalar(select(Assignment).where(Assignment.exchange_id==eid,Assignment.recipient_id==owner)).giver_id
        note=s.scalar(select(Notification).where(Notification.title=='Your recipient’s wish list is finalised'))
        assert note.user_id==giver
    c.delete(f'/api/families/{g["family"]}').raise_for_status()
    with g['factory']() as s:
        assert not s.scalar(select(WishListState))

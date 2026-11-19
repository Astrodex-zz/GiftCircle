import pytest
from sqlalchemy import select
from app import main
from app.models import Assignment, Notification, User, WishListState

TITLE='Your recipient is updating their wish list'


def setup_list(g,draw=True):
    c=g['c'];eid=g['eid']
    wid=c.post(f'/api/exchanges/{eid}/wishes',json={'title':'PRIVATE-GIFT'}).json()['id']
    c.post(f'/api/exchanges/{eid}/wishes',json={'title':'Keep this idea'}).raise_for_status()
    if draw:c.post(f'/api/exchanges/{eid}/draw').raise_for_status()
    c.post(f'/api/exchanges/{eid}/wish-list/finalise').raise_for_status()
    main.app.state.outbox.clear()
    return wid


@pytest.mark.parametrize('change',['add','delete','availability','draft'])
def test_reopening_sends_one_private_alert_per_finalised_version(group,change):
    g=group;c=g['c'];eid=g['eid'];wid=setup_list(g)
    def edit():
        if change=='add':return c.post(f'/api/exchanges/{eid}/wishes',json={'title':'New idea'})
        if change=='delete':return c.delete(f'/api/exchanges/{eid}/wishes/{wid}')
        if change=='availability':return c.post(f'/api/exchanges/{eid}/wishes/{wid}/availability')
        return c.post(f'/api/exchanges/{eid}/wish-list/draft')
    edit().raise_for_status()
    assert len(main.app.state.outbox)==1
    with g['factory']() as s:
        giver=s.scalar(select(Assignment).where(Assignment.exchange_id==eid,Assignment.recipient_id==g['alice']['id'])).giver_id
        address=s.get(User,giver).email
        notices=list(s.scalars(select(Notification).where(Notification.title==TITLE)))
        assert len(notices)==1 and notices[0].user_id==giver
    email=main.app.state.outbox[0]
    assert email['to']==address and email['subject']==TITLE
    assert 'PRIVATE-GIFT' not in email['body']
    assert f'/#exchanges/{eid}' in email['body']
    assert c.get(f"/api/exchanges/{eid}/wish-list/{g['alice']['id']}").json()['status']=='draft'
    c.post(f'/api/exchanges/{eid}/wishes',json={'title':'More drafting'}).raise_for_status()
    c.post(f'/api/exchanges/{eid}/wish-list/draft').raise_for_status()
    assert len(main.app.state.outbox)==1
    c.post(f'/api/exchanges/{eid}/wish-list/finalise').raise_for_status()
    assert main.app.state.outbox[-1]['subject']=='Your recipient’s wish list is finalised'
    c.post(f'/api/exchanges/{eid}/wishes',json={'title':'Another revision'}).raise_for_status()
    assert [m['subject'] for m in main.app.state.outbox].count(TITLE)==2


def test_drafts_before_draw_and_other_exchange_do_not_notify(group):
    g=group;c=g['c'];eid=g['eid'];setup_list(g,draw=False)
    c.post(f'/api/exchanges/{eid}/wishes',json={'title':'Change before assignment'}).raise_for_status()
    assert main.app.state.outbox==[]
    c.post(f'/api/exchanges/{eid}/draw').raise_for_status()
    other=c.post(f"/api/families/{g['family']}/exchanges",json={'name':'Another event'}).json()['id']
    main.app.state.outbox.clear()
    c.post(f'/api/exchanges/{other}/wishes',json={'title':'Other event idea'}).raise_for_status()
    c.post(f'/api/exchanges/{eid}/wishes',json={'title':'Never re-finalised'}).raise_for_status()
    assert main.app.state.outbox==[]
    with g['factory']() as s:assert not s.scalar(select(Notification).where(Notification.title==TITLE))


def test_update_respects_email_opt_out_and_invalid_changes_do_not_notify(group):
    g=group;c=g['c'];eid=g['eid'];wid=setup_list(g)
    assert c.post(f'/api/exchanges/{eid}/wishes',json={'title':'Invalid','url':'javascript:alert(1)'}).status_code==400
    assert main.app.state.outbox==[]
    with g['factory']() as s:
        giver=s.scalar(select(Assignment).where(Assignment.exchange_id==eid,Assignment.recipient_id==g['alice']['id'])).giver_id
        s.get(User,giver).notify_email=False;s.commit()
    c.delete(f'/api/exchanges/{eid}/wishes/{wid}').raise_for_status()
    assert main.app.state.outbox==[]
    with g['factory']() as s:assert s.scalar(select(Notification).where(Notification.title==TITLE)).user_id==giver


def test_email_sent_after_commit_and_failure_preserves_update(group,monkeypatch):
    g=group;c=g['c'];eid=g['eid'];setup_list(g)
    called=[]
    def fail_delivery(*args):
        with g['factory']() as s:
            assert s.get(WishListState,(eid,g['alice']['id'])).finalised_at is None
            assert s.scalar(select(Notification).where(Notification.title==TITLE))
        called.append(args)
        raise RuntimeError('Simulated SMTP outage')
    monkeypatch.setattr(main,'email_send',fail_delivery)
    c.post(f'/api/exchanges/{eid}/wishes',json={'title':'Saved despite outage'}).raise_for_status()
    assert len(called)==1
    c.post(f'/api/exchanges/{eid}/wishes',json={'title':'Further draft edit'}).raise_for_status()
    assert len(called)==1

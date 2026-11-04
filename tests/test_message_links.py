from app import main


def test_message_email_links_to_correct_conversation(group):
    g=group;c=g['c'];eid=g['eid']
    c.post(f'/api/exchanges/{eid}/draw').raise_for_status()
    assignment=c.get(f'/api/exchanges/{eid}').json()['my_assignment']
    aid=assignment['assignment_id']
    c.post(f'/api/exchanges/{eid}/messages/{aid}',json={'content':'Hello there'}).raise_for_status()
    mail=main.app.state.outbox[-1]
    assert f'/#messages/{eid}/santa' in mail['body']
    assert 'Replies to this email are not posted' in mail['body']
    recipient_email={g[k]['id']:g[k]['email'] for k in ['alice','bob','carol']}[assignment['recipient_id']]
    g['login'](recipient_email)
    c.post(f'/api/exchanges/{eid}/messages/{aid}',json={'content':'Hello back'}).raise_for_status()
    assert f'/#messages/{eid}/giver' in main.app.state.outbox[-1]['body']
    g['login']('alice@example.com')
    c.post(f'/api/exchanges/{eid}/announcements',json={'content':'Party time'}).raise_for_status()
    assert all(f'/#messages/{eid}/group' in m['body'] for m in main.app.state.outbox[-2:])


def test_signin_preserves_safe_message_destination(env):
    c,*_=env
    c.post('/api/auth/request',json={'email':'person@example.com','return_to':'#messages/3/group'}).raise_for_status()
    assert '#messages/3/group' in main.app.state.outbox[-1]['body']
    c.post('/api/auth/request',json={'email':'person@example.com','return_to':'https://evil.example'}).raise_for_status()
    assert 'evil.example' not in main.app.state.outbox[-1]['body']


def test_group_messages_notify_participants_and_respect_email_preferences(group):
    from sqlalchemy import select
    from app.models import Notification
    g=group;c=g['c'];eid=g['eid']
    g['login']('bob@example.com')
    c.patch('/api/me',json={'name':'Bob','notify_email':False}).raise_for_status()
    g['login']('alice@example.com')
    main.app.state.outbox.clear()
    c.post(f'/api/exchanges/{eid}/group-messages',json={'content':'Hello everyone'}).raise_for_status()
    assert [m['to'] for m in main.app.state.outbox]==['carol@example.com']
    assert f'/#messages/{eid}/group' in main.app.state.outbox[0]['body']
    with g['factory']() as s:
        notices=list(s.scalars(select(Notification).where(Notification.exchange_id==eid)))
        assert {n.user_id for n in notices}=={g['bob']['id'],g['carol']['id']}
    g['login']('outsider@example.com')
    main.app.state.outbox.clear()
    assert c.post(f'/api/exchanges/{eid}/group-messages',json={'content':'No access'}).status_code in (403,404)
    assert main.app.state.outbox==[]

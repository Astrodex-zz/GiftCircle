import re
from datetime import timedelta
from sqlalchemy import select
from fastapi.testclient import TestClient
from app import main
from app.models import RevealToken,Assignment,Exchange,PreviousDrawRule,utcnow


def draw_links(c,eid):
    c.post(f'/api/exchanges/{eid}/draw').raise_for_status()
    mails=[m for m in main.app.state.outbox if '#reveal=' in m['body']]
    return {m['to']:re.search(r'#reveal=([A-Za-z0-9_-]+)',m['body']).group(1) for m in mails}


def test_private_reveal_is_scoped_expiring_and_does_not_sign_in(group):
    g=group;c=g['c'];eid=g['eid'];tokens=draw_links(c,eid)
    assert len(tokens)==3 and len(set(tokens.values()))==3
    anon=TestClient(main.app)
    for key in ['alice','bob','carol']:
        person=g[key];token=tokens[person['email']]
        with g['factory']() as s:
            assignment=s.scalar(select(Assignment).where(Assignment.exchange_id==eid,Assignment.giver_id==person['id']))
            from app.models import User
            expected=s.get(User,assignment.recipient_id).name
            stored=s.scalar(select(RevealToken).where(RevealToken.digest==main.digest(token)))
            assert stored.digest!=token
        response=anon.post('/api/reveal',json={'token':token})
        assert response.status_code==200
        assert response.json()['recipient_name']==expected
        assert set(response.json())=={'exchange_name','group_name','recipient_name','budget','exchange_date'}
        assert 'set-cookie' not in response.headers
        assert response.headers['cache-control']=='no-store'
        assert anon.get('/api/me').status_code==401
    token=tokens['alice@example.com']
    assert anon.post('/api/reveal',json={'token':'x'*43}).status_code==404
    with g['factory']() as s:
        stored=s.scalar(select(RevealToken).where(RevealToken.digest==main.digest(token)))
        stored.expires_at=utcnow()-timedelta(seconds=1);s.commit()
    assert anon.post('/api/reveal',json={'token':token}).status_code==404


def test_delete_only_exchange_and_revoke_reveal(group):
    g=group;c=g['c'];eid=g['eid'];fid=g['family'];tokens=draw_links(c,eid)
    other=c.post(f'/api/families/{fid}/exchanges',json={'name':'Next year','exchange_date':'2027-12-25','invitation_message':'See you next year'}).json()['id']
    c.put(f'/api/exchanges/{other}/exclusions',json={'pairs':[],'previous_draw_id':eid}).raise_for_status()
    g['login']('bob@example.com')
    assert c.delete(f'/api/exchanges/{eid}').status_code==403
    g['login']('alice@example.com')
    c.delete(f'/api/exchanges/{eid}').raise_for_status()
    for email in ['alice@example.com','bob@example.com','carol@example.com']:
        g['login'](email)
        assert [e['id'] for e in c.get('/api/exchanges').json()]==[other]
        assert c.get(f'/api/families/{fid}').status_code==200
        assert c.get(f'/api/exchanges/{eid}').status_code==404
    anon=TestClient(main.app)
    assert anon.post('/api/reveal',json={'token':tokens['alice@example.com']}).status_code==404
    with g['factory']() as s:
        assert s.get(Exchange,other)
        assert s.get(PreviousDrawRule,other) is None
        assert not s.scalar(select(RevealToken).where(RevealToken.exchange_id==eid))


def test_later_group_invite_includes_saved_welcome_without_exchange_selection(group):
    g=group;c=g['c'];fid=g['family']
    eid=c.post(f'/api/families/{fid}/exchanges',json={'name':'Birthday','invitation_message':'Bring your favourite party hat!'}).json()['id']
    token=g['invite'](fid,'later@example.com')
    assert 'Bring your favourite party hat!' in main.app.state.outbox[-1]['body']
    g['login']('later@example.com')
    invites=c.get('/api/invites').json()
    assert any(w['message']=='Bring your favourite party hat!' for w in invites[0]['welcomes'])
    c.post('/api/invites/accept',json={'token':token}).raise_for_status()
    assert eid in [e['id'] for e in c.get('/api/exchanges').json()]


def test_email_headers_and_plain_html_alternatives(monkeypatch):
    sent=[]
    class SMTP:
        def __init__(self,*a,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def starttls(self,**kw):pass
        def login(self,*a):pass
        def send_message(self,mail,**kw):sent.append((mail,kw))
    monkeypatch.setattr(main.smtplib,'SMTP',SMTP)
    monkeypatch.setenv('MAIL_MODE','smtp');monkeypatch.setenv('SMTP_HOST','smtp.example.com')
    monkeypatch.setenv('MAIL_FROM','GiftCircle <sender@example.com>')
    main.email_send('recipient@example.com','A friendly test',f'Hello <friend>\n\nReveal my recipient: {main.PUBLIC_URL}/#reveal=testtoken')
    mail,options=sent[0]
    assert mail['Date'] and mail['Message-ID'] and mail['Auto-Submitted']=='auto-generated'
    assert options['from_addr']=='sender@example.com'
    assert mail.get_body(preferencelist=('plain',)) is not None
    html=mail.get_body(preferencelist=('html',)).get_content()
    assert 'Reveal my recipient</a>' in html and '&lt;friend&gt;' in html

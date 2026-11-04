from sqlalchemy import select
from app.models import Assignment, Exchange

def test_history_and_manual_rules(group):
    g=group;c=g['c'];old=g['eid'];fid=g['family']
    # A genuinely earlier completed exchange in the same group.
    with g['factory']() as s:
        s.get(Exchange,old).exchange_date='2025-12-25';s.commit()
    assert c.post(f'/api/exchanges/{old}/draw').status_code==200
    eid=c.post(f'/api/families/{fid}/exchanges',json={'name':'Next Christmas','exchange_date':'2026-12-25'}).json()['id']
    with g['factory']() as s:
        prior={(a.giver_id,a.recipient_id) for a in s.scalars(select(Assignment).where(Assignment.exchange_id==old))}
    g_id,r_id=next(iter(prior))
    pair={'giver_id':g_id,'recipient_id':r_id}
    url=f'/api/exchanges/{eid}/exclusions'
    assert c.put(url,json={'pairs':[pair,pair],'previous_draw_id':old}).status_code==200
    detail=c.get(f'/api/exchanges/{eid}').json()
    assert detail['exclusions']==[pair]  # History does not expose secret assignments.
    assert detail['previous_pair_count']==3
    assert detail['previous_draws']==[{'id':old,'name':'Christmas 2026','date':'2025-12-25'}]
    # Disabling history keeps manual selections.
    assert c.put(url,json={'pairs':[pair]}).status_code==200
    assert c.get(f'/api/exchanges/{eid}').json()['previous_draw_id'] is None
    # Invalid source and invalid pair are atomic failures.
    assert c.put(url,json={'pairs':[],'previous_draw_id':eid}).status_code==400
    assert c.put(url,json={'pairs':[{'giver_id':g_id,'recipient_id':g_id}]}).status_code==400
    assert c.get(f'/api/exchanges/{eid}').json()['exclusions']==[pair]
    g['login']('bob@example.com')
    assert c.put(url,json={'pairs':[]}).status_code==403
    assert 'previous_draws' not in c.get(f'/api/exchanges/{eid}').json()
    g['login']('alice@example.com')
    foreign=c.post('/api/families',json={'name':'Other group'}).json()['id']
    other=c.post(f'/api/families/{foreign}/exchanges',json={'name':'Other draw','exchange_date':'2025-12-25'}).json()['id']
    assert c.put(url,json={'pairs':[],'previous_draw_id':other}).status_code==400
    assert c.put(url,json={'pairs':[pair],'previous_draw_id':old}).status_code==200
    assert c.post(f'/api/exchanges/{eid}/draw').status_code==200
    with g['factory']() as s:
        new={(a.giver_id,a.recipient_id) for a in s.scalars(select(Assignment).where(Assignment.exchange_id==eid))}
    assert not new.intersection(prior)
    assert c.put(url,json={'pairs':[]}).status_code==409

def test_multiple_recipients_and_impossible_draw(group):
    g=group;c=g['c'];eid=g['eid'];alice=g['alice']['id']
    pairs=[{'giver_id':alice,'recipient_id':g[name]['id']} for name in ('bob','carol')]
    assert c.put(f'/api/exchanges/{eid}/exclusions',json={'pairs':pairs}).status_code==200
    assert len(c.get(f'/api/exchanges/{eid}').json()['exclusions'])==2
    assert c.post(f'/api/exchanges/{eid}/draw').status_code==422
    assert c.get(f'/api/exchanges/{eid}').json()['drawn'] is False

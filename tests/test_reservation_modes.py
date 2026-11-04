from app import main

def test_reservation_modes_and_availability(group):
    g=group;c=g['c'];eid=g['eid']
    assert c.get(f'/api/exchanges/{eid}').json()['reservation_mode']=='show'
    for name in ('alice','bob','carol'):
        g['login'](name+'@example.com')
        c.post(f'/api/exchanges/{eid}/wishes',json={'title':'Gift '+name}).raise_for_status()
    g['login']('alice@example.com')
    c.post(f'/api/exchanges/{eid}/draw').raise_for_status()
    rid=c.get(f'/api/exchanges/{eid}').json()['my_assignment']['recipient_id']
    target=next(n for n in ('bob','carol') if g[n]['id']==rid)
    wid=c.get(f'/api/exchanges/{eid}/wishes/{rid}').json()[0]['id']
    main.app.state.outbox.clear()
    c.post(f'/api/exchanges/{eid}/wishes/{wid}/reserve').raise_for_status()
    assert len(main.app.state.outbox)==1
    assert main.app.state.outbox[0]['to']==target+'@example.com'
    c.post(f'/api/exchanges/{eid}/wishes/{wid}/purchase').raise_for_status()
    g['login'](target+'@example.com')
    own=c.get(f'/api/exchanges/{eid}/wishes/{rid}').json()[0]
    assert own['reserved'] is True and 'reserved_by' not in own and 'purchased_by_me' not in own
    assert c.post(f'/api/exchanges/{eid}/wishes/{wid}/availability').status_code==409
    assert c.put(f'/api/exchanges/{eid}/reservation-settings',json={'mode':'surprise'}).status_code==403
    g['login']('alice@example.com')
    c.post(f'/api/exchanges/{eid}/wishes/{wid}/reserve').raise_for_status()
    g['login'](target+'@example.com')
    c.post(f'/api/exchanges/{eid}/wishes/{wid}/availability').raise_for_status()
    g['login']('alice@example.com')
    assert c.post(f'/api/exchanges/{eid}/wishes/{wid}/reserve').status_code==409
    c.put(f'/api/exchanges/{eid}/reservation-settings',json={'mode':'surprise'}).raise_for_status()
    other=c.post(f'/api/families/{g["family"]}/exchanges',json={'name':'Other'}).json()['id']
    assert c.get(f'/api/exchanges/{other}').json()['reservation_mode']=='show'
    g['login'](target+'@example.com')
    assert 'reserved' not in c.get(f'/api/exchanges/{eid}/wishes/{rid}').json()[0]
    assert c.post(f'/api/exchanges/{eid}/wishes/{wid}/availability').status_code==409
    g['login']('alice@example.com')
    c.delete(f'/api/families/{g["family"]}').raise_for_status()

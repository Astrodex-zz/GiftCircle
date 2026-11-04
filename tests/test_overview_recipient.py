def test_overview_recipient_only_shows_signed_in_users_assignment(group):
    g=group;c=g['c'];eid=g['eid']
    assert c.get('/api/exchanges').json()[0]['my_recipient'] is None
    c.post(f'/api/exchanges/{eid}/draw').raise_for_status()
    for email in ['alice@example.com','bob@example.com','carol@example.com']:
        g['login'](email)
        detail=c.get(f'/api/exchanges/{eid}').json()
        overview=next(e for e in c.get('/api/exchanges').json() if e['id']==eid)
        mine=detail['my_assignment']
        assert overview['my_recipient']=={'id':mine['recipient_id'],'name':mine['name']}
        assert 'assignments' not in overview
        assert 'giver_id' not in overview
    g['login']('outsider@example.com')
    assert c.get('/api/exchanges').json()==[]

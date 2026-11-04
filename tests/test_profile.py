def test_name_setup_persists_and_is_account_specific(env):
    c,login,*_=env
    login('first@example.com')
    assert c.get('/api/me').json()['name_confirmed'] is False
    saved=c.patch('/api/me',json={'name':'  First Person  ','notify_email':False})
    assert saved.status_code==200
    assert saved.json()['name']=='First Person'
    assert saved.json()['name_confirmed'] is True
    assert saved.json()['notify_email'] is False
    assert c.patch('/api/me',json={'name':'   '}).status_code==422
    login('second@example.com')
    assert c.get('/api/me').json()['name_confirmed'] is False
    assert c.get('/api/me').json()['email']=='second@example.com'
    login('first@example.com')
    profile=c.get('/api/me').json()
    assert profile['name']=='First Person'
    assert profile['name_confirmed'] is True
    assert profile['notify_email'] is False

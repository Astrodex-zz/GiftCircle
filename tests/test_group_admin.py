def test_admin_remove_member_and_revoke_old_invites(group):
    g=group;c=g['c'];fid=g['family'];uid=g['bob']['id']
    g['login']('bob@example.com')
    assert c.delete(f'/api/families/{fid}/members/{g["carol"]["id"]}').status_code==403
    g['login']('alice@example.com')
    assert c.delete(f'/api/families/{fid}/members/{g["alice"]["id"]}').status_code==409
    assert c.delete(f'/api/families/{fid}/members/{uid}').status_code==200
    assert uid not in [p['id'] for p in c.get(f'/api/exchanges/{g["eid"]}').json()['participants']]
    g['login']('bob@example.com')
    assert c.get('/api/families').json()==[]
    assert c.get(f'/api/families/{fid}').status_code==404

def test_draw_protected_and_group_delete_cleans_dependencies(group):
    g=group;c=g['c'];fid=g['family'];eid=g['eid']
    c.post(f'/api/exchanges/{eid}/wishes',json={'title':'A book'}).raise_for_status()
    c.post(f'/api/exchanges/{eid}/draw',json={}).raise_for_status()
    assert c.delete(f'/api/families/{fid}/members/{g["bob"]["id"]}').status_code==409
    g['login']('bob@example.com')
    assert c.delete(f'/api/families/{fid}').status_code==403
    g['login']('alice@example.com')
    other=c.post('/api/families',json={'name':'Keep this group'}).json()['id']
    c.delete(f'/api/families/{fid}').raise_for_status()
    assert [f['id'] for f in c.get('/api/families').json()]==[other]
    assert c.get('/api/exchanges').json()==[]
    assert c.get('/api/me').status_code==200


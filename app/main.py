import hashlib, hmac, os, re, secrets, smtplib, ssl, logging
from datetime import timedelta, date
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, Depends, HTTPException, Request, Response, Cookie
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy import create_engine, select, and_, func, delete, or_
from sqlalchemy.orm import Session as DBSession, sessionmaker
from .models import *

log=logging.getLogger('giftcircle')
DB_URL=os.getenv('DATABASE_URL','sqlite:////tmp/giftcircle.db')
engine=create_engine(DB_URL,connect_args={'check_same_thread':False} if DB_URL.startswith('sqlite') else {},pool_pre_ping=True)
Factory=sessionmaker(bind=engine,autoflush=False,expire_on_commit=False)
Base.metadata.create_all(engine)
app=FastAPI(title='GiftCircle',version='1.0.0',docs_url=None,redoc_url=None)
STATIC=Path(__file__).parent/'static'
app.mount('/assets',StaticFiles(directory=STATIC),name='assets')
app.state.outbox=[]
@app.middleware('http')
async def security_headers(request:Request,call_next):
    # Cross-origin requests are not needed. Block mutation from foreign origins.
    if request.method in ('POST','PATCH','PUT','DELETE'):
        origin=request.headers.get('origin')
        if origin and origin.rstrip('/') != str(request.base_url).rstrip('/') and origin.rstrip('/') != PUBLIC_URL:
            return Response('Foreign origin rejected',status_code=403)
    response=await call_next(request)
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control']='no-store'
    return response

PUBLIC_URL=os.getenv('PUBLIC_URL','http://localhost:8000').rstrip('/')
HTTPS=PUBLIC_URL.startswith('https://')
COOKIE='giftcircle_session'

def db():
    with Factory() as session: yield session

def digest(s): return hashlib.sha256(s.encode()).hexdigest()
def new_token(): return secrets.token_urlsafe(32)
def fail(code,msg): raise HTTPException(code,msg)
def stamp(d): return d.isoformat()+'Z' if d else None

def user_or_401(request:Request, session:DBSession=Depends(db)):
    value=request.cookies.get(COOKIE,'')
    if not value: fail(401,'Please sign in')
    auth=session.scalar(select(Session).where(Session.digest==digest(value)))
    if not auth or auth.expires_at < utcnow(): fail(401,'Session expired')
    user=session.get(User,auth.user_id)
    if not user: fail(401,'Account unavailable')
    return user

def family_member(s,u,fid):
    f=s.get(Family,fid)
    if not f or not s.scalar(select(Membership).where(Membership.family_id==fid,Membership.user_id==u.id)): fail(404,'Group not found')
    return f

def exchange_member(s,u,eid):
    e=s.get(Exchange,eid)
    if not e: fail(404,'Exchange not found')
    family_member(s,u,e.family_id)
    if not s.scalar(select(Participant).where(Participant.exchange_id==eid,Participant.user_id==u.id)): fail(403,'Not participating in exchange')
    return e

def only_owner(s,u,fid):
    f=family_member(s,u,fid)
    if f.owner_id!=u.id: fail(403,'Only the group organiser can do that')
    return f

def email_send(to,subject,body):
    mode=os.getenv('MAIL_MODE','log')
    if mode=='log':
        app.state.outbox.append({'to':to,'subject':subject,'body':body})
        # Keep development capture bounded; never retain SMTP sign-in tokens here.
        del app.state.outbox[:-300]
        log.warning('Development email to %s: %s — %s',to,subject,body)
        return
    host=os.getenv('SMTP_HOST','')
    if not host: raise RuntimeError('SMTP_HOST required when MAIL_MODE=smtp')
    mail=EmailMessage()
    mail['From']=os.getenv('MAIL_FROM','GiftCircle <gifts@example.test>')
    mail['To']=to
    mail['Subject']=subject
    sender=parseaddr(mail['From'])[1]
    mail['Date']=formatdate(localtime=False,usegmt=True)
    mail['Message-ID']=make_msgid(domain=sender.rsplit('@',1)[-1])
    mail['Auto-Submitted']='auto-generated'
    # Keep transactional mail plain text, including complete sign-in/reveal links.
    mail.set_content(body)
    port=int(os.getenv('SMTP_PORT','587'))
    if os.getenv('SMTP_SSL','false').lower()=='true':
        server=smtplib.SMTP_SSL(host,port,timeout=10,context=ssl.create_default_context())
    else: server=smtplib.SMTP(host,port,timeout=10)
    with server:
        if os.getenv('SMTP_STARTTLS','false').lower()=='true':server.starttls(context=ssl.create_default_context())
        if os.getenv('SMTP_USERNAME'):server.login(os.environ['SMTP_USERNAME'],os.environ['SMTP_PASSWORD'])
        server.send_message(mail,from_addr=sender)

def notify(s,user_id,eid,title,detail,link=None):
    s.add(Notification(user_id=user_id,exchange_id=eid,title=title,detail=detail))
    u=s.get(User,user_id)
    if u and u.notify_email:
        destination=f'View messages and reply: {PUBLIC_URL}{link}\n\nPlease reply in GiftCircle. Replies to this email are not posted to your conversation.' if link else f'Open GiftCircle: {PUBLIC_URL}/'
        try: email_send(u.email,title, f'{detail}\n\n{destination}\n\nYou can change notifications in your profile.')
        except Exception: log.exception('Email delivery failed; in-app notification preserved')

class LoginRequest(BaseModel): email:EmailStr;return_to:str=Field(default="",max_length=100)
class LoginConsume(BaseModel): token:str
class Profile(BaseModel): name:str=Field(max_length=100);notify_email:bool=True
class FamilyCreate(BaseModel): name:str=Field(min_length=2,max_length=120)
class InviteRequest(BaseModel): email:EmailStr;exchange_id:int|None=None
class AcceptRequest(BaseModel): token:str
class ExchangeCreate(BaseModel): name:str=Field(min_length=2,max_length=120);budget:int=Field(default=50,ge=0,le=100000);exchange_date:str='';invitation_message:str=Field(default='',max_length=3000)
class ExclusionRequest(BaseModel):giver_id:int;recipient_id:int;excluded:bool=True
class WishCreate(BaseModel):title:str=Field(min_length=1,max_length=200);details:str=Field(default='',max_length=1500);url:str=Field(default='',max_length=1500);price:str=Field(default='',max_length=40)
class MessageCreate(BaseModel): content:str=Field(min_length=1,max_length=3000)

@app.get('/api/health')
def health():return {'ok':True,'version':'1.0.0'}

@app.post('/api/auth/request')
def request_link(body:LoginRequest,request:Request,s:DBSession=Depends(db)):
    email=str(body.email).strip().lower()
    destination=body.return_to if re.fullmatch(r'#messages/\d+(?:/(giver|santa|group))?',body.return_to) else ''
    # Limit account-targeted email bombing, including users who are not registered.
    key=digest(email)
    recent=s.scalar(select(func.count(LoginAttempt.id)).where(LoginAttempt.key==key,LoginAttempt.created_at>=utcnow()-timedelta(minutes=15)))
    if recent>=10:fail(429,'Too many links requested. Please try again later.')
    s.add(LoginAttempt(key=key))
    u=s.scalar(select(User).where(User.email==email))
    if not u:
        u=User(email=email,name=email.split('@')[0].replace('.',' ').title());s.add(u);s.flush()
    # Invalidate all outstanding links for this user; do not disclose user existence
    for t in s.scalars(select(AuthToken).where(AuthToken.user_id==u.id,AuthToken.consumed_at==None)): t.consumed_at=utcnow()
    token=new_token();s.add(AuthToken(user_id=u.id,digest=digest(token),expires_at=utcnow()+timedelta(minutes=20)))
    s.commit()
    email_send(email,'Your GiftCircle sign-in link',f'Your private sign-in link (valid for 20 minutes and one use):\n\n{PUBLIC_URL}/?login={token}{destination}\n\nIf you did not request this, ignore this email.')
    return {'ok':True,'message':'Check your email for a sign-in link.'}

@app.post('/api/auth/consume')
def consume_link(body:LoginConsume,response:Response,s:DBSession=Depends(db)):
    t=s.scalar(select(AuthToken).where(AuthToken.digest==digest(body.token)).with_for_update())
    if not t or t.consumed_at or t.expires_at<utcnow(): fail(400,'Sign-in link expired or already used')
    t.consumed_at=utcnow();secret=new_token();s.add(Session(user_id=t.user_id,digest=digest(secret),expires_at=utcnow()+timedelta(days=30)))
    s.commit();response.set_cookie(COOKIE,secret,max_age=30*86400,httponly=True,secure=HTTPS,samesite='lax',path='/')
    return {'ok':True}

@app.post('/api/auth/logout')
def logout(response:Response,request:Request,s:DBSession=Depends(db)):
    token=request.cookies.get(COOKIE,'')
    if token:
        auth=s.scalar(select(Session).where(Session.digest==digest(token)))
        if auth:s.delete(auth);s.commit()
    response.delete_cookie(COOKIE,path='/');return {'ok':True}

@app.get('/api/me')
def me(u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    return {'id':u.id,'email':u.email,'name':u.name,'notify_email':u.notify_email,'name_confirmed':bool(s.get(UserProfileState,u.id))}

@app.patch('/api/me')
def update_me(body:Profile,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    name=body.name.strip()
    if not name: fail(422,'Please enter your name')
    u.name=name;u.notify_email=body.notify_email;s.add(u)
    if not s.get(UserProfileState,u.id): s.add(UserProfileState(user_id=u.id))
    s.commit();return me(u,s)

@app.get('/api/families')
def families(u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    ms=s.scalars(select(Membership).where(Membership.user_id==u.id)).all()
    return [{'id':f.id,'name':f.name,'owner_id':f.owner_id} for m in ms if (f:=s.get(Family,m.family_id))]

@app.post('/api/families')
def make_family(body:FamilyCreate,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    if len(body.name.strip())<2:fail(422,'Enter a group name of at least two characters')
    f=Family(name=body.name.strip(),owner_id=u.id);s.add(f);s.flush();s.add(Membership(family_id=f.id,user_id=u.id));s.commit();return {'id':f.id,'name':f.name}

@app.get('/api/families/{fid}')
def family_detail(fid:int,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    f=family_member(s,u,fid)
    members=[{'id':m.user_id,'name':s.get(User,m.user_id).name} for m in s.scalars(select(Membership).where(Membership.family_id==fid))]
    pending=[{'email':i.email,'expires_at':stamp(i.expires_at),'welcomes':exchange_welcomes(s,i.family_id)} for i in s.scalars(select(Invitation).where(Invitation.family_id==fid,Invitation.accepted_at==None)) if i.expires_at>utcnow()] if u.id==f.owner_id else []
    return {'id':f.id,'name':f.name,'owner_id':f.owner_id,'members':members,'pending':pending}

@app.delete('/api/families/{fid}/members/{uid}')
def remove_member(fid:int,uid:int,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    f=only_owner(s,u,fid)
    if uid==f.owner_id:fail(409,'The group admin cannot be removed. You can delete the group instead.')
    member=s.scalar(select(Membership).where(Membership.family_id==fid,Membership.user_id==uid))
    if not member:fail(404,'Member not found')
    ids=list(s.scalars(select(Exchange.id).where(Exchange.family_id==fid)))
    if s.scalar(select(Participant.id).join(Exchange,Participant.exchange_id==Exchange.id).where(Exchange.family_id==fid,Exchange.drawn_at!=None,Participant.user_id==uid)):
        fail(409,'This member is part of a completed draw and cannot be removed without breaking its assignments.')
    s.execute(delete(Exclusion).where(Exclusion.exchange_id.in_(ids),or_(Exclusion.giver_id==uid,Exclusion.recipient_id==uid)))
    s.execute(delete(WishListState).where(WishListState.exchange_id.in_(ids),WishListState.user_id==uid))
    s.execute(delete(WishAvailability).where(WishAvailability.wish_id.in_(select(Wish.id).where(Wish.exchange_id.in_(ids),Wish.user_id==uid))))
    s.execute(delete(Wish).where(Wish.exchange_id.in_(ids),Wish.user_id==uid))
    s.execute(delete(MessageReadState).where(MessageReadState.exchange_id.in_(ids),MessageReadState.user_id==uid))
    s.execute(delete(Message).where(Message.exchange_id.in_(ids),Message.sender_id==uid))
    s.execute(delete(Notification).where(Notification.exchange_id.in_(ids),Notification.user_id==uid))
    s.execute(delete(Participant).where(Participant.exchange_id.in_(ids),Participant.user_id==uid))
    s.execute(delete(Invitation).where(Invitation.family_id==fid,Invitation.email==s.get(User,uid).email))
    s.delete(member);s.commit();return {'ok':True}

@app.delete('/api/families/{fid}')
def delete_group(fid:int,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    f=only_owner(s,u,fid)
    ids=list(s.scalars(select(Exchange.id).where(Exchange.family_id==fid)))
    s.execute(delete(PreviousDrawRule).where(or_(PreviousDrawRule.exchange_id.in_(ids),PreviousDrawRule.source_id.in_(ids))))
    for model in (MessageReadState,RevealToken,Message,Notification,ExchangeInvitationText,ReservationPolicy,WishListState,WishAvailability,Wish,Exclusion,Assignment,Participant):
        s.execute(delete(model).where(model.exchange_id.in_(ids)))
    s.execute(delete(Exchange).where(Exchange.family_id==fid))
    s.execute(delete(Invitation).where(Invitation.family_id==fid))
    s.execute(delete(Membership).where(Membership.family_id==fid))
    s.delete(f);s.commit();return {'ok':True}

@app.post('/api/families/{fid}/invites')
def invite(fid:int,body:InviteRequest,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    f=only_owner(s,u,fid);email=str(body.email).lower()
    chosen=s.get(Exchange,body.exchange_id) if body.exchange_id is not None else None
    if body.exchange_id is not None and (not chosen or chosen.family_id!=fid):fail(400,'Choose an exchange in this group')
    if chosen and chosen.drawn_at:fail(409,'Names have already been drawn for this exchange')
    welcomes=exchange_welcomes(s,fid)
    if chosen:welcomes.sort(key=lambda item:item['id']!=chosen.id)
    introduction='\n\n'.join(f"{item['name']}\n{item['message']}" for item in welcomes) or f'{u.name} invited you to join {f.name}.'
    occasion=f'Exchange: {chosen.name} · {f.name}\n\n' if chosen else ''
    existing=s.scalar(select(User).where(User.email==email))
    if existing and s.scalar(select(Membership).where(Membership.family_id==fid,Membership.user_id==existing.id)):fail(409,'Already a group member')
    token=new_token();s.add(Invitation(family_id=fid,email=email,digest=digest(token),expires_at=utcnow()+timedelta(days=14)));s.commit()
    email_send(email,f'You are invited to {f.name} on GiftCircle',f'{occasion}{introduction}\n\nAccept your invitation: {PUBLIC_URL}/?invite={token}\n\nInvitation expires in 14 days. Sign in using this email address.')
    return {'ok':True}

def join_invitation(i,u,s):
    if not i:fail(404,'Invitation not found')
    if not hmac.compare_digest(i.email,u.email):fail(403,'Sign in using the email address to which the invitation was sent')
    if i.expires_at<utcnow() and not i.accepted_at:fail(400,'Invitation expired')
    if not s.scalar(select(Membership).where(Membership.family_id==i.family_id,Membership.user_id==u.id)):
        s.add(Membership(family_id=i.family_id,user_id=u.id))
    for e in s.scalars(select(Exchange).where(Exchange.family_id==i.family_id,Exchange.drawn_at==None)):
        if not s.scalar(select(Participant).where(Participant.exchange_id==e.id,Participant.user_id==u.id)):
            s.add(Participant(exchange_id=e.id,user_id=u.id))
    for other in s.scalars(select(Invitation).where(Invitation.family_id==i.family_id,Invitation.email==u.email,Invitation.accepted_at==None)):
        other.accepted_at=utcnow()
    s.commit();return {'ok':True,'family_id':i.family_id}

def exchange_welcomes(s,fid):
    return [{'id':e.id,'name':e.name,'message':text.message} for e in s.scalars(select(Exchange).where(Exchange.family_id==fid,Exchange.drawn_at==None).order_by(Exchange.id)) if (text:=s.get(ExchangeInvitationText,e.id)) and text.message.strip()]

@app.get('/api/invites')
def my_invitations(u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    return [{'id':i.id,'family_name':s.get(Family,i.family_id).name,'expires_at':stamp(i.expires_at),'welcomes':exchange_welcomes(s,i.family_id)} for i in s.scalars(select(Invitation).where(Invitation.email==u.email,Invitation.accepted_at==None,Invitation.expires_at>utcnow()))]

@app.post('/api/invites/accept')
def accept_invite(body:AcceptRequest,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    i=s.scalar(select(Invitation).where(Invitation.digest==digest(body.token)))
    if not i or i.accepted_at:fail(400,'Invitation expired or already used')
    return join_invitation(i,u,s)

@app.post('/api/invites/{iid}/accept')
def accept_my_invite(iid:int,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    i=s.get(Invitation,iid)
    if not i or i.email!=u.email:fail(404,'Invitation not found')
    return join_invitation(i,u,s)

def invitation_message(s,eid):
    text=s.get(ExchangeInvitationText,eid)
    return text.message if text else ''

@app.get('/api/exchanges')
def exchanges(u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    ids=[m.family_id for m in s.scalars(select(Membership).where(Membership.user_id==u.id))]
    if not ids:return []
    result=[]
    for e in s.scalars(select(Exchange).where(Exchange.family_id.in_(ids)).order_by(Exchange.id.desc())):
        if s.scalar(select(Participant).where(Participant.exchange_id==e.id,Participant.user_id==u.id)):
            f=s.get(Family,e.family_id)
            assignment=s.scalar(select(Assignment).where(Assignment.exchange_id==e.id,Assignment.giver_id==u.id)) if e.drawn_at else None
            recipient=s.get(User,assignment.recipient_id) if assignment else None
            result.append({'id':e.id,'name':e.name,'family_id':e.family_id,'family_name':f.name,'drawn':bool(e.drawn_at),'exchange_date':e.exchange_date,'budget':e.budget,'invitation_message':invitation_message(s,e.id),'my_recipient':{'id':recipient.id,'name':recipient.name} if recipient else None})
    return result

@app.post('/api/families/{fid}/exchanges')
def new_exchange(fid:int,body:ExchangeCreate,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    only_owner(s,u,fid)
    if len(body.name.strip())<2:fail(422,'Enter an exchange name of at least two characters')
    if body.exchange_date:
        try:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',body.exchange_date):raise ValueError()
            date.fromisoformat(body.exchange_date)
        except ValueError:fail(400,'Choose a valid date')
    e=Exchange(family_id=fid,name=body.name.strip(),budget=body.budget,exchange_date=body.exchange_date)
    s.add(e);s.flush()
    if body.invitation_message.strip():s.add(ExchangeInvitationText(exchange_id=e.id,message=body.invitation_message.strip()))
    for m in s.scalars(select(Membership).where(Membership.family_id==fid)):s.add(Participant(exchange_id=e.id,user_id=m.user_id))
    s.commit();return {'id':e.id}

@app.delete('/api/exchanges/{eid}')
def delete_exchange(eid:int,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    e=s.get(Exchange,eid)
    if not e:fail(404,'Exchange not found')
    only_owner(s,u,e.family_id)
    s.execute(delete(PreviousDrawRule).where(or_(PreviousDrawRule.exchange_id==eid,PreviousDrawRule.source_id==eid)))
    for model in (MessageReadState,RevealToken,Message,Notification,ExchangeInvitationText,ReservationPolicy,WishListState,WishAvailability,Wish,Exclusion,Assignment,Participant):
        s.execute(delete(model).where(model.exchange_id==eid))
    s.delete(e);s.commit();return {'ok':True}

class RevealRequest(BaseModel):
    token:str=Field(min_length=20,max_length=200)

@app.post('/api/reveal')
def reveal_recipient(body:RevealRequest,s:DBSession=Depends(db)):
    token=s.scalar(select(RevealToken).where(RevealToken.digest==digest(body.token)))
    if not token or token.expires_at<utcnow():fail(404,'This reveal link has expired or is no longer available. Sign in to view your exchange.')
    e=s.get(Exchange,token.exchange_id)
    a=s.scalar(select(Assignment).where(Assignment.exchange_id==token.exchange_id,Assignment.giver_id==token.giver_id))
    member=s.scalar(select(Membership).where(Membership.family_id==e.family_id,Membership.user_id==token.giver_id)) if e else None
    if not e or not a or not member:fail(404,'This exchange is no longer available')
    recipient=s.get(User,a.recipient_id)
    return {'exchange_name':e.name,'group_name':s.get(Family,e.family_id).name,'recipient_name':recipient.name,'budget':e.budget,'exchange_date':e.exchange_date}

@app.get('/api/exchanges/{eid}')
def exchange_detail(eid:int,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    e=exchange_member(s,u,eid);f=s.get(Family,e.family_id)
    people=[{'id':p.user_id,'name':s.get(User,p.user_id).name,'wish_count':s.scalar(select(func.count(Wish.id)).where(Wish.exchange_id==eid,Wish.user_id==p.user_id))} for p in s.scalars(select(Participant).where(Participant.exchange_id==eid))]
    result={'id':e.id,'name':e.name,'family_id':e.family_id,'family_name':f.name,'owner':f.owner_id==u.id,'budget':e.budget,'exchange_date':e.exchange_date,'drawn':bool(e.drawn_at),'participants':people,'reservation_mode':reservation_mode(s,eid),'exclusions':[],'my_assignment':None,'my_santa_conversation':None}
    if f.owner_id==u.id and not e.drawn_at:
        result['exclusions']=[{'giver_id':x.giver_id,'recipient_id':x.recipient_id} for x in s.scalars(select(Exclusion).where(Exclusion.exchange_id==eid))]
        rule=s.get(PreviousDrawRule,eid)
        result['previous_draw_id']=rule.source_id if rule else None
        result['previous_draws']=[{'id':x.id,'name':x.name,'date':x.exchange_date} for x in s.scalars(select(Exchange).where(Exchange.family_id==e.family_id,Exchange.id!=eid,Exchange.drawn_at!=None).order_by(Exchange.exchange_date.desc(),Exchange.id.desc())) if not e.exchange_date or (x.exchange_date and x.exchange_date<e.exchange_date)]
        result['previous_pair_count']=len(history_pairs(s,e,rule.source_id)) if rule else 0
    if e.drawn_at:
        mine=s.scalar(select(Assignment).where(Assignment.exchange_id==eid,Assignment.giver_id==u.id))
        incoming=s.scalar(select(Assignment).where(Assignment.exchange_id==eid,Assignment.recipient_id==u.id))
        if mine:
            r=s.get(User,mine.recipient_id)
            result['my_assignment']={'assignment_id':mine.id,'recipient_id':r.id,'name':r.name}
        if incoming:result['my_santa_conversation']=incoming.id
    return result

@app.post('/api/exchanges/{eid}/exclusions')
def set_exclusion(eid:int,body:ExclusionRequest,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    e=exchange_member(s,u,eid);only_owner(s,u,e.family_id)
    if e.drawn_at:fail(409,'Cannot change exclusions after drawing')
    ps={p.user_id for p in s.scalars(select(Participant).where(Participant.exchange_id==eid))}
    if body.giver_id==body.recipient_id or body.giver_id not in ps or body.recipient_id not in ps:fail(400,'Select two different participants')
    x=s.scalar(select(Exclusion).where(Exclusion.exchange_id==eid,Exclusion.giver_id==body.giver_id,Exclusion.recipient_id==body.recipient_id))
    if body.excluded and not x:s.add(Exclusion(exchange_id=eid,giver_id=body.giver_id,recipient_id=body.recipient_id))
    if not body.excluded and x:s.delete(x)
    s.commit();return {'ok':True}

def history_pairs(s,e,source_id):
    source=s.get(Exchange,source_id)
    if not source or source.id==e.id or source.family_id!=e.family_id or not source.drawn_at or (e.exchange_date and (not source.exchange_date or source.exchange_date>=e.exchange_date)):
        fail(400,'Choose a completed earlier exchange from this group')
    ids=set(s.scalars(select(Participant.user_id).where(Participant.exchange_id==e.id)))
    return {(a.giver_id,a.recipient_id) for a in s.scalars(select(Assignment).where(Assignment.exchange_id==source_id)) if a.giver_id in ids and a.recipient_id in ids}

class ExclusionPair(BaseModel):
    giver_id:int
    recipient_id:int
class ExclusionSettings(BaseModel):
    pairs:list[ExclusionPair]=Field(default_factory=list,max_length=10000)
    previous_draw_id:int|None=None

@app.put('/api/exchanges/{eid}/exclusions')
def save_exclusions(eid:int,body:ExclusionSettings,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    e=exchange_member(s,u,eid);only_owner(s,u,e.family_id)
    if e.drawn_at:fail(409,'Cannot change exclusions after drawing')
    ids=set(s.scalars(select(Participant.user_id).where(Participant.exchange_id==eid)))
    pairs={(p.giver_id,p.recipient_id) for p in body.pairs}
    if any(g==r or g not in ids or r not in ids for g,r in pairs):fail(400,'Select two different participants')
    if body.previous_draw_id is not None:history_pairs(s,e,body.previous_draw_id)
    for old in s.scalars(select(Exclusion).where(Exclusion.exchange_id==eid)):s.delete(old)
    s.flush()
    for g,r in pairs:s.add(Exclusion(exchange_id=eid,giver_id=g,recipient_id=r))
    rule=s.get(PreviousDrawRule,eid)
    if body.previous_draw_id is None:
        if rule:s.delete(rule)
    elif rule:rule.source_id=body.previous_draw_id
    else:s.add(PreviousDrawRule(exchange_id=eid,source_id=body.previous_draw_id))
    s.commit();return {'ok':True}

def draw_pairs(ids,forbidden):
    """Fair randomised search for one-to-one assignment (no self-assignments)."""
    ids=list(ids)
    allowed={giver:[r for r in ids if giver!=r and (giver,r) not in forbidden] for giver in ids}
    if any(not opts for opts in allowed.values()):return None
    # Minimum remaining values heuristic with fresh cryptographic shuffle at each level.
    def search(remaining,free,pairs):
        if not remaining:return pairs
        giver=min(remaining,key=lambda g:sum(r in free for r in allowed[g]))
        options=[r for r in allowed[giver] if r in free]
        secrets.SystemRandom().shuffle(options)
        for r in options:
            v=search([g for g in remaining if g!=giver],free-{r},pairs+[(giver,r)])
            if v is not None:return v
        return None
    return search(ids,set(ids),[])

@app.post('/api/exchanges/{eid}/draw')
def draw(eid:int,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    e=exchange_member(s,u,eid);only_owner(s,u,e.family_id)
    e=s.scalar(select(Exchange).where(Exchange.id==eid).with_for_update().execution_options(populate_existing=True))
    if e.drawn_at:fail(409,'Names have already been drawn; create a new exchange to redraw safely')
    ps=[p.user_id for p in s.scalars(select(Participant).where(Participant.exchange_id==eid))]
    if len(ps)<3:fail(400,'At least three participants are required')
    forbidden={(x.giver_id,x.recipient_id) for x in s.scalars(select(Exclusion).where(Exclusion.exchange_id==eid))}
    rule=s.get(PreviousDrawRule,eid)
    if rule:forbidden.update(history_pairs(s,e,rule.source_id))
    matched=draw_pairs(ps,forbidden)
    if matched is None:fail(422,'Exclusions make a valid draw impossible. Change the exclusions and try again.')
    for giver,receiver in matched:s.add(Assignment(exchange_id=eid,giver_id=giver,recipient_id=receiver))
    e.drawn_at=utcnow()
    for giver,receiver in matched:
        state=s.get(WishListState,(eid,receiver))
        if state and state.finalised_at:notify_finalised(s,e,receiver,giver)
    deliveries=[]
    for uid in ps:
        subject='Your gift recipient is ready to reveal'
        s.add(Notification(user_id=uid,exchange_id=eid,title=subject,detail=f'The names for {e.name} have been drawn. Open this exchange to see your recipient.'))
        person=s.get(User,uid)
        if person.notify_email:
            secret=new_token()
            s.add(RevealToken(exchange_id=eid,giver_id=uid,digest=digest(secret),expires_at=utcnow()+timedelta(days=30)))
            body=f'The draw for {e.name} is complete!\n\nClick below, then tap the covered card to reveal the person receiving your gift. No sign-in needed.\n\nReveal my recipient: {PUBLIC_URL}/#reveal={secret}\n\nThis private link reveals only your recipient and expires in 30 days. Keep it to yourself. You can also sign in to GiftCircle at any time to view your exchange.'
            deliveries.append((person.email,subject,body))
    s.commit()
    for address,subject,body in deliveries:
        try:email_send(address,subject,body)
        except Exception:log.exception('Draw email delivery failed; in-app draw remains available')
    return {'ok':True,'count':len(matched)}

def wishlist_state(s,eid,uid):
    # Existing participant row serialises finalise/edit requests for the same list.
    s.scalar(select(Participant).where(Participant.exchange_id==eid,Participant.user_id==uid).with_for_update())
    state=s.get(WishListState,(eid,uid))
    if not state:
        state=WishListState(exchange_id=eid,user_id=uid);s.add(state)
    return state

def notify_finalised(s,e,owner_id,giver_id):
    owner=s.get(User,owner_id)
    notify(s,giver_id,e.id,'Your recipient’s wish list is finalised',f'Your recipient has finalised their gift ideas for {e.name}. Open GiftCircle to view their list.')

@app.get('/api/exchanges/{eid}/wish-list/{owner_id}')
def get_wishlist_state(eid:int,owner_id:int,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    exchange_member(s,u,eid)
    if owner_id!=u.id and not s.scalar(select(Assignment).where(Assignment.exchange_id==eid,Assignment.giver_id==u.id,Assignment.recipient_id==owner_id)):
        fail(403,'You can only view your own or your assigned recipient’s wish list')
    state=s.get(WishListState,(eid,owner_id))
    return {'status':'finalised' if state and state.finalised_at else 'draft','finalised_at':stamp(state.finalised_at) if state else None}

@app.post('/api/exchanges/{eid}/wish-list/finalise')
def finalise_wishlist(eid:int,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    e=exchange_member(s,u,eid)
    state=wishlist_state(s,eid,u.id)
    if state.finalised_at:return {'ok':True,'status':'finalised'}
    if not s.scalar(select(Wish.id).where(Wish.exchange_id==eid,Wish.user_id==u.id)):
        fail(400,'Add at least one gift idea before finalising your list')
    state.finalised_at=utcnow()
    assignment=s.scalar(select(Assignment).where(Assignment.exchange_id==eid,Assignment.recipient_id==u.id))
    if assignment:notify_finalised(s,e,u.id,assignment.giver_id)
    s.commit();return {'ok':True,'status':'finalised'}

@app.post('/api/exchanges/{eid}/wish-list/draft')
def draft_wishlist(eid:int,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    exchange_member(s,u,eid)
    wishlist_state(s,eid,u.id).finalised_at=None
    s.commit();return {'ok':True,'status':'draft'}

def reservation_mode(s,eid):
    policy=s.get(ReservationPolicy,eid)
    return policy.mode if policy else 'show'

class ReservationSettings(BaseModel):
    mode:str

@app.put('/api/exchanges/{eid}/reservation-settings')
def set_reservation_mode(eid:int,body:ReservationSettings,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    e=exchange_member(s,u,eid);only_owner(s,u,e.family_id)
    if body.mode not in ('show','surprise'):fail(400,'Choose show or surprise')
    policy=s.get(ReservationPolicy,eid)
    if not policy:policy=ReservationPolicy(exchange_id=eid);s.add(policy)
    policy.mode=body.mode;s.commit();return {'ok':True,'mode':body.mode}

@app.post('/api/exchanges/{eid}/wishes/{wid}/availability')
def set_availability(eid:int,wid:int,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    exchange_member(s,u,eid)
    if reservation_mode(s,eid)!='show':fail(409,'This control is available in Show reservations mode')
    w=s.scalar(select(Wish).where(Wish.id==wid).with_for_update())
    if not w or w.exchange_id!=eid:fail(404,'Gift idea not found')
    if w.user_id!=u.id:fail(403,'Not your gift idea')
    state=s.get(WishAvailability,wid)
    if state:s.delete(state)
    else:
        if w.reserved_by:fail(409,'This gift is reserved. Message your giver before buying it yourself.')
        s.add(WishAvailability(wish_id=wid,exchange_id=eid))
    wishlist_state(s,eid,u.id).finalised_at=None
    s.commit();return {'ok':True}

@app.get('/api/exchanges/{eid}/wishes/{owner_id}')
def get_wishes(eid:int,owner_id:int,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    e=exchange_member(s,u,eid)
    if owner_id!=u.id:
        a=s.scalar(select(Assignment).where(Assignment.exchange_id==eid,Assignment.giver_id==u.id,Assignment.recipient_id==owner_id))
        if not a:fail(403,'You can only view your own or your assigned recipient’s wish list')
    return [{'id':w.id,'title':w.title,'details':w.details,'url':w.url,'price':w.price,'unavailable':bool(s.get(WishAvailability,w.id)),**(({'reserved':w.reserved_by is not None} if reservation_mode(s,eid)=='show' else {}) if owner_id==u.id else {'reserved':w.reserved_by is not None,'reserved_by_me':w.reserved_by==u.id,'purchased_by_me':bool(w.purchased and w.reserved_by==u.id)})} for w in s.scalars(select(Wish).where(Wish.exchange_id==eid,Wish.user_id==owner_id).order_by(Wish.id.desc()))]

@app.post('/api/exchanges/{eid}/wishes')
def add_wish(eid:int,body:WishCreate,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    exchange_member(s,u,eid)
    if not body.title.strip():fail(422,'Enter a gift idea')
    if body.url:
        link=urlparse(body.url)
        if link.scheme not in ('https','http') or not link.netloc:fail(400,'Use a valid http(s) URL')
    wishlist_state(s,eid,u.id).finalised_at=None
    w=Wish(exchange_id=eid,user_id=u.id,title=body.title.strip(),details=body.details,url=body.url,price=body.price);s.add(w);s.commit();return {'id':w.id}

@app.delete('/api/exchanges/{eid}/wishes/{wid}')
def delete_wish(eid:int,wid:int,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    exchange_member(s,u,eid);w=s.scalar(select(Wish).where(Wish.id==wid).with_for_update())
    if not w or w.exchange_id!=eid:fail(404,'Gift idea not found')
    if w.user_id!=u.id:fail(403,'Not your gift idea')
    # The owner must receive the same result whether or not a giver reserved it.
    wishlist_state(s,eid,u.id).finalised_at=None
    s.execute(delete(WishAvailability).where(WishAvailability.wish_id==wid))
    s.delete(w);s.commit();return {'ok':True}

@app.post('/api/exchanges/{eid}/wishes/{wid}/reserve')
def reserve(eid:int,wid:int,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    exchange_member(s,u,eid);w=s.scalar(select(Wish).where(Wish.id==wid).with_for_update())
    if not w or w.exchange_id!=eid:fail(404,'Gift idea not found')
    a=s.scalar(select(Assignment).where(Assignment.exchange_id==eid,Assignment.giver_id==u.id,Assignment.recipient_id==w.user_id))
    if not a:fail(403,'Only the assigned gift giver can reserve this item')
    if s.get(WishAvailability,wid) and not w.reserved_by:fail(409,'This gift is no longer needed')
    if w.reserved_by and w.reserved_by!=u.id:fail(409,'Already reserved')
    w.reserved_by=None if w.reserved_by==u.id else u.id
    w.purchased=False
    if reservation_mode(s,eid)=='show':
        notify(s,w.user_id,eid,'Gift reservation updated',f'{w.title}: '+('reserved — please do not buy this yourself.' if w.reserved_by else 'reservation released.'))
    s.commit();return {'reserved':bool(w.reserved_by)}

@app.post('/api/exchanges/{eid}/wishes/{wid}/purchase')
def purchase(eid:int,wid:int,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    exchange_member(s,u,eid);w=s.scalar(select(Wish).where(Wish.id==wid).with_for_update())
    if not w or w.exchange_id!=eid:fail(404,'Gift idea not found')
    if w.reserved_by!=u.id:fail(403,'Reserve this item before marking it purchased')
    w.purchased=not w.purchased;s.commit();return {'purchased':w.purchased}

class ReadMessages(BaseModel):
    through_id:int=Field(ge=1)


def conversation_filter(s,u,eid,channel):
    if channel=='group':return Message.kind.in_(['group','announcement'])
    if channel not in ('giver','santa'):fail(422,'Unknown conversation')
    role=Assignment.giver_id if channel=='giver' else Assignment.recipient_id
    assignment=s.scalar(select(Assignment).where(Assignment.exchange_id==eid,role==u.id))
    if not assignment:fail(404,'Conversation not found')
    return and_(Message.kind=='private',Message.assignment_id==assignment.id)


@app.get('/api/messages/unread')
def unread_messages(u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    counts={}
    # Three aggregate queries regardless of the number of exchanges or messages.
    for channel in ('giver','santa','group'):
        query=(select(Message.exchange_id,func.count(Message.id))
            .join(Exchange,Exchange.id==Message.exchange_id)
            .join(Membership,and_(Membership.family_id==Exchange.family_id,Membership.user_id==u.id))
            .join(Participant,and_(Participant.exchange_id==Exchange.id,Participant.user_id==u.id))
            .outerjoin(MessageReadState,and_(MessageReadState.exchange_id==Exchange.id,
                MessageReadState.user_id==u.id,MessageReadState.channel==channel))
            .where(Message.sender_id!=u.id,Message.id>func.coalesce(MessageReadState.last_message_id,0)))
        if channel=='group':query=query.where(Message.kind.in_(['group','announcement']))
        else:
            role=Assignment.giver_id if channel=='giver' else Assignment.recipient_id
            query=query.join(Assignment,and_(Assignment.id==Message.assignment_id,
                Assignment.exchange_id==Exchange.id,role==u.id)).where(Message.kind=='private')
        for eid,count in s.execute(query.group_by(Message.exchange_id)):
            counts.setdefault(eid,{'giver':0,'santa':0,'group':0,'total':0})[channel]=count
            counts[eid]['total']+=count
    return {'total':sum(row['total'] for row in counts.values()),'exchanges':counts}


@app.post('/api/exchanges/{eid}/messages/read/{channel}')
def read_messages(eid:int,channel:str,body:ReadMessages,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    exchange_member(s,u,eid)
    condition=conversation_filter(s,u,eid,channel)
    # Only acknowledge a message actually returned by this conversation, never
    # a future/global ID. A message arriving during the request stays unread.
    message=s.scalar(select(Message).where(Message.id==body.through_id,Message.exchange_id==eid,condition))
    if not message:fail(404,'Message not found in this conversation')
    # Serialise simultaneous acknowledgements (including initial creation).
    s.scalar(select(Participant).where(Participant.exchange_id==eid,Participant.user_id==u.id).with_for_update())
    state=s.get(MessageReadState,(eid,u.id,channel))
    if state:state.last_message_id=max(state.last_message_id,body.through_id)
    else:s.add(MessageReadState(exchange_id=eid,user_id=u.id,channel=channel,last_message_id=body.through_id))
    s.commit()
    return {'ok':True}


@app.get('/api/exchanges/{eid}/messages/{assignment_id}')
def private_messages(eid:int,assignment_id:int,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    exchange_member(s,u,eid);a=s.get(Assignment,assignment_id)
    if not a or a.exchange_id!=eid:fail(404,'Conversation not found')
    if u.id not in (a.giver_id,a.recipient_id):fail(403,'Not your conversation')
    other=s.get(User,a.recipient_id if u.id==a.giver_id else a.giver_id)
    label=other.name if u.id==a.giver_id else 'Your Mystery Gifter'
    ms=s.scalars(select(Message).where(Message.assignment_id==assignment_id,Message.kind=='private').order_by(Message.id)).all()
    return {'label':label,'messages':[{'id':m.id,'content':m.content,'mine':m.sender_id==u.id,'created_at':stamp(m.created_at)} for m in ms]}

@app.post('/api/exchanges/{eid}/messages/{assignment_id}')
def send_private(eid:int,assignment_id:int,body:MessageCreate,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    if not body.content.strip():fail(422,'Enter a message')
    exchange_member(s,u,eid);a=s.get(Assignment,assignment_id)
    if not a or a.exchange_id!=eid:fail(404,'Conversation not found')
    if u.id not in (a.giver_id,a.recipient_id):fail(403,'Not your conversation')
    recipient=a.recipient_id if u.id==a.giver_id else a.giver_id
    s.add(Message(exchange_id=eid,assignment_id=assignment_id,sender_id=u.id,kind='private',content=body.content.strip()))
    notify(s,recipient,eid,'New anonymous message',"You've received a private message in your gift exchange.",link=f'/#messages/{eid}/{"santa" if recipient==a.recipient_id else "giver"}')
    s.commit();return {'ok':True}

@app.get('/api/exchanges/{eid}/group-messages')
def group_messages(eid:int,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    exchange_member(s,u,eid)
    return [{'id':m.id,'content':m.content,'name':s.get(User,m.sender_id).name,'mine':m.sender_id==u.id,'kind':m.kind,'created_at':stamp(m.created_at)} for m in s.scalars(select(Message).where(Message.exchange_id==eid,Message.kind.in_(['group','announcement'])).order_by(Message.id))]

@app.post('/api/exchanges/{eid}/group-messages')
def send_group(eid:int,body:MessageCreate,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    if not body.content.strip():fail(422,'Enter a message')
    e=exchange_member(s,u,eid)
    s.add(Message(exchange_id=eid,sender_id=u.id,kind='group',content=body.content.strip()))
    for p in s.scalars(select(Participant).where(Participant.exchange_id==eid)):
        if p.user_id!=u.id:notify(s,p.user_id,eid,f'New group message: {e.name}',f'{u.name} posted a message in {e.name}.',link=f'/#messages/{eid}/group')
    s.commit();return {'ok':True}

@app.post('/api/exchanges/{eid}/announcements')
def announce(eid:int,body:MessageCreate,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    if not body.content.strip():fail(422,'Enter a message')
    e=exchange_member(s,u,eid);only_owner(s,u,e.family_id)
    s.add(Message(exchange_id=eid,sender_id=u.id,kind='announcement',content=body.content.strip()))
    for p in s.scalars(select(Participant).where(Participant.exchange_id==eid)):
        if p.user_id!=u.id:notify(s,p.user_id,eid,f'Announcement: {e.name}',body.content[:450],link=f'/#messages/{eid}/group')
    s.commit();return {'ok':True}

@app.get('/api/notifications')
def notifications(u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    return [{'id':n.id,'exchange_id':n.exchange_id,'title':n.title,'detail':n.detail,'read':bool(n.read_at),'created_at':stamp(n.created_at)} for n in s.scalars(select(Notification).where(Notification.user_id==u.id).order_by(Notification.id.desc()).limit(40))]

@app.post('/api/notifications/{nid}/read')
def notification_read(nid:int,u:User=Depends(user_or_401),s:DBSession=Depends(db)):
    n=s.get(Notification,nid)
    if not n or n.user_id!=u.id:fail(404,'Notification not found')
    n.read_at=utcnow();s.commit();return {'ok':True}

@app.get('/')
def root():return FileResponse(STATIC/'index.html')

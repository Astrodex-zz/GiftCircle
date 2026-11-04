/* GiftCircle: dependency-free, self-hosted responsive client. MIT License. */
'use strict';
const $ = (s,root=document)=>root.querySelector(s);
const esc = s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = v=>'$'+Number(v||0).toLocaleString('en-AU');
const glyph = {home:'⌂',wish:'♡',chat:'☏',family:'♧',alerts:'♧',settings:'⚙',gift:'🎁',mail:'✉',plus:'＋'};
const appState={me:null,families:[],invitations:[],fid:null,exchanges:[],eid:null,exchange:null,page:'home',chat:'giver',sending:false,unread:{total:0,exchanges:{}}};
const namePrompted=new Set();
let modalOpen=false,refreshing=false,toastTimer=null;
async function api(path,opts={}){
  const res=await fetch('/api'+path,{credentials:'same-origin',...opts,headers:{...(opts.body?{'Content-Type':'application/json'}:{}),...opts.headers}});
  let data={};try{data=await res.json()}catch{}
  if(!res.ok)throw new Error(typeof data.detail==='string'?data.detail:`Request failed (${res.status})`);
  return data;
}
const send=(path,body,method='POST')=>api(path,{method,body:JSON.stringify(body)});
function toast(msg,error=false){clearTimeout(toastTimer);$('#toast')?.remove();const n=document.createElement('div');n.id='toast';n.className='toast'+(error?' error':'');n.textContent=msg;document.body.append(n);toastTimer=setTimeout(()=>n.remove(),4600)}
function h(head,sub='',actions=''){return `<header class="page-head"><div><div class="eyebrow">${esc(sub||'GiftCircle')}</div><h1>${esc(head)}</h1></div>${actions?`<div class="header-actions">${actions}</div>`:''}</header>`}
function btn(label,act,type='secondary',size=''){if(act.endsWith(':messages'))label+=unreadBadge(act.split(':')[1]);return `<button type="button" class="btn ${type} ${size}" data-action="${act}">${label}</button>`}
const planeIcon='<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg>';
const mailIcon='<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 6 9 7 9-7"/></svg>';
function unreadCount(eid='all',channel='total'){return eid==='all'?appState.unread.total||0:appState.unread.exchanges?.[eid]?.[channel]||0}
function unreadBadge(eid='all',channel='total'){const n=unreadCount(eid,channel);return `<span class="unread-badge" data-unread-eid="${eid}" data-unread-channel="${channel}" aria-label="${n} unread messages" ${n?'':'hidden'}>${n}</span>`}
function paintUnread(){
 document.querySelectorAll('[data-unread-eid]').forEach(b=>{const n=unreadCount(b.dataset.unreadEid,b.dataset.unreadChannel);b.textContent=n;b.hidden=!n;b.setAttribute('aria-label',n+' unread messages');b.closest('button')?.classList.toggle('has-unread',n>0)});
 document.querySelectorAll('#exchange-select option').forEach(o=>{const e=appState.exchanges.find(x=>x.id===Number(o.value));if(e)o.textContent=e.name+' · '+e.family_name+(unreadCount(e.id)?' ('+unreadCount(e.id)+' unread)':'')});
}
let unreadRequest=0;
async function refreshUnread(){const request=++unreadRequest;const result=await api('/messages/unread');if(request===unreadRequest){appState.unread=result;paintUnread()}}
async function acknowledgeMessages(body){
 if(!body||!body.dataset.through||document.hidden||appState.page!=='messages'||body!==$('#chat-body'))return;
 const {eid,channel,through}=body.dataset;
 try{await send(`/exchanges/${eid}/messages/read/${channel}`,{through_id:Number(through)});await refreshUnread()}catch{/* Retry on the next visible refresh. */}
}
async function openMessages(eid=null){
 const selected=appState.exchanges.find(e=>e.id===Number(eid))||appState.exchanges.find(e=>e.id===appState.eid&&unreadCount(e.id))||appState.exchanges.find(e=>unreadCount(e.id))||appState.exchanges.find(e=>e.id===appState.eid)||appState.exchanges[0];
 if(selected){appState.eid=selected.id;appState.fid=selected.family_id;appState.chat=['giver','santa','group'].find(c=>unreadCount(selected.id,c))||'giver'}
 appState.page='messages';await sync(true);
}
function card(inner,classes=''){return `<section class="card ${classes}">${inner}</section>`}
function empty(icon,title,detail,action=''){return `<div class="empty"><div class="em-icon">${icon}</div><h3>${esc(title)}</h3><p>${esc(detail)}</p>${action}</div>`}
function popup(title,desc,body,submitLabel,onSubmit){
 modalOpen=true;
 const bg=document.createElement('div');bg.className='modal-backdrop';bg.id='modal-root';
 bg.innerHTML=`<div class="modal" role="dialog" aria-modal="true" aria-label="${esc(title)}"><div class="flex between"><h2>${esc(title)}</h2><button class="btn secondary small" type="button" id="modal-close" aria-label="Close">✕</button></div>${desc?`<p>${esc(desc)}</p>`:''}<form id="dialog-form">${body}<div id="dialog-error" class="danger-note"></div><div class="modal-foot"><button type="button" class="btn outline" id="modal-cancel">Cancel</button><button type="submit" class="btn" id="modal-submit">${esc(submitLabel)}</button></div></form></div>`;
 const dismiss=()=>{bg.remove();modalOpen=false};
 let outsidePress=false,outsideRelease=false;
 bg.addEventListener('pointerdown',e=>{outsidePress=e.target===bg&&e.isPrimary&&e.button===0;outsideRelease=false});
 bg.addEventListener('pointerup',e=>{outsideRelease=outsidePress&&document.elementFromPoint(e.clientX,e.clientY)===bg});
 bg.addEventListener('pointercancel',()=>{outsidePress=false;outsideRelease=false});
 bg.addEventListener('click',e=>{const close=e.target===bg&&outsidePress&&outsideRelease;outsidePress=false;outsideRelease=false;if(close)dismiss()});
 document.body.append(bg);$('#modal-close').onclick=dismiss;$('#modal-cancel').onclick=dismiss;
 $('#dialog-form').onsubmit=async e=>{e.preventDefault();const b=$('#modal-submit');b.disabled=true;b.textContent='Working…';try{await onSubmit(new FormData(e.target),e.target);dismiss();await sync(true)}catch(err){$('#dialog-error').textContent=err.message;b.disabled=false;b.textContent=submitLabel}};
 bg.querySelector('input,textarea,select')?.focus();
}
async function sync(force=false){
 if(refreshing)return;refreshing=true;
 try{
  const priorEid=appState.eid,priorFid=appState.fid;
  appState.me=await api('/me');
  appState.families=await api('/families');
  appState.invitations=await api('/invites');
  if(!appState.families.some(f=>f.id===appState.fid))appState.fid=appState.families[0]?.id||null;
  appState.exchanges=await api('/exchanges');
  await refreshUnread();
  if(!appState.exchanges.some(x=>x.id===appState.eid))appState.eid=(appState.page==='family'?appState.exchanges.find(x=>x.family_id===appState.fid):appState.exchanges[0])?.id||null;
  const routeExchange=location.hash.match(/^#exchanges\/(\d+)$/);
  if(routeExchange&&appState.page==='family'&&appState.exchanges.some(x=>x.id===Number(routeExchange[1])))appState.fid=appState.exchanges.find(x=>x.id===Number(routeExchange[1])).family_id;
  if(priorEid&&!appState.exchanges.some(x=>x.id===priorEid)&&['family','wishes','messages','exclusions'].includes(appState.page))appState.page='home';
  if(priorFid&&!appState.families.some(x=>x.id===priorFid)&&appState.page==='family')appState.page='groups';
  appState.exchange=appState.eid?await api('/exchanges/'+appState.eid):null;
  if(!modalOpen||force)await render();
  if(!modalOpen&&!appState.me.name_confirmed&&!namePrompted.has(appState.me.id)){namePrompted.add(appState.me.id);editName(true)}
 }catch(err){if(err.message==='Please sign in'||err.message==='Session expired'){appState.me=null;renderAuth()}else toast(err.message,true)}
 finally{refreshing=false}
}
function authLanding(message=''){
 return `<div class="auth-page"><header class="auth-header"><a class="logo" href="/"><span class="logo-mark">♔</span> giftcircle<span style="color:#e2b772">.</span></a><span class="auth-trust">♢ &nbsp; Private by design</span></header><main class="auth-body"><div class="hero"><div class="hero-kicker">● &nbsp; The nicer way to give</div><h1>Make memories.<br><em>Not spreadsheets.</em></h1><p>A calm, thoughtful home for group gift exchanges. Exchange names, share wish lists and keep the surprises secret — without the clutter.</p><div class="chips"><span class="chip">✓ &nbsp; No ads, ever</span><span class="chip">✓ &nbsp; Private groups</span><span class="chip">✓ &nbsp; Anonymous messages</span></div></div><div class="auth-card"><div class="sign-icon">♔</div><h2>Welcome to GiftCircle</h2><p>Enter your email address and we'll send you a secure sign-in link. No password to remember.</p>${message?`<div class="info-banner">${esc(message)}</div>`:''}<form id="login-form"><div class="field"><label for="email">Email address</label><input id="email" name="email" type="email" placeholder="you@example.com" autocomplete="email" required></div><button class="btn full" type="submit" id="login-submit">Send sign-in link &nbsp; →</button></form><div class="footnote">♙ &nbsp; Your email stays private. No ads, no tracking.</div></div></main><footer class="auth-footer">Made for people you know &nbsp; ✳ &nbsp; Self-hosted & open source</footer></div>`;
}
function renderAuth(msg=''){
 $('#app').innerHTML=authLanding(msg);
 $('#login-form').onsubmit=async e=>{e.preventDefault();const btn=$('#login-submit');btn.disabled=true;btn.textContent='Sending…';try{await send('/auth/request',{email:$('#email').value,return_to:location.hash});renderAuth('Sign-in link sent. Check your inbox (and spam folder).')}catch(err){toast(err.message,true);btn.disabled=false;btn.textContent='Send sign-in link →'}};
}
function navLink(page,title,g){return `<button class="${appState.page===page?'active':''}" data-page="${page}"><span class="glyph">${g}</span>${title}${page==='messages'?unreadBadge():''}</button>`}
function editName(first=false){
 popup(first?'What should we call you?':'Edit your name',`Signed in as ${appState.me.email}`,`<div class="field"><label for="display-name">Your name</label><input id="display-name" name="name" autocomplete="name" required maxlength="100" value="${esc(appState.me.name)}"></div>`,'Save name',async f=>{await send('/me',{name:f.get('name'),notify_email:appState.me.notify_email},'PATCH');toast('Name saved')});
}
function accountIdentity(){return `<div class="account-identity" aria-label="Signed-in account"><span class="muted-label">Signed in as</span><div class="account-name-row"><strong>${esc(appState.me.name)}</strong><button class="name-edit" data-action="edit-name" aria-label="Edit your name" title="Edit your name">✎</button>${!appState.me.name_confirmed?btn('Add name','edit-name','outline small'):''}</div><span class="account-email">${esc(appState.me.email)}</span><div class="account-signout">${btn("Sign out","logout","account-signout-button")}</div></div>`}
function shell(body){
 const initials=appState.me.name.slice(0,1).toUpperCase();
 return `<div class="shell"><aside class="sidebar"><a href="/" class="logo"><span class="logo-mark">♔</span> giftcircle<span style="color:#e2b772">.</span></a><div><div class="side-label">YOUR SPACE</div><nav class="nav">${navLink('home','Overview','⌂')}${navLink('messages','Messages',mailIcon)}${navLink('groups','Groups','♧')}${navLink('alerts','Notifications','♢')}${navLink('settings','Settings','⚙')}</nav></div><div><div class="side-label">YOUR EXCHANGES</div><div class="exchange-list">${appState.exchanges.map(x=>`<button data-exchange="${x.id}" class="${x.id===appState.eid?'active':''}"><span>🎁</span><span>${esc(x.name)}</span>${unreadBadge(x.id)}</button>`).join('')||'<span class="dim tiny" style="padding:0 13px">No exchanges yet</span>'}</div></div><div class="sidebar-bottom"><div class="avatar">${esc(initials)}</div><div class="grow"><div class="who">${esc(appState.me.name)}</div><div class="email">${esc(appState.me.email)}</div></div></div></aside><div class="mobile-head"><span class="logo"><span class="logo-mark">♔</span> giftcircle<span style="color:#e2b772">.</span></span><div class="avatar" style="width:31px;height:31px" data-page="settings">${esc(initials)}</div></div><main class="main" id="content">${accountIdentity()}${body}</main><nav class="mobile-bar">${[['home','⌂','Home'],['messages',mailIcon,'Messages'],['groups','♧','Groups'],['settings','⚙','More']].map(x=>`<button data-page="${x[0]}" class="${appState.page===x[0]?'active':''}"><span class="glyph">${x[1]}</span>${x[2]}${x[0]==='messages'?unreadBadge():''}</button>`).join('')}</nav></div>`;
}
function exchangeSelect(){return `<label class="exchange-picker" for="exchange-select"><span>Exchange</span><select class="select-inline" id="exchange-select">${appState.exchanges.map(e=>`<option value="${e.id}" ${e.id===appState.eid?'selected':''}>${esc(e.name)} · ${esc(e.family_name)}</option>`).join('')}</select></label>`;}

function exchangePageHeader(title,e,actions=''){
 return h(title,'GiftCircle',actions)+`<section class="active-exchange" aria-label="Selected exchange"><span class="muted-label">Current exchange</span><h2>${esc(e.name)}</h2><p>${esc(e.family_name)}${e.exchange_date?' · '+esc(e.exchange_date):''}</p>${exchangeSelect().replace('<span>Exchange</span>','<span>Change exchange</span>')}</section>`;
}
function groupsOverview(){
 return card(`<div class="flex between wrap"><h2 class="card-title">Your groups</h2></div>${appState.families.map(f=>`<div class="list-row"><div><button class="group-name-link" data-group="${f.id}">${esc(f.name)}</button> <span class="pill">${f.owner_id===appState.me.id?'Admin':'Member'}</span><div class="dim tiny">${appState.exchanges.filter(e=>e.family_id===f.id).length} exchanges · Group #${f.id}</div></div><button class="btn secondary small" data-group="${f.id}">Open group</button></div>`).join('')||'<p class="dim">No groups yet. Accept an invitation below or create a group.</p>'}`)+
 (appState.invitations.length?card(`<h2 class="card-title">Your invitations</h2>${appState.invitations.map(i=>`<div class="list-row"><div><strong>${esc(i.family_name)}</strong>${(i.welcomes||[]).map(w=>`<div class="invite-welcome"><b>${esc(w.name)}</b><p>${esc(w.message)}</p></div>`).join('')}</div>${btn('Accept invitation','accept-invite:'+i.id,'primary small')}</div>`).join('')}`):'');
}
function isPastExchange(e){
 const now=new Date();const today=[now.getFullYear(),String(now.getMonth()+1).padStart(2,'0'),String(now.getDate()).padStart(2,'0')].join('-');
 return !!e.exchange_date&&e.exchange_date<today;
}
function recipientSpotlight(e){
 const recipient=e.my_recipient||e.my_assignment;
 return `<div class="recipient-spotlight"><span class="muted-label">${recipient?'You’re gifting to':'Your gift recipient'}</span><strong>${recipient?esc(recipient.name):e.drawn?'No recipient assigned':'Names haven’t been drawn yet'}</strong></div>`;
}
function overviewExchangeCard(e){
 const admin=appState.families.find(f=>f.id===e.family_id)?.owner_id===appState.me.id;
 return card(`<div class="flex between wrap"><span class="eyebrow" style="margin:0">Gift exchange</span><span class="pill">${e.drawn?'Names drawn':'Preparing'}</span></div><h3 class="exchange-card-title">${esc(e.family_name)} · ${esc(e.name)} <span aria-hidden="true">✨</span></h3>${recipientSpotlight(e)}<p class="dim tiny">${e.exchange_date?'Gift day: '+esc(e.exchange_date)+' · ':''}${money(e.budget)} gift budget</p><p class="dim">${e.drawn?'Names have been drawn. Open your wish list or messages to plan your gifts.':admin?'Invite your group and draw names when everyone is ready.':'Your organiser will draw names when everyone is ready.'}</p><div class="flex wrap">${btn('♡ &nbsp; My Wish List',`exchange-page:${e.id}:wishes`,'primary')}${btn(mailIcon+' Messages',`exchange-page:${e.id}:messages`,'outline')}${btn('♧ &nbsp; Group',`exchange-page:${e.id}:family`,'outline')}</div>`,'recipient-card overview-exchange-card').replace('<section ',`<section data-exchange="${e.id}" tabindex="0" role="link" aria-label="Open ${esc(e.family_name)} · ${esc(e.name)}" `);
}
function homeScreen(){
 const current=appState.exchanges.filter(e=>!isPastExchange(e));
 const past=appState.exchanges.filter(isPastExchange);
 return h('Overview','Welcome home',btn('＋ Create group','new-family','primary'))+groupsOverview()+`<section class="overview-exchanges"><div class="flex between wrap"><h2 class="section-title">Exchanges</h2>${past.length?btn('Past exchanges ('+past.length+') →','past-exchanges','outline small'):''}</div><div class="stack">${current.map(overviewExchangeCard).join('')||card(empty('🎁','No current exchanges','Open a group to create an exchange or view your past exchanges.'))}</div></section>`;
}
function pastExchangesScreen(){
 const past=appState.exchanges.filter(isPastExchange).sort((a,b)=>b.exchange_date.localeCompare(a.exchange_date));
 return h('Past exchanges','Previous gift days',btn('← Overview','home','outline'))+`<p class="dim">Exchanges whose gift date has passed. Your lists and messages remain available.</p><div class="stack">${past.map(overviewExchangeCard).join('')||card(empty('🎁','No past exchanges','Exchanges appear here after their gift date.'))}</div>`;
}
function actionTile(icon,title,detail,act){return `<button class="action-tile" data-action="${act}"><span class="tile-icon">${icon}</span><span><strong>${esc(title)}</strong><div class="dim">${esc(detail)}</div></span></button>`}
function compactWishList(e,wishes,mine,finalised){
 const show=e.reservation_mode==='show';
 const rows=wishes.map(w=>{
  const status=mine?(show?(w.unavailable?'No longer needed':w.reserved?'Reserved — don’t buy yourself':'Not reserved'):''):(w.unavailable?'No longer needed':w.purchased_by_me?'Bought':w.reserved?'Reserved':'Available');
  const controls=mine?`${show&&!w.reserved?btn(w.unavailable?'Make available':'No longer needed',`availability:${w.id}`,'outline small'):''}<button class="btn outline small" data-delete-wish="${w.id}" aria-label="Remove ${esc(w.title)}">Remove</button>`:`${(!w.unavailable&&!w.reserved)||w.reserved_by_me?btn(w.reserved_by_me?'Unreserve':'Reserve',`reserve:${w.id}`,w.reserved_by_me?'outline small':'primary small'):''}${w.reserved_by_me?btn(w.purchased_by_me?'Undo bought':'Mark bought',`purchase:${w.id}`,'outline small'):''}`;
  return `<article class="compact-gift-row"><div class="compact-gift-info"><div class="compact-gift-title"><h3>${esc(w.title)}</h3>${w.price?`<span class="wish-price">${esc(w.price)}</span>`:''}${status?`<span class="pill gray">${esc(status)}</span>`:''}</div>${w.details?`<p>${esc(w.details)}</p>`:''}${w.url?`<a target="_blank" rel="noopener noreferrer" href="${esc(w.url)}">View gift ↗</a>`:''}</div><div class="compact-gift-actions">${controls}</div></article>`;
 }).join('');
 const finalise=mine?(finalised?btn('Mark as Draft','draft-list','outline small'):`<button class="btn primary small" data-action="finalise-list" ${wishes.length?'':'disabled'}>Finalise list</button>`):'';
 return `<section class="compact-wishlist"><header class="compact-list-header"><div><h2>${mine?'My wish list':'Gift ideas for '+esc(e.my_assignment.name)}</h2><span class="pill ${finalised?'':'gold'}">${finalised?'Finalised':'Draft'}</span></div><div class="compact-gift-actions">${mine?btn('＋ Add a gift','new-wish','primary small'):''}${finalise}</div></header><p class="compact-list-note">${mine?(show?'Reserved ideas are labelled. Your giver’s identity stays private.':'Surprise mode: your giver’s reservations stay private.'):(show?'Reservations are visible to your recipient. Your identity stays private.':'Surprise mode: your recipient cannot see your reservations.')}${mine?' Finalising notifies your giver'+(e.drawn?'.':' after names are drawn.'):(finalised?'':' This list is still being worked on.')}</p><div class="compact-gift-list">${rows||`<p class="compact-empty">${mine?'No ideas yet—add your first gift above.':'No gift ideas yet.'}</p>`}</div></section>`;
}
async function wishesScreen(ownerOverride=null,embedded=false){const e=appState.exchange;if(!e)return h('Wish lists')+empty('♡','No exchange yet','Create a group and exchange first.');
 let owner=ownerOverride||appState.wishTarget||appState.me.id;
 if(owner!==appState.me.id&&(!e.my_assignment||owner!==e.my_assignment.recipient_id))owner=appState.me.id;
 let wishes=await api(`/exchanges/${e.id}/wishes/${owner}`);
 const mine=owner===appState.me.id;
 const listState=await api(`/exchanges/${e.id}/wish-list/${owner}`);
 const finalised=listState.status==='finalised';
 const head=exchangePageHeader(mine?'My wish list':`${e.my_assignment.name}'s wish list`,e,mine?'':btn('← &nbsp; My wish list','own-wishes','outline'));
 const tabs=`<div class="tabstrip" style="margin-bottom:18px"><button data-action="own-wishes" class="${mine?'active':''}">My list</button>${e.my_assignment?`<button data-action="recipient-wishes" class="${!mine?'active':''}">${esc(e.my_assignment.name)}'s list</button>`:''}</div>`;
 const showReservations=e.reservation_mode==='show';
 const note=`<div class="info-banner">${showReservations?(mine?'Show reservations mode: reserved gifts are labelled below. Your giver’s identity and purchase status stay private. Unreserved ideas may still be chosen later.':'Show reservations mode: your recipient sees reservations and is notified when you reserve or release a gift. Your identity and purchase status stay private.'):'Surprise mode: reservations and purchases stay hidden from the recipient.'}${e.owner&&!embedded?' '+btn('Change mode','reservation-mode','outline small'):''}</div>`;

 const addCard=mine?`<button class="wish-card add-gift-card" data-action="new-wish"><span class="add-gift-plus" aria-hidden="true">＋</span><strong>Add a gift</strong><span class="dim tiny">A gift, a hobby, or a little hint</span></button>`:'';
 const statusCard=card(`<div class="flex between wrap"><div><span class="pill ${finalised?'':'gold'}">${finalised?'Finalised':'Draft'}</span><p class="dim tiny">${mine?(finalised?'Your list is ready. Adding or removing an idea returns it to Draft.':"Still working on your ideas? Finalise your list when you're ready." ):(finalised?'Your recipient has finished this version of their list.':'Your recipient is still working on this list. Ideas may change.')}</p>${mine?`<p class="dim tiny">${e.drawn?'Finalising notifies your gift giver in GiftCircle and by email if they have email notifications enabled.':'Finalise now and your gift giver will be notified after names are drawn.'}</p>`:''}</div>${mine?(finalised?btn('Mark as Draft','draft-list','outline'):`<button class="btn primary" data-action="finalise-list" ${wishes.length?'':'disabled'}>Finalise list</button>`):''}</div>`,'wish-status');
 const items=(mine||wishes.length)?`<div class="wishlist-grid">${addCard}${wishes.map(w=>`<article class="wish-card"><div class="flex between"><span class="tile-icon">🎁</span>${mine?`<button class="text-only" data-delete-wish="${w.id}" aria-label="Delete gift idea">Remove</button>`:`<span class="pill ${w.purchased_by_me?'':'gray'}">${w.unavailable?'No longer needed':w.purchased_by_me?'Purchased':w.reserved_by_me?'Reserved':w.reserved?'Reserved':'Available'}</span>`}</div><h3>${esc(w.title)}</h3>${mine&&showReservations?`<span class="pill ${w.reserved?'gold':'gray'}">${w.unavailable?'Bought for myself / no longer needed':w.reserved?'Reserved — don’t buy this yourself':'Not reserved'}</span>${!w.reserved?btn(w.unavailable?'Make available again':'Bought for myself / no longer needed',`availability:${w.id}`,'outline small'):''}`:''}<div class="wish-detail">${esc(w.details||'A lovely gift idea.')}</div>${w.price?`<span class="wish-price">${esc(w.price)}</span>`:''}${w.url?`<a class="wish-link" target="_blank" rel="noopener noreferrer" href="${esc(w.url)}">View gift idea ↗</a>`:''}${!mine?`<div class="flex wrap" style="margin-top:8px">${(!w.unavailable&&!w.reserved)||w.reserved_by_me?btn(w.reserved_by_me?'Unreserve':'Reserve this gift',`reserve:${w.id}`,w.reserved_by_me?'outline small':'primary small'):''}${w.reserved_by_me?btn(w.purchased_by_me?'Mark unpurchased':'Mark purchased',`purchase:${w.id}`,'secondary small'):''}</div>`:''}</article>`).join('')}</div>`:card(empty('♡',mine?'Your wish list is a blank canvas':'No gift ideas yet',mine?'Add a few hints—specific gifts, favourite hobbies, or even something wonderfully simple.':'Your recipient has not added gift ideas. You can send them an anonymous message.',btn(mine?'Add your first idea':'Ask a question',mine?'new-wish':'chat-giver','primary')));
 const context=`<section class="card wish-context" aria-label="Wish list exchange and people"><div class="wish-people"><div><span class="muted-label">Gift recipient</span><strong>${esc(mine?appState.me.name:e.my_assignment.name)}${mine?' (you)':''}</strong></div><div><span class="muted-label">Gift giver</span><strong>${mine?(e.drawn?'Your Mystery Gifter · identity hidden':'Not assigned — names not drawn'):esc(appState.me.name)+' (you)'}</strong></div></div><p class="dim tiny">These ideas belong only to this exchange. Other exchanges have separate wish lists.</p></section>`;
 if(embedded)return compactWishList(e,wishes,mine,finalised);
 return head+context+tabs+note+statusCard+items;
}
async function messagesScreen(){const e=appState.exchange;if(!e)return h('Messages')+empty('☏','No exchange yet','Join an exchange to start chatting.');
 const modes=[...(e.my_assignment?[['giver','My recipient']]:[]),...(e.my_santa_conversation?[['santa','My Mystery Gifter']]:[]),['group','Group chat']];
 if(!modes.some(x=>x[0]===appState.chat))appState.chat=modes[0][0];
 const tabs=`<div class="tabstrip message-tabs" style="margin-bottom:17px">${modes.map(([id,label])=>`<button data-chat="${id}" class="${appState.chat===id?'active':''}">${esc(label)}${unreadBadge(e.id,id)}</button>`).join('')}</div>`;
 let label='',description='',records=[],kind=appState.chat;
 if(kind==='group'){
  label='Group conversation';description='Everyone in '+e.name+' can read this conversation.';records=await api(`/exchanges/${e.id}/group-messages`);
 }else{
  const id=kind==='giver'?e.my_assignment?.assignment_id:e.my_santa_conversation;
  if(id){const result=await api(`/exchanges/${e.id}/messages/${id}`);label=result.label;description=kind==='giver'?'Your identity stays hidden from your recipient.':'You can reply without knowing who your gift giver is.';records=result.messages}
 }
 const messages=records.map(m=>`<div class="chat-entry ${m.mine?'mine':''}"><div class="bubble">${esc(m.content)}</div><div class="meta">${kind==='group'&&!m.mine?esc(m.name)+' · ':''}${m.mine?'You · ':''}${esc(m.created_at?new Date(m.created_at).toLocaleTimeString([],{hour:'numeric',minute:'2-digit'}):'')}</div></div>`).join('');
 return exchangePageHeader('Messages',e)+tabs+(kind!=='group'?`<div class="info-banner">♙ &nbsp; Anonymous conversation. Only you and the other participant can see these messages. The organiser cannot read them.</div>`:'')+`<div class="card chat"><div class="chat-heading"><span class="tile-icon">${kind==='group'?'♧':mailIcon}</span><div><strong>${esc(label)}</strong><div class="sub">${esc(description)}</div></div></div><div class="chat-body" id="chat-body" data-eid="${e.id}" data-channel="${kind}" data-through="${records.length?records[records.length-1].id:''}">${messages||`<div class="empty"><div class="em-icon">${mailIcon}</div><h3>No messages yet</h3><p>${kind==='group'?'Say hello to your group!':'Send a friendly question to get the conversation started.'}</p></div>`}</div><form class="composer" id="message-form"><textarea aria-label="Write a message" name="message" placeholder="Write a message…" required maxlength="3000"></textarea><button class="btn send-message" type="submit" aria-label="Send message" title="Send message">${planeIcon}</button></form></div>`;
}
function exclusionSummary(e,preview=false){
 const pairs=e.exclusions||[], source=(e.previous_draws||[]).find(x=>x.id===e.previous_draw_id);
 const rules=e.participants.map(g=>{const names=pairs.filter(x=>x.giver_id===g.id).map(x=>esc(e.participants.find(p=>p.id===x.recipient_id)?.name));return names.length?`<li><strong>${esc(g.name)}</strong> cannot give to ${names.join(', ')}.</li>`:''}).join('');
 return `<div class="exclusion-summary"><strong>${preview?'Your selections — not saved yet':'Saved exclusions'}</strong>${rules?`<ul>${rules}</ul>`:'<p>No manual exclusions.</p>'}${source?`<p>Exclude repeat pairings from <strong>${esc(source.name)}</strong>. Only current participants are included; previous assignments remain private.</p>`:'<p>Previous-draw protection is off.</p>'}</div>`;
}
function exclusionsScreen(){const e=appState.exchange;if(!e?.owner||e.drawn)return h('Exclusions')+card('<p>Exclusions can only be changed by the organiser before drawing.</p>');return h('Exclusions',e.family_name+' · '+e.name,btn('Back to group','family','outline'))+card(`<h2 class="card-title">${esc(e.family_name)}</h2><p class="subline">${esc(e.name)} · ${e.participants.length} participants</p>${exclusionSettings(e)}`);}
function exclusionSettings(e){
 const pairs=e.exclusions||[], previous=e.previous_draws||[];
 const label=id=>e.participants.find(p=>p.id===id)?.name||'Former participant';
 const rules=e.participants.map(p=>{const names=pairs.filter(x=>x.giver_id===p.id).map(x=>esc(label(x.recipient_id)));return names.length?`<li><strong>${esc(p.name)}</strong> cannot give to ${names.join(', ')}.</li>`:''}).join('');
 const source=previous.find(x=>x.id===e.previous_draw_id);
 return `<h3 class="card-title">Matching exclusions</h3><p class="dim tiny">Choose who each person must not give to. You can tick several people. Rules are directional; self-pairings are always excluded.</p>
 <div id="exclusion-preview">${exclusionSummary(e)}</div>
 <form id="exclusion-form"><fieldset class="history-rule"><legend>Avoid repeat gifts</legend><label class="check-option"><input type="checkbox" name="use_history" ${source?'checked':''} ${previous.length?'':'disabled'}> Exclude all pairings from a previous exchange</label>${previous.length?`<label class="field">Previous exchange<select name="previous_draw_id">${previous.map(x=>`<option value="${x.id}" ${x.id===e.previous_draw_id?'selected':''}>${esc(x.name)}${x.date?' · '+esc(x.date):''}</option>`).join('')}</select></label><p class="dim tiny">Only pairings between people in this draw apply. Unticking this keeps your manual exclusions.</p>`:'<p class="dim tiny">No completed earlier exchange is available in this group yet. Once last year’s draw is recorded here, you can exclude its pairings with this checkbox.</p>'}</fieldset>
 <p class="dim tiny">Open a person below and tick everyone they cannot give to.</p>
 ${e.participants.map(g=>`<details class="exclusion-person"><summary>${esc(g.name)} <span class="dim tiny">${pairs.filter(x=>x.giver_id===g.id).length} saved exclusions</span></summary><fieldset><legend>${esc(g.name)} cannot give to:</legend><div class="exclusion-options">${e.participants.filter(r=>r.id!==g.id).map(r=>`<label class="check-option"><input type="checkbox" name="pair" value="${g.id}:${r.id}" ${pairs.some(x=>x.giver_id===g.id&&x.recipient_id===r.id)?'checked':''}>${esc(r.name)}</label>`).join('')}</div></fieldset></details>`).join('')}
 <p id="exclusion-status" role="status" class="dim tiny">Changes take effect when you save.</p><button class="btn" type="submit">Save exclusions</button></form>`;
}
async function familyScreen(){
 let e=appState.exchange;
 if(!appState.families.length)return h('My group','Your circle')+card(empty('♧','Bring your people together','Start by creating your private group space. Then invite everyone by email.',btn('Create a group','new-family','primary')));
 let f=appState.families.find(f=>f.id===appState.fid)||appState.families[0];
 if(e?.family_id!==f.id)e=null;
 const detail=await api(`/families/${f.id}`);
 const admin=detail.owner_id===appState.me.id;
 const participants=e?.family_id===f.id?e.participants:[];
 appState.groupDetail=detail;
 const wishSections=e?await Promise.all([wishesScreen(appState.me.id,true),e.my_assignment?wishesScreen(e.my_assignment.recipient_id,true):Promise.resolve('<p class="compact-empty">Your recipient’s gift ideas will appear here once names are drawn.</p>')]):[];
 const wishPanels=e?card(wishSections[0],'own-compact-wishlist'):'';
 const groupActions=btn('← All groups','groups','outline')+(admin?btn('＋ &nbsp; New exchange','new-exchange','primary'):'')+btn('＋ &nbsp; New group','new-family','outline');
 return (e?`<header class="page-head exchange-page-title"><div><div class="eyebrow">Your exchange</div><div class="exchange-title-line"><h1>${esc(e.name)}</h1>${btn(mailIcon+' Messages',`exchange-page:${e.id}:messages`,'primary exchange-message-button')}</div></div><div class="header-actions">${groupActions}</div></header>`:h(f.name,'Your group',groupActions))+
 (e?card(`<div class="flex between wrap"><span class="eyebrow">${esc(f.name)}</span><span class="pill">${e.drawn?'Names drawn':'Preparing'}</span></div>${recipientSpotlight(e)}<p class="dim">${e.exchange_date?'Gift day: '+esc(e.exchange_date)+' · ':''}${money(e.budget)} gift budget</p>${wishSections[1]}`,'recipient-card exchange-focus compact-exchange-focus'):'')+wishPanels+
 `<div class="two-col"><div class="stack">${card(`<div class="flex between"><div><div class="eyebrow">Group</div><h2 class="card-title" style="font-size:23px">${esc(f.name)}</h2></div><span class="pill">${admin?'Admin':'Member'}</span></div><details class="exchange-members"><summary>View group members (${detail.members.length})</summary><h3 class="card-title">Members (${detail.members.length})</h3>${detail.members.map(m=>`<div class="list-row"><div class="flex"><div class="avatar">${esc(m.name.slice(0,1).toUpperCase())}</div><strong style="font-size:13px">${esc(m.name)}</strong></div>${m.id===f.owner_id?'<span class="pill">Admin</span>':admin?btn('Remove','remove-member:'+m.id,'outline small'):''}</div>`).join('')}${admin?`<div style="margin-top:19px">${btn('＋ Invite group member','invite','primary')}</div>${detail.pending.length?`<div class="separation"></div><h3 class="card-title">Invitations pending</h3>${detail.pending.map(p=>`<div class="list-row"><span class="tiny dim">${esc(p.email)}</span><span class="pill gold">Pending</span></div>`).join('')}`:''}`:''}</details>`)}
 ${e?card(`<div class="flex between wrap"><span class="pill">${e.reservation_mode==='show'?'Show reservations':'Surprise mode'}</span>${admin?btn('Change reservation mode','reservation-mode','outline small'):''}</div><div class="separation"></div><div class="flex between"><h2 class="card-title">${esc(e.name)} · Draw settings</h2><span class="pill ${e.drawn?'':'gold'}">${e.drawn?'Names drawn':'Not drawn'}</span></div><p class="dim tiny">${e.participants.length} participants · ${money(e.budget)} budget ${e.exchange_date?'· '+esc(e.exchange_date):''}</p>${admin&&!e.drawn?`<div class="separation"></div>${exclusionSummary(e)}<div class="flex wrap" style="margin-top:20px">${btn('Edit exclusions','exclusions','outline')}${btn('Draw names','draw','primary')}</div>`:`<div class="info-banner">${e.drawn?'♙ The names are sealed and private. You cannot reveal everyone’s assignments or reset a draw that has begun.':'Your organiser will draw names once everyone has joined.'}</div>`}`):''}
 </div><div class="stack">${admin&&e?card(`<h2 class="card-title">Delete exchange</h2><p class="dim tiny">Remove ${esc(e.name)} and its gift ideas, draw and messages for everyone. Keep the group and its other exchanges.</p>${btn('Delete exchange','delete-exchange','danger')}`):''}${admin?card(`<h2 class="card-title">Delete group</h2><p class="dim tiny">Permanently remove this group, its exchanges, wish lists and messages for everyone.</p>${btn('Delete group','delete-group','danger')}`):''}</div></div>`;
}
async function alertsScreen(){const n=await api('/notifications');return h('Notifications','Your latest updates')+(n.length?card(n.map(x=>`<div class="list-row"><div><strong style="font-size:13px">${esc(x.title)}</strong><div class="dim tiny" style="margin-top:3px">${esc(x.detail)}</div><div class="dim tiny">${new Date(x.created_at).toLocaleDateString()}</div></div>${x.read?'<span class="pill gray">Read</span>':`<button class="btn secondary small" data-read="${x.id}">Mark read</button>`}</div>`).join('')):card(empty('♢','All caught up!','When something happens in your gift exchange, it appears here.')))}
function settingsScreen(){return h('Your settings','The personal touches')+card(`<div class="profile-box"><h2 class="card-title">Your profile</h2><form id="profile-form"><div class="field"><label>Display name</label><input name="name" required maxlength="100" value="${esc(appState.me.name)}"></div><div class="field"><label>Email address</label><input disabled value="${esc(appState.me.email)}"></div><label class="flex tiny"><input type="checkbox" name="notify_email" ${appState.me.notify_email?'checked':''}> Send email notifications for invitations, private messages and announcements.</label><div style="margin-top:25px" class="flex wrap"><button class="btn" type="submit">Save settings</button>${btn('Sign out','logout','outline')}</div></form><div class="separation"></div><p class="dim tiny">GiftCircle is self-hosted, free and open source. Only organisers control their group space. Your conversations remain private.</p></div>`);
}
let renderVersion=0,lastRenderedRoute=null;
async function render(){
 const version=++renderVersion;
 if(!appState.me){renderAuth();return}
 let content='';
 try{if(appState.page==='home')content=homeScreen();else if(appState.page==='past-exchanges')content=pastExchangesScreen();else if(appState.page==='wishes')content=await wishesScreen();else if(appState.page==='messages')content=await messagesScreen();else if(appState.page==='groups')content=h('Your groups','Your circle',btn('＋ Create group','new-family','primary'))+groupsOverview();else if(appState.page==='family')content=await familyScreen();else if(appState.page==='exclusions')content=exclusionsScreen();else if(appState.page==='alerts')content=await alertsScreen();else if(appState.page==='settings')content=settingsScreen();else content=homeScreen()}
 catch(err){content=card(empty('!','Something went wrong',err.message,btn('Try again','refresh','primary')))}
 if(version!==renderVersion)return;
 const route=appState.page==='messages'&&appState.eid?'messages/'+appState.eid+'/'+appState.chat:appState.page==='family'?(appState.exchange?.family_id===appState.fid?'exchanges/'+appState.eid:'groups/'+appState.fid):appState.page;
 if(location.hash!=='#'+route)history.pushState({},'','#'+route);
 $('#app').innerHTML=shell(content);paintUnread();
 if(lastRenderedRoute!==route){window.scrollTo(0,0);lastRenderedRoute=route}
 const select=$('#exchange-select');if(select)select.onchange=async e=>{appState.eid=Number(e.target.value);appState.wishTarget=null;await sync(true)};
 const exclusions=$('#exclusion-form');if(exclusions){
 exclusions.onchange=()=>{const d=new FormData(exclusions);const preview={...appState.exchange,exclusions:d.getAll('pair').map(v=>{const [giver_id,recipient_id]=v.split(':').map(Number);return {giver_id,recipient_id}}),previous_draw_id:d.has('use_history')?Number(d.get('previous_draw_id')):null};$('#exclusion-preview').innerHTML=exclusionSummary(preview,true);$('#exclusion-status').textContent='Unsaved changes — save before leaving this page.'};
 exclusions.onsubmit=async ev=>{ev.preventDefault();const b=exclusions.querySelector('button[type="submit"]');b.disabled=true;try{const d=new FormData(exclusions);await send(`/exchanges/${appState.eid}/exclusions`,{pairs:d.getAll('pair').map(v=>{const [giver_id,recipient_id]=v.split(':').map(Number);return {giver_id,recipient_id}}),previous_draw_id:d.has('use_history')?Number(d.get('previous_draw_id')):null},'PUT');toast('Exclusions saved');await sync(true)}catch(err){$('#exclusion-status').textContent=err.message;b.disabled=false}};
 }
 const body=$('#chat-body');if(body){body.scrollTop=body.querySelector('.chat-entry')?body.scrollHeight:0;acknowledgeMessages(body)}
 const msg=$('#message-form');if(msg)msg.onsubmit=async ev=>{ev.preventDefault();const value=msg.querySelector('textarea[name="message"]').value.trim();if(!value)return;const b=msg.querySelector('button');b.disabled=true;try{const e=appState.exchange;if(appState.chat==='group')await send(`/exchanges/${e.id}/group-messages`,{content:value});else await send(`/exchanges/${e.id}/messages/${appState.chat==='giver'?e.my_assignment.assignment_id:e.my_santa_conversation}`,{content:value});await render()}catch(err){toast(err.message,true);b.disabled=false}};
 const prof=$('#profile-form');if(prof)prof.onsubmit=async ev=>{ev.preventDefault();try{await send('/me',{name:prof.querySelector('[name="name"]').value,notify_email:prof.querySelector('[name="notify_email"]').checked},'PATCH');toast('Settings saved');await sync(true)}catch(err){toast(err.message,true)}};
}
async function act(name){
 if(name==='messages'){await openMessages();return}
 if(name==='edit-name'){editName();return}
 if(name.startsWith('exchange-page:')){const [,id,page]=name.split(':');if(page==='messages'){await openMessages(id);return}const e=appState.exchanges.find(e=>e.id===Number(id));if(!e)return;appState.eid=e.id;appState.fid=e.family_id;appState.wishTarget=null;appState.chat='giver';appState.page=page;if(page==='family')history.replaceState({},'','#exchanges/'+e.id);await sync(true);return}

 if(name==='reservation-mode'){
  const e=appState.exchange;
  popup('Reservation visibility',e.family_name+' · '+e.name,`<div class="field"><label>Mode for this exchange</label><select name="mode"><option value="show" ${e.reservation_mode==='show'?'selected':''}>Show reservations</option><option value="surprise" ${e.reservation_mode==='surprise'?'selected':''}>Surprise mode</option></select></div><p>Show reservations lets recipients see reserved items and receive reservation updates. Surprise mode hides reservations. Changing back to Surprise cannot undo information already seen.</p>`,'Save mode',async d=>{await send(`/exchanges/${e.id}/reservation-settings`,{mode:d.get('mode')},'PUT');toast('Exchange mode saved');});return;
 }

 if(name==='finalise-list'||name==='draft-list'){await send(`/exchanges/${appState.eid}/wish-list/${name==='finalise-list'?'finalise':'draft'}`,{});toast(name==='finalise-list'?'Wish list finalised':'Wish list marked as Draft');await sync(true);return}

 if(name==='delete-exchange'){
  const e=appState.exchange;if(!e?.owner)return;
  popup('Delete '+e.name+'?','This permanently removes this exchange, its draw, gift ideas and messages for everyone. The group and other exchanges remain. Historical exclusions based on this draw will be cleared.',`<div class="field"><label>Type the exchange name to confirm</label><input name="confirm" required autocomplete="off"></div>`,'Delete exchange permanently',async d=>{if(d.get('confirm')!==e.name)throw new Error('Enter the exact exchange name to confirm.');await api('/exchanges/'+e.id,{method:'DELETE'});appState.eid=null;appState.exchange=null;appState.page='home';toast('Exchange deleted')});$('#modal-submit').classList.add('danger');return;
 }
 if(name==='delete-group'){
  const f=appState.groupDetail;
  popup('Delete '+f.name+'?','This permanently deletes the group and all its exchanges, wishes and messages for everyone. It does not delete anyone’s account.',`<div class="field"><label>Type the group name to confirm</label><input name="confirm" required autocomplete="off"></div>`,'Delete group permanently',async d=>{if(d.get('confirm')!==f.name)throw new Error('Enter the exact group name to confirm.');await api('/families/'+f.id,{method:'DELETE'});appState.fid=null;appState.page='groups';toast('Group deleted');});$('#modal-submit').classList.add('danger');return;
 }
 if(name.startsWith('remove-member:')){
  const f=appState.groupDetail;const uid=Number(name.split(':')[1]);const member=f.members.find(m=>m.id===uid);
  popup('Remove '+member.name+'?',`Remove this person from ${f.name}? Their participation and gift ideas in undrawn exchanges will be removed. Completed draws are protected.`,'','Remove member',async()=>{await api(`/families/${f.id}/members/${uid}`,{method:'DELETE'});toast('Member removed');});return;
 }

 if(name.startsWith('accept-invite:')){const result=await send('/invites/'+Number(name.split(':')[1])+'/accept',{});appState.fid=result.family_id;appState.eid=null;history.replaceState({},'','#groups/'+result.family_id);appState.page='family';toast('You joined the group!');await sync(true);return}
 if(name==='refresh'){await sync(true);return}
 if(['home','past-exchanges','groups','wishes','messages','family','alerts','settings','exclusions'].includes(name)){appState.page=name;if(name==='wishes')appState.wishTarget=null;await render();return}
 if(name==='recipient-wishes'){appState.wishTarget=appState.exchange?.my_assignment?.recipient_id;appState.page='wishes';await render();return}
 if(name==='own-wishes'){appState.wishTarget=appState.me.id;appState.page='wishes';await render();return}
 if(name==='chat-giver'){appState.page='messages';appState.chat='giver';await render();return}
 if(name==='logout'){await send('/auth/logout',{});unreadRequest++;appState.unread={total:0,exchanges:{}};appState.me=null;appState.eid=null;renderAuth();return}
 if(name==='new-family'){
  popup('Create your group','A private space for friends, colleagues or loved ones.',`<div class="field"><label>Group name</label><input name="name" maxlength="120" required placeholder="e.g. The Office Team"></div>`,'Create group',async d=>{const f=await send('/families',{name:d.get('name')});history.replaceState({},'','#groups/'+f.id);appState.page='family';toast('Group created!');appState.fid=f.id});return;
 }
 if(name==='new-exchange'){
  if(!appState.families.length){toast('Create a group first',true);return}
  const opts=appState.families.filter(f=>f.owner_id===appState.me.id).map(f=>`<option value="${f.id}" ${f.id===appState.fid?'selected':''}>${esc(f.name)}</option>`).join('');
  popup('Create gift exchange','Choose the group and set the occasion.',`<div class="field"><label>Group</label><select name="family">${opts}</select></div><div class="field"><label>Exchange name</label><input name="name" required maxlength="120" placeholder="Christmas 2026" value="Christmas 2026"></div><section class="welcome-message-panel"><label for="invitation-message">✉ Welcome message</label><p>Make the invitation yours. This message is included for people invited later, too.</p><textarea id="invitation-message" name="invitation_message" rows="6" maxlength="3000" placeholder="Tell everyone what you’re celebrating, how it works, and anything they should know…"></textarea><span class="dim tiny">Optional · up to 3,000 characters</span></section><div class="field"><label>Gift budget (AUD)</label><input name="budget" type="number" min="0" max="100000" value="50"></div><div class="field"><label>Gift exchange date</label><input name="date" type="date" value="2026-12-25"></div>`,'Create exchange',async d=>{const e=await send(`/families/${d.get('family')}/exchanges`,{name:d.get('name'),budget:Number(d.get('budget')),exchange_date:d.get('date'),invitation_message:d.get('invitation_message')});appState.eid=e.id;appState.fid=Number(d.get('family'));history.replaceState({},'','#exchanges/'+e.id);appState.page='family';toast('Exchange created!')});return;
 }
 if(name==='invite'){
  const e=appState.exchange;const f=appState.fid||e?.family_id||appState.families[0]?.id;if(!f)return;
  const available=appState.exchanges.filter(x=>x.family_id===f&&!x.drawn);
  const selected=available.find(x=>x.id===appState.eid)?.id||available[0]?.id||'';
  popup('Invite someone','An invitation link is sent privately to their email.',`<div class="field"><label>Their email address</label><input name="email" type="email" required placeholder="colleague@example.com"></div><div class="field"><label for="invite-exchange">Invitation for</label><select id="invite-exchange" name="exchange_id"><option value="">Group invitation only</option>${available.map(x=>`<option value="${x.id}" ${x.id===selected?'selected':''}>${esc(x.name)}</option>`).join('')}</select></div><div class="field"><label>Message preview</label><p id="invite-message-preview" class="invitation-preview"></p></div>`,'Send invitation',async d=>{await send(`/families/${f}/invites`,{email:d.get('email'),exchange_id:d.get('exchange_id')?Number(d.get('exchange_id')):null});toast('Invitation sent!')});
  const preview=()=>{const selected=Number($('#invite-exchange').value);const welcomes=available.filter(x=>x.invitation_message).sort((a,b)=>(b.id===selected)-(a.id===selected));$('#invite-message-preview').textContent=welcomes.map(x=>x.name+'\n'+x.invitation_message).join('\n\n')||`${appState.me.name} invited you to join ${appState.families.find(x=>x.id===f)?.name||'the group'}.`};
  $('#invite-exchange').onchange=preview;preview();return;
 }
 if(name==='new-wish'){
  if(!appState.eid){toast('Create an exchange first',true);return}
  const wishExchange=appState.exchange;const returnPage=appState.page==='family'?'family':'wishes';
  popup('Add a gift idea',`For ${appState.me.name} · ${wishExchange.name} · ${wishExchange.family_name}`,`<div class="field"><label>What would you love?</label><input name="title" required maxlength="200" placeholder="An interesting book"></div><div class="field"><label>Notes (optional)</label><textarea name="details" maxlength="1500" placeholder="Favourite authors, colours, sizes…"></textarea></div><div class="field"><label>Link (optional)</label><input type="url" name="url" maxlength="1500" placeholder="https://..."></div><div class="field"><label>Estimated price (optional)</label><input name="price" maxlength="40" placeholder="Around $25"></div>`,'Add to my list',async d=>{await send(`/exchanges/${wishExchange.id}/wishes`,{title:d.get('title'),details:d.get('details'),url:d.get('url'),price:d.get('price')});appState.page=returnPage;appState.wishTarget=appState.me.id;toast('Gift idea added')});return;
 }
 if(name==='draw'){
  const e=appState.exchange;if(!e?.owner||e.drawn)return;
  popup('Ready to draw names?','Every participant gets one recipient. This action is final so that messages and surprise gifts remain protected.',`<div class="notice">Check that all ${e.participants.length} participants have joined and exclusions are correct. The assignments will remain secret, including from you.</div>`,'Draw names now',async()=>{await send(`/exchanges/${e.id}/draw`,{});appState.page='home';toast('Names drawn! Everyone has been notified.')});return;
 }
 if(name.startsWith('reserve:')||name.startsWith('purchase:')||name.startsWith('availability:')){
  const [type,id]=name.split(':');await send(`/exchanges/${appState.eid}/wishes/${id}/${type}`,{});toast(type==='reserve'?'Reservation updated':type==='availability'?'Gift availability updated':'Purchase status updated');await sync(true);return;
 }
}
document.addEventListener('keydown',ev=>{if((ev.key==='Enter'||ev.key===' ')&&ev.target.matches('.overview-exchange-card')){ev.preventDefault();ev.target.click()}});
document.addEventListener('click',async ev=>{
 const group=ev.target.closest('[data-group]');const page=ev.target.closest('[data-page]');const action=ev.target.closest('[data-action]');const exchange=ev.target.closest('[data-exchange]');const chat=ev.target.closest('[data-chat]');const del=ev.target.closest('[data-delete-wish]');const read=ev.target.closest('[data-read]');
 try{
  if(group){appState.fid=Number(group.dataset.group);appState.eid=appState.exchanges.find(x=>x.family_id===appState.fid)?.id||null;appState.page='family';history.replaceState({},'','#groups/'+appState.fid);await sync(true)}
  else if(page){if(page.dataset.page==='messages')await openMessages();else{appState.page=page.dataset.page;await render()}}
  else if(action)await act(action.dataset.action);
  else if(exchange){appState.eid=Number(exchange.dataset.exchange);appState.fid=appState.exchanges.find(e=>e.id===appState.eid)?.family_id;appState.page='family';appState.wishTarget=null;history.replaceState({},'','#exchanges/'+appState.eid);await sync(true)}
  else if(chat){appState.chat=chat.dataset.chat;await render()}
  else if(del){if(confirm('Remove this gift idea?')){await api(`/exchanges/${appState.eid}/wishes/${del.dataset.deleteWish}`,{method:'DELETE'});await sync(true)}}
  else if(read){await send(`/notifications/${read.dataset.read}/read`,{});await render()}
 }catch(err){toast(err.message,true)}
});
function readRoute(){
 const exchangeRoute=location.hash.match(/^#exchanges\/(\d+)$/);
 if(exchangeRoute){appState.eid=Number(exchangeRoute[1]);appState.page='family';return}
 const messageRoute=location.hash.match(/^#messages\/(\d+)(?:\/(giver|santa|group))?$/);
 if(messageRoute){appState.eid=Number(messageRoute[1]);appState.chat=messageRoute[2]||'giver';appState.page='messages';return}
 const match=location.hash.match(/^#groups\/(\d+)$/);
 if(match){appState.fid=Number(match[1]);appState.page='family'}
 else if(['home','past-exchanges','groups','wishes','messages','alerts','settings','family','exclusions'].includes(location.hash.slice(1)))appState.page=location.hash.slice(1);
}
window.addEventListener('popstate',async()=>{if(openRevealRoute())return;readRoute();if(appState.me)await sync(true)});
window.addEventListener('hashchange',()=>{openRevealRoute()});
function openRevealRoute(){const reveal=location.hash.match(/^#reveal=([A-Za-z0-9_-]+)$/);if(!reveal)return false;appState.page='reveal';renderReveal(reveal[1]);return true}
function renderReveal(token){
 $('#app').innerHTML=`<main class="reveal-page"><a class="logo" href="/">🎁 GiftCircle</a><section class="card reveal-card"><div class="eyebrow">The draw is ready</div><h1>A little surprise awaits</h1><p>Tap the covered card to reveal who you’re gifting to.</p><button type="button" id="reveal-recipient" class="reveal-veil"><span aria-hidden="true">🎁</span><strong>Tap to reveal my recipient</strong></button><div id="reveal-result" aria-live="polite"></div><p class="dim tiny">This private link reveals only your recipient. Keep it to yourself.</p><a href="/" class="btn outline">Open GiftCircle</a></section></main>`;
 $('#reveal-recipient').onclick=async()=>{
  const b=$('#reveal-recipient');b.disabled=true;b.textContent='Opening your surprise…';
  try{const result=await send('/reveal',{token});b.remove();$('#reveal-result').innerHTML=`<div class="revealed-name"><span class="muted-label">You’re gifting to</span><h2>${esc(result.recipient_name)}</h2><p>${esc(result.group_name)} · ${esc(result.exchange_name)}</p><p>${money(result.budget)} gift budget${result.exchange_date?' · '+esc(result.exchange_date):''}</p></div>`;history.replaceState({},'',location.pathname)}
  catch(err){$('#reveal-result').textContent=err.message;b.textContent='Try again';b.disabled=false}
 };
}
(async function init(){
 if(openRevealRoute())return;
 readRoute();
 const params=new URLSearchParams(location.search);
 const login=params.get('login');const invitation=params.get('invite');
 if(invitation)sessionStorage.setItem('giftcircle_pending_invite',invitation);
 if(login||invitation)history.replaceState({},'',location.pathname+location.hash);
 if(login){try{await send('/auth/consume',{token:login})}catch(err){renderAuth(err.message);return}}
 try{
  const u=await api('/me');appState.me=u;
  const token=sessionStorage.getItem('giftcircle_pending_invite');
  if(token){try{await send('/invites/accept',{token});toast('You joined the group!');sessionStorage.removeItem('giftcircle_pending_invite')}catch(err){toast(err.message,true)}}
  await sync(true)
 }catch{renderAuth(invitation?'Sign in with the email address your invitation was sent to.':'')}
})();
// Refresh membership without replacing an in-progress form or message draft.
let checkingAccess=false;
async function refreshAccess(){
 if(!appState.me||appState.page==='reveal'||refreshing||checkingAccess||modalOpen||document.visibilityState==='hidden')return;
 checkingAccess=true;
 try{
  const [families,exchanges]=await Promise.all([api('/families'),api('/exchanges'),refreshUnread()]);
  const removed=appState.families.some(f=>!families.some(x=>x.id===f.id))||appState.exchanges.some(e=>!exchanges.some(x=>x.id===e.id));
  if(removed){await sync(true);return}
  const draft=$('#message-form textarea');
  const chatBody=$('#chat-body');const readingEarlier=chatBody&&chatBody.scrollHeight-chatBody.scrollTop-chatBody.clientHeight>50;
  if(appState.page==='messages'&&!draft?.value.trim()&&!$('#message-form textarea:focus')&&!readingEarlier)await sync();
 }catch(err){if(err.message==='Please sign in'||err.message==='Session expired'){appState.me=null;renderAuth()}}
 finally{checkingAccess=false}
}
setInterval(refreshAccess,8000);
window.addEventListener('focus',refreshAccess);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshAccess()});

if ('serviceWorker' in navigator && location.protocol==='https:') navigator.serviceWorker.register('/assets/sw.js').catch(()=>{});

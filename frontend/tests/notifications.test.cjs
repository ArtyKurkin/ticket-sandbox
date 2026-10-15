const {test}=require('node:test');const assert=require('node:assert/strict');const React=require('../node_modules/react');const {renderToStaticMarkup:render}=require('../node_modules/react-dom/server');const {modules}=require('./helpers.cjs');
const load=modules({},'notifications'),api=load('api'),{NotificationController}=load('controller');
const tier=(code,rank)=>({code,rank,rarity:code});
const raw=(id=1)=>({event_id:id,action:'grant',public_id:'00000000-0000-4000-8000-000000000001',title:'Первый результат',secret:false,from_tier:null,to_tier:tier('bronze',1),recorded_at:'2026-10-14T12:00:00+00:00',art_key:'speed',read:false,read_at:null});
const event=(id=1)=>api.parseNotification(raw(id));
function client(events=[event()],overrides={}){
 const calls={feed:0,claim:[],ack:[]},read=new Set(),timers=new Map();let timerId=0;
 const fake={feed:async()=>{calls.feed++;return{items:events.filter(e=>!read.has(e.eventId)),unread:events.filter(e=>!read.has(e.eventId)).length}},claim:async(id,token)=>{calls.claim.push([id,token]);return read.has(id)?null:events.find(e=>e.eventId===id)},ack:async(id,token)=>{calls.ack.push([id,token]);read.add(id)},...overrides};
 const states=[];let navigated=0;
 const c=new NotificationController({api:fake,changed:s=>states.push(s),navigate:()=>navigated++,uuid:()=>`token-${calls.claim.length}`,delay:(fn,ms)=>{assert.equal(ms,50000);timers.set(++timerId,fn);return timerId},cancel:id=>timers.delete(id)});
 return{c,calls,states,timers,read,navigated:()=>navigated};
}
test('notification contract validates genuine event IDs and real jump; rejects revoke, HTML URLs, malformed data',()=>{
 const n=api.parseNotification({...raw(),action:'upgrade',from_tier:tier('bronze',1),to_tier:tier('platinum',4)});assert.equal(n.toTier.rarity,'platinum');assert.equal(api.asAchievement(n).highestTier.code,'platinum');
 for(const bad of [{...raw(),action:'revoke'},{...raw(),event_id:0},{...raw(),to_tier:{code:'bad',rank:1,rarity:'bad'}},{...raw(),recorded_at:'fake'},{...raw(),action:'upgrade',from_tier:tier('gold',3)}])assert.throws(()=>api.parseNotification(bad));
 assert.throws(()=>api.parseFeed({items:[raw(),raw()],unread_count:2}));assert.throws(()=>api.safeRoomUrl('//evil.invalid'));assert.throws(()=>api.eventUrl('https://evil.invalid/{event_id}',1));assert.equal(api.parseNotification({...raw(),art_key:'evil'}).artKey,'generic');
});
test('grant renders existing medallion; bronze to platinum renders exactly one real transition',()=>{
 const toast=modules({},'achievements')('TrophyUnlockToast').TrophyUnlockToast;
 const n=api.parseNotification({...raw(),action:'upgrade',from_tier:tier('bronze',1),to_tier:tier('platinum',4)});
 const html=render(React.createElement(toast,{achievement:api.asAchievement(n),notificationLabel:'Награда улучшена',description:'Бронза → Платина',autoDismiss:false,onDismiss(){},onOpen(){}}));
 assert.equal((html.match(/class="tp-unlock-toast"/g)||[]).length,1);assert.match(html,/data-palette="platinum"/);assert.match(html,/Бронза → Платина/);assert.doesNotMatch(html,/Серебро|Золото/);assert.match(html,/Награда улучшена/);
});
test('sequential polling deduplicates repeated GET and renews current lease without a second toast',async()=>{
 const {c,calls,timers}=client();await c.poll();assert.equal(c.state.current.eventId,1);await c.poll();assert.equal(c.state.current.eventId,1);assert.equal(calls.claim.length,2);assert.equal(calls.claim[0][1],calls.claim[1][1]);assert.equal(timers.size,1);c.stop();assert.equal(timers.size,0);
});
test('queue shows one event and limits initial portion to three; remaining require explicit next',async()=>{
 const {c,calls}=client([1,2,3,4,5].map(event));await c.poll();assert.equal(c.state.current.eventId,1);await c.dismiss();assert.equal(c.state.current.eventId,2);await c.dismiss();assert.equal(c.state.current.eventId,3);await c.dismiss();assert.equal(c.state.current,null);assert.equal(c.state.unread,2);assert.equal(calls.ack.length,3);c.next();await new Promise(r=>setImmediate(r));assert.equal(c.state.current.eventId,4);c.stop();
});
test('dismiss only marks read after server success and read event never reappears on refresh',async()=>{
 const {c,calls}=client();await c.poll();await c.dismiss();assert.equal(c.state.current,null);await c.poll();assert.equal(c.state.current,null);assert.equal(calls.ack.length,1);c.stop();
});
test('open Trophy Room acknowledges first and navigates only after confirmed read',async()=>{
 const {c,navigated}=client();await c.poll();await c.dismiss(true);assert.equal(navigated(),1);c.stop();
});
test('ack error retains unread event; retries same claim token; does not falsely navigate',async()=>{
 let fail=true;const {c,calls,navigated}=client(undefined,{ack:async(id,token)=>{calls.ack.push([id,token]);if(fail)throw new api.NotificationError(500,'Не подтверждено');}});
 await c.poll();await c.dismiss(true);assert.equal(c.state.current.eventId,1);assert.match(c.state.error,/Не подтверждено/);assert.equal(navigated(),0);fail=false;await c.dismiss(true);assert.equal(navigated(),1);assert.deepEqual(calls.ack[0],calls.ack[1]);c.stop();
});
test('network error is retryable; 401 and 403 stop automatic polls until explicit authorization retry',async()=>{
 for(const status of [0,401,403]){let fail=true;const {c,calls,timers}=client(undefined,{feed:async()=>{calls.feed++;if(fail)throw new api.NotificationError(status,'Ошибка');return{items:[event()],unread:1}}});await c.poll();assert.equal(c.state.current,null);assert(c.state.error);if(status){assert.equal(timers.size,0);await c.poll();assert.equal(calls.feed,1);}fail=false;c.next();await new Promise(r=>setImmediate(r));assert.equal(c.state.current.eventId,1);c.stop();}
});
test('background tab does not poll, return checks again; late response cannot revive stopped/hidden host',async()=>{
 let release;const {c,calls}=client(undefined,{feed:async()=>{calls.feed++;return new Promise(r=>release=r)}});const pending=c.poll();c.setActive(false);await c.poll();assert.equal(calls.feed,1);release({items:[event()],unread:1});await pending;assert.equal(c.state.current,null);c.stop();
});
test('multiple overlapping poll/dismiss requests are serialized on one page',async()=>{
 let release;const {c,calls}=client(undefined,{claim:async()=>new Promise(r=>release=r)});let p=c.poll();await new Promise(r=>setImmediate(r));await c.poll();await c.dismiss();assert.equal(calls.feed,1);release(event());await p;c.stop();
});
test('server claim conflicts skip event; revoked secret current disappears after renewal 404',async()=>{
 let claimed=false;const {c}=client(undefined,{claim:async()=>{if(claimed)throw new api.NotificationError(404,'hidden');claimed=true;return event()}});await c.poll();assert.equal(c.state.current.eventId,1);await c.poll();assert.equal(c.state.current,null);c.stop();
});
test('API uses same origin, CSRF, read success validation and server-safe endpoints',async t=>{
 let calls=[];t.mock.method(globalThis,'fetch',async(url,o)=>{calls.push([url,o]);if(url.endsWith('claim/'))return Response.json({read:false,notification:raw(),claim_token:'token',lease_seconds:90});if(url.endsWith('ack/'))return Response.json({event_id:1,read:true,read_at:raw().recorded_at});return Response.json({items:[raw()],unread_count:1});});
 const a=api.createApi({feedUrl:'/api/achievements/me/notifications/',claimUrl:'/api/achievements/me/notifications/{event_id}/claim/',ackUrl:'/api/achievements/me/notifications/{event_id}/ack/',csrfToken:'csrf'}),signal=new AbortController().signal;
 await a.feed(signal);await a.claim(1,'token',signal);await a.ack(1,'token',signal);assert.equal(calls[0][1].method,'GET');assert.equal(calls[1][1].credentials,'same-origin');assert.equal(calls[1][1].headers['X-CSRFToken'],'csrf');assert.deepEqual(JSON.parse(calls[2][1].body),{claim_token:'token'});
});
test('host singleton guard, shared integration, lifecycle and reduced motion exist without changing medal geometry',()=>{
 const fs=require('node:fs'),path=require('node:path');const source=fs.readFileSync(path.join(__dirname,'../src/notifications/main.tsx'),'utf8');assert.match(source,/dataset\.achievementNotifications === 'mounted'/);
 const css=fs.readFileSync(path.join(__dirname,'../src/notifications/styles.css'),'utf8');assert.match(css,/prefers-reduced-motion:reduce/);assert.match(css,/animation: none !important/);
 const host=fs.readFileSync(path.join(__dirname,'../src/notifications/NotificationHost.tsx'),'utf8');assert.match(host,/visibilitychange/);assert.match(host,/pagehide/);assert.match(host,/BroadcastChannel/);assert.match(host,/data-mode="demo"/);assert.match(host,/client\.stop\(\)/);
});
test('BroadcastChannel acknowledgement is only a hint; server unread state retains current toast',async()=>{
 const {c,calls}=client();await c.poll();c.externalAck(1);await new Promise(r=>setImmediate(r));assert.equal(c.state.current.eventId,1);assert.equal(calls.ack.length,0);c.stop();
});

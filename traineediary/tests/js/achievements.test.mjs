import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const source=fs.readFileSync(new URL('../../../static/js/diary-achievement-api.js',import.meta.url),'utf8');
const api=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const id='00000000-0000-4000-8000-000000000001';
function item(){return {public_id:id,title:'Скорость',description:'Описание',status:'locked',highest_tier:null,
 supported_tiers:['bronze','silver','gold','platinum'].map((code,i)=>({code,rank:i+1,rarity:code,criterion:code,automatic:true})),
 revision:0,applicable:true,secret:false,revealed:true,earned_at:null,last_upgraded_at:null,manual:false,data_quality:'not_evaluated',auto_grant_blocked:false};}
const url=`/api/achievements/users/42/${id}/grant/`;
test('staff catalogue validates UUID, nullable tier and metadata; no invented award',()=>{
 const a=api.parseItem(item());assert.equal(a.highest_tier,null);assert.equal(a.revision,0);
 assert.equal(api.parseCatalogue({items:[a],stats:{earned:0,applicable_total:1},pending_source_events:0}).items.length,1);
 for(const mutate of [a=>a.highest_tier={code:'bronze',rank:1,rarity:'bronze'},a=>a.revision=-1,a=>a.public_id='bad']){const a=item();mutate(a);assert.throws(()=>api.parseItem(a));}
 assert.throws(()=>api.parseCatalogue({items:[a,a],stats:{earned:0,applicable_total:1},pending_source_events:0}));
});
test('upgrades offer only higher existing tiers and keep one UUID',()=>{
 const a=item();a.status='earned';a.highest_tier={code:'bronze',rank:1,rarity:'bronze'};
 assert.deepEqual(api.higherTiers(a).map(t=>t.code),['silver','gold','platinum']);
 a.highest_tier={code:'platinum',rank:4,rarity:'platinum'};assert.equal(api.higherTiers(a).length,0);assert.equal(api.eligibleDefinitions([a]).length,0);
});
test('operation freezes original revision/reason/id for uncertain retry and suppresses parallel sends',async t=>{
 let release,calls=[];t.mock.method(globalThis,'fetch',async(u,options)=>{calls.push(JSON.parse(options.body));assert.equal(u,url);assert.equal(options.method,'POST');assert.equal(options.credentials,'same-origin');assert.equal(options.headers['X-CSRFToken'],'token');await new Promise(r=>release=r);return Response.json({action:'grant',event_id:1,revision:1});});
 const a=item(),op=new api.Operation('grant',a,'bronze',' Причина ','stable-id');const promise=op.send(url,'token');
 await assert.rejects(op.send(url,'token'),/уже отправляется/);a.revision=100;release();await promise;
 const repeat=op.send(url,'token');release();await repeat;
 assert.equal(calls.length,2);assert.deepEqual(calls[0],calls[1]);assert.equal(calls[1].expected_revision,0);assert.equal(calls[1].operation_id,'stable-id');assert.equal(calls[1].reason,'Причина');
});
test('manual platinum is one POST and empty reason or lower level cannot enter confirmation payload',async t=>{
 const calls=[];t.mock.method(globalThis,'fetch',async(_,o)=>{calls.push(JSON.parse(o.body));return Response.json({action:'grant',event_id:1,revision:1});});
 await new api.Operation('grant',item(),'platinum','Проверено','plat-id').send(url,'token');assert.equal(calls.length,1);assert.equal(calls[0].tier,'platinum');
 assert.throws(()=>new api.Operation('grant',item(),'fake','r','id'));assert.throws(()=>new api.Operation('grant',item(),'bronze',' ','id'));
 const a=item();a.highest_tier={code:'gold',rank:3,rarity:'gold'};assert.throws(()=>new api.Operation('grant',a,'silver','r','id'));
});
test('revoke has reason/operation/revision and no fabricated fallback tier',async t=>{
 let payload;t.mock.method(globalThis,'fetch',async(_,o)=>{payload=JSON.parse(o.body);return Response.json({action:'revoke',event_id:2,revision:2});});
 const a=item();a.status='earned';a.highest_tier=a.supported_tiers[3];a.revision=1;
 await new api.Operation('revoke',a,null,'Ошибка выдачи','revoke-id').send(url.replace('/grant/','/revoke/'),'csrf');
 assert.deepEqual(Object.keys(payload).sort(),['expected_revision','operation_id','reason']);assert.equal(a.highest_tier.rarity,'platinum');
});
test('401/403/404/409/server/network remain failures without automatic POST retry',async t=>{
 let calls=0;const mocked=t.mock.method(globalThis,'fetch',async()=>{calls++;return new Response('{}',{status:409});});
 const op=new api.Operation('grant',item(),'bronze','r','id');await assert.rejects(op.send(url,'csrf'),e=>e.status===409);assert.equal(calls,1);
 for(const status of [401,403,404,500]){mocked.mock.mockImplementation(async()=>new Response('{}',{status}));await assert.rejects(api.request(url),e=>e.status===status);}
 mocked.mock.mockImplementation(async()=>{throw Error('offline');});await assert.rejects(op.send(url,'csrf'),e=>e.status===0);assert.equal(op.body.operation_id,'id');
});
test('cursor history keeps server dates/authors and real bronze to platinum without intermediate events',()=>{
 const a=item();const base={id:1,action:'grant',from_tier:null,to_tier:'bronze',recorded_at:'2026-10-14T10:00:00+03:00',occurred_at:'2026-10-10T10:00:00+03:00',actor_name:'Наставник',actor_id:5,reason:'Проверено',manual:true};
 const d=api.parseDetail({achievement:a,history:[base,{...base,id:2,action:'upgrade',from_tier:'bronze',to_tier:'platinum'}],next_cursor:2});
 assert.equal(d.history.length,2);assert.equal(api.eventLabel(d.history[1]),'Бронза → Платина');assert.equal(d.history[0].actor_name,'Наставник');assert.equal(d.history[0].recorded_at,base.recorded_at);
 assert.equal(api.mergeEvents(d.history,[d.history[1]]).length,2);
});
test('same-origin route whitelist prevents arbitrary mutation targets',()=>{
 assert.equal(api.endpoint('/api/achievements/users/42/{public_id}/grant/',id),url);
 assert.throws(()=>api.endpoint('https://evil.example/{public_id}/',id));assert.throws(()=>api.endpoint('/api/achievements/users/42/{public_id}/grant/','../'));
});
test('friendly system history text preserves every manual reason verbatim',()=>{
 const text='Исходное доказательство изменено; необходим явный staff review/revoke.';
 assert.match(api.historyReason({action:'evidence_disputed',manual:false,reason:text}),/Данные, на основании которых выдана награда, изменились/);
 assert.equal(api.historyReason({action:'grant',manual:true,reason:text}),text);
 assert.equal(api.historyReason({action:'evidence_disputed',manual:true,reason:'<script>literal</script>'}),'<script>literal</script>');
 assert.equal(api.manualRegrantMessage,'После отзыва награду можно выдать повторно только вручную.');
});
test('detail description omits duplicate title and keeps substantive descriptions',()=>{
 assert.equal(api.detailDescription({title:'Ticket Sandbox',description:' Ticket Sandbox '}),null);
 assert.equal(api.detailDescription({title:'Sandbox',description:'Подтверждённый технический результат'}),'Подтверждённый технический результат');
});

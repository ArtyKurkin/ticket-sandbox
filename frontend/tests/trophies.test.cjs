const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const React=require('../node_modules/react');
const {renderToStaticMarkup:render}=require('../node_modules/react-dom/server');
const {modules}=require('./helpers.cjs');
const load=modules({},'achievements');
const api=load('api');
const types=load('types');
const fixture=name=>JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/trophies',name+'.json'),'utf8'));
const collection=()=>api.parseCollection(fixture('real'));
const speed=()=>collection().items.find(a=>a.category==='speed');
const profile={displayName:'Сотрудник',role:'Стажёр',canDemo:false,sandboxUrl:'/sandbox/',achievementsApiUrl:'/api/achievements/me/',loginUrl:'/login/'};
function page(state,staff=false){const {TrophyRoom}=modules({useTrophies:{useTrophies:()=>({state,retry:()=>{}})}},'achievements')('TrophyRoom');return render(React.createElement(TrophyRoom,{profile:{...profile,canDemo:staff}}));}
function card(a){return render(React.createElement(load('TrophyCard').TrophyCard,{achievement:a,glowing:false,onOpen:()=>{}}));}
function medallion(a){return render(React.createElement(load('TrophyMedallion').TrophyMedallion,{achievement:a}));}
function ready(c=collection()){return {status:'ready',data:c};}
function tick(){return new Promise(r=>setImmediate(r));}

test('actual Django catalogue maps one card per UUID with server stats and no fake progress',()=>{
  const c=collection();assert.equal(c.items.length,11);assert.equal(new Set(c.items.map(a=>a.id)).size,11);
  const html=page(ready(c));assert.equal((html.match(/data-achievement-id=/g)||[]).length,11);
  assert.equal((html.match(/<progress /g)||[]).length,0);assert.doesNotMatch(html,/ПРОГРЕСС КОМНАТЫ|Старт миссии|24\.10\.2024|tp-unlock-toast/);
  assert(html.includes(`<strong>${c.stats.earned}</strong>`));assert(c.items.every(a=>a.progress===null));
});
test('direct platinum and bronze to platinum keep one definition and real jump history',()=>{
  const detail=api.parseDetail(fixture('independent_speed-detail'));
  assert.equal(detail.achievement.highestTier.rarity,'platinum');
  assert.deepEqual(detail.history.map(e=>[e.action,e.from_tier,e.to_tier]),[['grant',null,'bronze'],['upgrade','bronze','platinum']]);
  assert.equal((card(detail.achievement).match(/data-achievement-id=/g)||[]).length,1);
  const direct={...detail,history:[{...detail.history[1],action:'grant',from_tier:null}]};
  const html=render(React.createElement(load('TrophyDetails').History,{events:direct.history}));
  assert.match(html,/Платина/);assert.doesNotMatch(html,/Серебро|Золото|Бронза/);
});
test('history uses recorded server dates, keeps genuine actions, deduplicates cursor pages',()=>{
  const d=api.parseDetail(fixture('independent_speed-detail'));
  const merged=api.mergeHistory(d.history,[d.history[1]]);assert.equal(merged.length,2);
  const html=render(React.createElement(load('TrophyDetails').History,{events:merged}));
  assert.match(html,/Бронза → Платина/);assert(html.includes(d.history[0].recorded_at));
  assert.doesNotMatch(html,/Повышение: Бронза → Серебро/);
});
test('uneared secret stays neutral even if malicious extra metadata is sent',()=>{
  const raw=fixture('clean_week-detail');Object.assign(raw.achievement,{title:'SECRET LEAK',description:'100%',category:'quality',art_key:'MasterArt',code:'clean_week',supported_tiers:[{code:'platinum'}]});
  const a=api.parseDetail(raw).achievement;assert.equal(a.title,'Секретное достижение');assert.equal(a.category,null);assert.equal(types.displayMetal(a),null);
  const html=card(a);assert.doesNotMatch(html,/SECRET LEAK|Платина|MasterArt|clean_week/);assert.match(html,/tp-secret/);assert.match(html,/data-palette="neutral"/);
  assert.equal(types.matchesFilters(a,'all','platinum'),false);assert.equal(types.matchesFilters(a,'all','all','quality'),false);
});
test('secret reveals after earned and returns to closed art after revoke',()=>{
  const raw=fixture('real').items.find(a=>a.category==='speed');
  raw.secret=true;raw.title='Раскрытая награда';const earned=api.parseAchievement(raw);assert.match(card(earned),/Раскрытая награда/);
  const locked=fixture('clean_week-detail').achievement;locked.status='revoked';locked.earned_at=raw.earned_at;
  const revoked=api.parseAchievement(locked);assert.equal(types.isHidden(revoked),true);assert.match(card(revoked),/Секретное достижение/);assert.doesNotMatch(card(revoked),/Раскрытая награда/);
});
test('not applicable, unknown context, revoked and disputed do not create an earned tier',()=>{
  const internal=api.parseCollection(fixture('internal'));const training=internal.items.find(a=>a.artKey==='training');
  assert.equal(training.applicable,false);assert.match(card(training),/Не требуется/);assert.equal(training.highestTier,null);
  const empty=api.parseCollection(fixture('empty'));assert.match(card(empty.items.find(a=>a.applicable===null)),/Применимость уточняется/);
  const revoked={...speed(),status:'revoked',highestTier:null};assert.match(card(revoked),/Отозвано/);
  const quality=collection().items.find(a=>a.category==='quality'&&!a.secret);assert.equal(quality.dataQuality,'disputed');assert.equal(quality.highestTier.rarity,'gold');assert.match(card(quality),/Результат требует проверки/);
});
test('filters use highest tier or public fixed rarity, and never change server totals',()=>{
  const c=collection();assert.equal(types.matchesFilters(speed(),'earned','platinum'),true);assert.equal(types.matchesFilters(speed(),'earned','bronze'),false);
  assert.equal(types.matchesFilters(speed(),'all','all','speed'),true);assert.equal(types.matchesFilters(speed(),'all','all','quality'),false);
  const changed={...c,stats:{...c.stats,earned:123,applicable_total:456,rarities:{bronze:10,silver:20,gold:30,platinum:40}}};
  const html=page(ready(changed));assert.match(html,/<strong>123<\/strong>/);assert.match(html,/456/);assert.match(html,/<strong>40<\/strong>/);
});
test('loading, empty, pending, HTTP and network errors render without fixture fallback',()=>{
  assert.match(page({status:'loading'}),/Загружаем достижения/);assert.doesNotMatch(page({status:'loading'}),/data-achievement-id=|tp-statistics|tp-unlock-toast/);
  assert.match(page(ready({items:[],stats:{earned:0,applicable_total:0,rarities:{bronze:0,silver:0,gold:0,platinum:0}},pendingEvents:0})),/Каталог достижений пока пуст/);
  assert.match(page(ready({...collection(),pendingEvents:2})),/ещё обрабатываются/);
  for(const kind of ['unauthorized','forbidden','server','network','not_found']){
    const html=page({status:'error',error:new api.TrophyError(kind,'Ошибка')});assert.match(html,/Повторить загрузку/);assert.doesNotMatch(html,/data-achievement-id=|tp-statistics/);
    if(kind==='unauthorized')assert.match(html,/href="\/login\/"/);
  }
});
test('staff demonstration is gated by server boolean, separate state, and sends no POST',async t=>{
  assert.doesNotMatch(page(ready()),/>Демонстрация</);assert.match(page(ready(),true),/>Демонстрация</);
  const fake=t.mock.method(global,'fetch',async()=>{throw Error('demo cannot fetch');});
  const demo=load('demonstration');const d=demo.demoCollection();assert.strictEqual(demo.demoUnlock(d.items,false),d.items);
  const after=demo.demoUnlock(d.items,true);assert.equal(after.find(a=>a.id==='demo-3').status,'earned');assert.equal(fake.mock.callCount(),0);
  assert(after.every(a=>a.id.startsWith('demo-')));assert(after.every(a=>a.earnedAt===null));assert.equal(collection().items.some(a=>a.id.startsWith('demo-')),false);
});
test('initial and repeated snapshots never generate ordinary toast',()=>{
  for(const c of [collection(),collection(),{...collection(),items:collection().items.map(a=>({...a,revision:a.revision+1}))}])assert.doesNotMatch(page(ready(c)),/tp-unlock-toast|ТРОФЕЙ РАЗБЛОКИРОВАН/);
});
test('all metals repaint rims, bevels and inner geometry, without changing SVG paths',()=>{
  const a=speed();const palette=load('palette');const svgs=[];
  for(const rarity of Object.keys(types.metalLabels)){
    const copy={...a,highestTier:{...a.highestTier,rarity}};const html=medallion(copy);
    assert.match(html,new RegExp(`data-palette="${rarity}"`));assert.match(html,/--tp-metal-rim-0:/);assert.match(html,/--tp-metal-core-0:/);assert.match(html,/fill="var\(--tp-metal-/);
    svgs.push(html.slice(html.indexOf('<svg'),html.indexOf('</svg>')+6));
  }
  assert.equal(new Set(svgs).size,1);assert.notDeepEqual(palette.paletteStyle('bronze'),palette.paletteStyle('platinum'));
  assert(medallion({...a,artKey:'<svg onload=alert(1)>'}).includes('<svg'));assert.doesNotMatch(medallion({...a,artKey:'__proto__'}),/onload|undefined/);
});
test('GET API authenticates same-origin and supports every failure and retry',async t=>{
  let calls=0;const fetch=t.mock.method(global,'fetch',async(url,options)=>{
    assert.equal(url,'/api/achievements/me/');assert.equal(options.method,'GET');assert.equal(options.credentials,'same-origin');assert.equal(options.cache,'no-store');assert(options.signal);
    calls++;return calls===1?new Response('{}',{status:500}):Response.json(fixture('real'));
  });
  await assert.rejects(api.loadCollection(profile.achievementsApiUrl,new AbortController().signal),e=>e.kind==='server');
  assert.equal((await api.loadCollection(profile.achievementsApiUrl,new AbortController().signal)).items.length,11);
  for(const [status,kind] of [[401,'unauthorized'],[403,'forbidden'],[404,'not_found'],[500,'server']]){
    fetch.mock.mockImplementation(async()=>new Response('{}',{status}));await assert.rejects(api.loadCollection(profile.achievementsApiUrl,new AbortController().signal),e=>e.kind===kind);
  }
  fetch.mock.mockImplementation(async()=>{throw new TypeError('offline');});await assert.rejects(api.loadCollection(profile.achievementsApiUrl,new AbortController().signal),e=>e.kind==='network');
  fetch.mock.mockImplementation(async()=>new Response('<html>'));await assert.rejects(api.loadCollection(profile.achievementsApiUrl,new AbortController().signal),e=>e.kind==='contract');
});
test('details follow server cursors safely and abort obsolete requests',async t=>{
  const raw=fixture('independent_speed-detail');const id=raw.achievement.public_id;
  t.mock.method(global,'fetch',async(url,opts)=>{assert.equal(url,`/api/achievements/me/${id}/?cursor=1`);assert.equal(opts.method,'GET');return Response.json(raw);});
  assert.equal((await api.loadDetail(profile.achievementsApiUrl,id,1,new AbortController().signal)).history.length,2);
  await assert.rejects(api.loadDetail(profile.achievementsApiUrl,'../staff/',null,new AbortController().signal),e=>e.kind==='contract');
  await assert.rejects(api.loadCollection('https://evil.example/api/achievements/me/',new AbortController().signal),e=>e.kind==='contract');
});
test('malformed catalogue, duplicate definitions and forged earned state fail closed',()=>{
  for(const mutate of [c=>c.items.push(c.items[0]),c=>c.items[0].status='passed',c=>c.items[0].highest_tier=null,c=>c.stats.earned=-1,c=>c.items[0].public_id='unsafe',c=>c.items[0].progress={percent:101,label:'fake'}]){
    const c=fixture('real');mutate(c);assert.throws(()=>api.parseCollection(c),e=>e.kind==='contract');
  }
});
test('hook loading/error/retry aborts earlier fetch and ignores obsolete success',async t=>{
  const resolvers=[];t.mock.method(global,'fetch',(_url,opts)=>new Promise(resolve=>resolvers.push({resolve,signal:opts.signal})));
  let values=[],slot=0,scheduled,cleanup,oldDeps;
  const fakeReact={...React,useState:init=>{const i=slot++;if(!(i in values))values[i]=typeof init==='function'?init():init;return [values[i],v=>values[i]=typeof v==='function'?v(values[i]):v];},useCallback:fn=>fn,useEffect:(fn,deps)=>{if(!oldDeps||deps.some((v,i)=>v!==oldDeps[i])){scheduled=fn;oldDeps=deps;}}};
  const hook=modules({react:fakeReact},'achievements')('useTrophies').useTrophies;
  function run(){slot=0;const result=hook(profile.achievementsApiUrl);if(scheduled){cleanup?.();cleanup=scheduled();scheduled=null;}return result;}
  assert.equal(run().state.status,'loading');resolvers[0].resolve(new Response('{}',{status:500}));await tick();assert.equal(run().state.status,'error');
  run().retry();assert.equal(run().state.status,'loading');assert.equal(resolvers[0].signal.aborted,true);
  run().retry();run();assert.equal(resolvers[1].signal.aborted,true);
  resolvers[1].resolve(Response.json(fixture('empty')));await tick();assert.equal(run().state.status,'loading');
  resolvers[2].resolve(Response.json(fixture('real')));await tick();assert.equal(run().state.status,'ready');assert.equal(run().state.data.stats.earned,fixture('real').stats.earned);cleanup();
});

const { test } = require('node:test');
const assert = require('node:assert/strict');
const { modules, fixture } = require('./helpers.cjs');
const load = modules();
const { parseRoadmap, loadRoadmap, safeActionUrl } = load('api');
const { mapStations, formatPercent, segmentLit, canLaunch, demoStages } = load('presentation');
const { stageStatus } = load('types');
const React = require('../node_modules/react');
const { renderToStaticMarkup: render } = require('../node_modules/react-dom/server');
const { RoadmapStation } = load('RoadmapStation');
const { StageDetails } = load('StageDetails');
const { RoadmapPath } = load('RoadmapPath');
const profile = {displayName:'Стажёр',role:'Стажёр',canDemo:false,actionExternalHosts:[],sandboxUrl:'/sandbox/',achievementsUrl:'/achievements/',roadmapApiUrl:'/api/roadmap/me/',loginUrl:'/login/'};
function renderPage(state, canDemo=false) {
  const page = modules({useRoadmap:{useRoadmap:() => ({state,retry:() => {}})}})('RoadmapPage');
  return render(React.createElement(page.RoadmapPage,{profile:{...profile,canDemo}}));
}
function card(data, id) {
  const stage=mapStations(data).find(s=>s.id===id);
  return render(React.createElement(StageDetails,{stage,status:stageStatus(stage,data.journey),surface:null,stationElements:new Map(),onClose:()=>{},journey:data.journey,demonstration:false,baseHeight:730,onReserveSpace:()=>{}}));
}
function station(data, id) {
  const stage=mapStations(data).find(s=>s.id===id);
  return render(React.createElement(RoadmapStation,{stage,status:stageStatus(stage,data.journey),selected:false,onSelect:()=>{},elementRef:()=>{}}));
}
function stage(data,id) { return data.stages.find(s=>s.id===id); }
function setState(data,id,state) { Object.assign(stage(data,id),{state,display_status:state}); }

test('actual backend examples validate and map by stable ID, independently of array order', () => {
  for (const name of ['new_hire','internal_transfer']) {
    const data=fixture(name); data.stages.reverse();
    const mapped=mapStations(parseRoadmap(data));
    assert.equal(mapped.length,8);
    assert.deepEqual(mapped.map(s=>s.order),[1,2,3,4,5,6,7,8]);
    assert.deepEqual(mapped.map(s=>s.position),[{x:156,y:189},{x:348,y:280},{x:600,y:154},{x:888,y:210},{x:1002,y:350},{x:816,y:490},{x:528,y:532},{x:216,y:546}]);
  }
});
test('reject malformed and unsupported contracts', () => {
  for (const mutate of [d=>d.schema_version=2,d=>d.stages.pop(),d=>d.stages[1]=d.stages[0],d=>d.overall.percent='33.3',d=>d.stages[0].state='passed',d=>d.stages[0].actions=[{label:'Run',url:'javascript:alert(1)'}],d=>d.journey.metrics=[{week_number:1,week_start_date:null,speed_tickets_per_hour:0,quality_percent:null}],d=>d.stages[2].actions=[{label:'Run',url:'/run/'}]]) {
    const data=fixture('new_hire');mutate(data);assert.throws(()=>parseRoadmap(data),error=>error.kind==='contract');
  }
});
test('API uses same-origin session cookies, checks HTTP status, and supports retry', async t => {
  let calls=0;
  t.mock.method(global,'fetch',async (url, options) => {
    assert.equal(url,'/api/roadmap/me/');assert.equal(options.credentials,'same-origin');assert.equal(options.cache,'no-store');assert(options.signal);
    calls++;return calls===1 ? new Response('{}',{status:503}) : Response.json(fixture('new_hire'));
  });
  await assert.rejects(loadRoadmap('/api/roadmap/me/',new AbortController().signal),error=>error.kind==='server');
  const data=await loadRoadmap('/api/roadmap/me/',new AbortController().signal);assert.equal(data.schema_version,1);assert.equal(calls,2);
});
test('authentication, access, missing journey, network and malformed JSON errors are distinct', async t => {
  const fetch=t.mock.method(global,'fetch');
  for (const [status,kind] of [[401,'unauthorized'],[403,'forbidden'],[404,'not_found']]) {
    fetch.mock.mockImplementation(async()=>new Response('{}',{status}));
    await assert.rejects(loadRoadmap(profile.roadmapApiUrl,new AbortController().signal),error=>error.kind===kind);
  }
  fetch.mock.mockImplementation(async()=>{throw new TypeError('offline');});
  await assert.rejects(loadRoadmap(profile.roadmapApiUrl,new AbortController().signal),error=>error.kind==='network');
  fetch.mock.mockImplementation(async()=>new Response('<html>'));
  await assert.rejects(loadRoadmap(profile.roadmapApiUrl,new AbortController().signal),error=>error.kind==='contract');
});
test('obsolete requests carry an abort signal and are not replaced with demo data', async t => {
  t.mock.method(global,'fetch',(_url,{signal})=>new Promise((_resolve,reject)=>signal.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError')),{once:true})));
  const controller=new AbortController();const promise=loadRoadmap(profile.roadmapApiUrl,controller.signal);controller.abort();
  await assert.rejects(promise,error=>error.name==='AbortError');
});
test('staff endpoint can be loaded without any public trainee selector', async t => {
  t.mock.method(global,'fetch',async(url)=>{assert.equal(url,'/api/roadmap/trainees/2/');return Response.json(fixture('internal_transfer'));});
  assert.equal((await loadRoadmap('/api/roadmap/trainees/2/',new AbortController().signal)).journey.id,2);
});
test('loading and error render no fictitious progress, awards or stations', () => {
  const loading=renderPage({status:'loading'});assert.match(loading,/Загружаем Roadmap/);assert.doesNotMatch(loading,/из 8 этапов|трофе[йяев]|rm-station /);
  const {RoadmapError}=load('api');
  const error=renderPage({status:'error',error:new RoadmapError('server','Roadmap временно недоступен.')});
  assert.match(error,/Повторить загрузку/);assert.doesNotMatch(error,/rm-station /);
  const auth=renderPage({status:'error',error:new RoadmapError('unauthorized','Войдите снова.')});assert.match(auth,/href="\/login\/"/);
});
test('external 2/6 and internal 1/4 display the server overall value without recomputation', () => {
  const external=fixture('new_hire');Object.assign(external.overall,{completed_count:2,percent:33.3});
  assert.match(renderPage({status:'success',data:external}),/2 из 6 этапов/);
  assert.match(renderPage({status:'success',data:external}),/33,3%/);
  const internal=fixture('internal_transfer');assert.match(renderPage({status:'success',data:internal}),/1 из 4 этапов/);assert.match(renderPage({status:'success',data:internal}),/25%/);
  assert.equal(formatPercent(33.3),'33,3');
});
test('coming soon and not required have distinct badges, no locks, checks or launch actions', () => {
  const data=fixture('internal_transfer');
  for (const id of ['escalation','ticket_analysis']) {
    assert.match(station(data,id),/COMING SOON/);assert.doesNotMatch(station(data,id),/rm-lock|rm-check/);
    assert.doesNotMatch(card(data,id),/rm-stage-action/);
  }
  for (const id of ['training','sandbox']) {
    assert.match(station(data,id),/Не требуется/);assert.doesNotMatch(station(data,id),/rm-lock|rm-check|COMING SOON/);
    assert.match(card(data,id),/не входит в программу/);assert.doesNotMatch(card(data,id),/rm-stage-action/);
  }
});
test('enabling a future module changes presentation through API flags only', () => {
  const data=fixture('new_hire');Object.assign(stage(data,'escalation'),{availability:'enabled',applicable:true,state:'available',display_status:'available',actions:[{code:'open_future',label:'Открыть',url:'/future-module/',enabled:true,kind:'learning',external:false}]});
  assert.equal(stageStatus(mapStations(data)[2],data.journey),'available');
  assert.match(card(parseRoadmap(data),'escalation'),/href="\/future-module\/"/);
});
test('Sandbox snapshot remains completed despite changed catalog and text revision notifications', () => {
  const data=fixture('new_hire');const sb=stage(data,'sandbox');setState(data,'sandbox','completed');
  sb.progress={completed:2,total:3,unit:'tasks',basis:'technical',scope:'current_catalog'};
  sb.completion={id:7,completed_at:'2026-10-14T06:00:00Z',task_ids:[1,2],total:2};
  sb.notifications=[{code:'text_revision_required',count:3,blocking:false}];
  const html=card(parseRoadmap(data),'sandbox');assert.match(html,/2\/3/);assert.match(html,/требуют доработки/);assert.match(html,/>3</);assert.match(html,/Техническая часть завершена/);
  assert.equal(stageStatus(mapStations(data)[1],data.journey),'completed');
});
test('no invented Sandbox URL; only server actions can launch, and locked stages cannot launch', () => {
  const data=fixture('new_hire');stage(data,'sandbox').actions=[];assert.doesNotMatch(card(data,'sandbox'),/href=/);
  const sb=stage(data,'sandbox');setState(data,'sandbox','available');sb.actions=[{code:'open_sandbox',label:'Sandbox',url:'/real-sandbox/',enabled:true,kind:'learning',external:false}];
  assert.match(card(data,'sandbox'),/href="\/real-sandbox\/"/);setState(data,'sandbox','locked');assert.doesNotMatch(card(data,'sandbox'),/href=/);
  assert.equal(canLaunch(sb,true),false);
  for(const url of ['javascript:alert(1)','//evil.test/','/\\evil.test','https://evil.test/'])assert.equal(safeActionUrl(url),false);
});
test('nonlinear completions and returns never light missing stages based on overall count', () => {
  const data=fixture('new_hire');setState(data,'training','available');setState(data,'with_review','completed');setState(data,'optional_review','in_progress');
  Object.assign(data.journey.current_stage,{slug:'optional-review'});
  const mapped=mapStations(data);assert.equal(segmentLit(mapped[0].data,mapped[1].data),false);assert.equal(segmentLit(mapped[4].data,mapped[5].data),true);
  assert.equal(stageStatus(mapped[0],data.journey),'available');assert.equal(stageStatus(mapped[5],data.journey),'current');
  const path=render(React.createElement(RoadmapPath,{stages:mapped}));assert.equal((path.match(/data-lit="true"/g)||[]).length,1);
  setState(data,'with_review','in_progress');setState(data,'optional_review','locked');data.journey.current_stage.slug='with-review';
  assert.equal(segmentLit(stage(data,'with_review'),stage(data,'optional_review')),false);
  assert.equal(stageStatus(mapStations(data)[4],data.journey),'current');
});
test('terminated probation renders a neutral final station, no check and no reward', () => {
  const data=fixture('internal_transfer');data.journey.state='terminated';stage(data,'probation').evidence={outcome:'terminated'};setState(data,'probation','locked');
  assert.match(station(data,'probation'),/rm-neutral-final/);assert.match(station(data,'probation'),/ИС прекращён/);assert.doesNotMatch(station(data,'probation'),/rm-check/);
  assert.match(renderPage({status:'success',data}),/Испытательный срок прекращён/);assert.doesNotMatch(renderPage({status:'success',data}),/трофе[йяев]/);
});
test('metrics preserve unknown values rather than replacing them with zero; readiness comes from API', () => {
  const data=fixture('internal_transfer');data.journey.metrics=[{week_number:1,week_start_date:null,speed_tickets_per_hour:null,quality_percent:null}];
  assert.doesNotMatch(card(data,'optional_review'),/0 тикетов\/час|Качество ·/);
  data.journey.metrics.push({week_number:2,week_start_date:null,speed_tickets_per_hour:'3.2',quality_percent:95});
  const html=card(parseRoadmap(data),'optional_review');assert.match(html,/3.2 тикетов\/час/);assert.match(html,/95%/);assert.match(html,/До минимального срока/);
});
test('no adaptation keeps all eight visible with no invented personal progress', () => {
  const data=fixture('new_hire');data.journey={id:null,state:'not_started',entry_type:null,scheme:null};data.overall={completed_count:0,applicable_count:0,exempt_count:0,percent:0,adaptation_progress_percent:null};
  for(const s of data.stages){s.applicable=false;s.state=null;if(s.availability==='enabled')s.display_status='locked';}
  const html=renderPage({status:'success',data:parseRoadmap(data)});assert.match(html,/Адаптация ещё не началась/);assert.equal((html.match(/data-stage=/g)||[]).length,8);assert.doesNotMatch(html,/0 из 0 этапов|трофе[йяев]/);
});
test('staff demo is explicit and isolated; local demo does not mutate API data or produce awards/actions', () => {
  const data=fixture('new_hire');const before=JSON.stringify(data);
  for(const n of [1,3,6,8]){const demo=demoStages(n);assert.equal(demo.filter(s=>s.data.state==='completed').length,n);assert(demo.every(s=>s.data.actions.length===0));}
  assert.equal(JSON.stringify(data),before);
  assert.doesNotMatch(renderPage({status:'success',data}),/Демо:/);assert.match(renderPage({status:'success',data},true),/Реальные данные/);
  assert.doesNotMatch(renderPage({status:'success',data},true),/трофе[йяев]/);
});

test('Sandbox diagnostics do not cast doubt on a saved completion', () => {
  const data=fixture('new_hire');setState(data,'sandbox','completed');
  stage(data,'sandbox').data_quality=[{code:'conflicting_check_run',attempt_id:1,user_id:1,task_id:1}];
  const html=card(parseRoadmap(data),'sandbox');
  assert.match(html,/Техническая часть завершена/);
  assert.match(html,/неоднозначные исторические записи/);
  assert.doesNotMatch(html,/Недостаточно данных для подтверждения завершения/);
});
test('missing historical probation outcome stays neutral without a success check', () => {
  const data=fixture('internal_transfer');data.journey.state='insufficient_data';stage(data,'probation').evidence={outcome:'insufficient_data'};setState(data,'probation','locked');
  assert.match(station(data,'probation'),/Результат отсутствует/);
  assert.doesNotMatch(station(data,'probation'),/rm-check/);
  assert.match(card(parseRoadmap(data),'probation'),/исторический результат отсутствует/);
});
test('hook cleanup aborts pending requests and ignores responses after unmount', async () => {
  const effects=[],updates=[];let resolve,requestSignal;
  const mockReact={useState:initial=>[initial,value=>updates.push(value)],useEffect:callback=>effects.push(callback)};
  const api={...load('api'),loadRoadmap:(_url,signal)=>{requestSignal=signal;return new Promise(done=>{resolve=done;});}};
  const {useRoadmap}=modules({react:mockReact,api})('useRoadmap');
  assert.equal(useRoadmap(profile.roadmapApiUrl,[]).state.status,'loading');
  const cleanup=effects[0]();updates.length=0;cleanup();assert.equal(requestSignal.aborted,true);
  resolve(fixture('new_hire'));await new Promise(done=>setImmediate(done));assert.equal(updates.length,0);
});

test('disabled training action displays server explanation but no fake button or link', () => {
  const data=fixture('new_hire');stage(data,'training').actions=[{code:'open_training',label:'Перейти к обучению',url:null,enabled:false,kind:'learning',external:true,reason:'Ссылка на программу Teachbase не настроена.'}];
  const html=card(parseRoadmap(data),'training');assert.match(html,/Teachbase не настроена/);assert.doesNotMatch(html,/rm-stage-action|href=/);
});
test('configured external training links require the Django supplied exact host policy', () => {
  const data=fixture('new_hire');stage(data,'training').actions=[{code:'open_training',label:'Перейти к обучению',url:'https://courses.example.org/program/42',enabled:true,kind:'learning',external:true}];
  assert.throws(()=>parseRoadmap(data),error=>error.kind==='contract');
  assert.equal(safeActionUrl('HTTPS://COURSES.EXAMPLE.ORG/program',true,['courses.example.org']),true);
  const parsed=parseRoadmap(data,['courses.example.org']);const html=card(parsed,'training');
  assert.match(html,/href="https:\/\/courses.example.org\/program\/42"/);assert.match(html,/rel="noopener noreferrer"/);
  for(const url of ['http://courses.example.org/','https://evil.example/','https://courses.example.org.evil.example/','https://user@courses.example.org/','https://courses.example.org:8443/','//courses.example.org/'])assert.equal(safeActionUrl(url,true,['courses.example.org']),false);
});
test('enabled Sandbox action remains visible after completion with revision counts', () => {
  const data=fixture('new_hire');setState(data,'sandbox','completed');stage(data,'sandbox').actions=[{code:'open_sandbox',label:'Перейти к заданиям',url:'/sandbox/',enabled:true,kind:'learning',external:false}];
  stage(data,'sandbox').notifications=[{code:'text_revision_required',count:3,blocking:false}];
  const html=card(parseRoadmap(data),'sandbox');assert.match(html,/href="\/sandbox\/"/);assert.match(html,/Перейти к заданиям/);assert.match(html,/требуют доработки/);
});
test('server disabled actions never render as buttons even when the station is available', () => {
  const data=fixture('new_hire');setState(data,'sandbox','available');stage(data,'sandbox').actions=[{code:'open_sandbox',label:'Перейти к заданиям',url:'/sandbox/',enabled:false,kind:'learning',external:false,reason:'Этот этап пока заблокирован.'}];
  const html=card(parseRoadmap(data),'sandbox');assert.match(html,/пока заблокирован/);assert.doesNotMatch(html,/href="\/sandbox\/"/);
});
test('allowed staff result viewing works for terminated locked final station without enabling learning', () => {
  const data=fixture('internal_transfer');data.journey.state='terminated';setState(data,'probation','locked');stage(data,'probation').evidence={outcome:'terminated'};
  stage(data,'probation').actions=[{code:'view_probation_result',label:'Посмотреть результат ИС',url:'/diary/trainees/2/',enabled:true,kind:'view',external:false}];
  assert.match(card(parseRoadmap(data),'probation'),/Посмотреть результат ИС/);
  stage(data,'probation').actions[0].kind='learning';assert.doesNotMatch(card(data,'probation'),/href=/);
});
test('absence of a personal diary action shows its explanation without a staff-only link', () => {
  const data=fixture('internal_transfer');stage(data,'optional_review').action_notice='Персональная страница дневника для стажёра пока недоступна.';
  const html=card(parseRoadmap(data),'optional_review');assert.match(html,/Персональная страница дневника/);assert.doesNotMatch(html,/href=/);
});
test('reject action contracts with missing flags, duplicate codes, null enabled URL and unsafe URL substitutions', () => {
  const base={code:'open_training',label:'Перейти к обучению',url:'https://courses.example.org/program/42',enabled:true,kind:'learning',external:true};
  for(const mutate of [a=>delete a.enabled,a=>a.enabled='true',a=>a.url=null,a=>a.url='javascript:alert(1)',a=>a.url='https://evil.example/',a=>a.kind='complete']){
    const data=fixture('new_hire'),action={...base};mutate(action);stage(data,'training').actions=[action];assert.throws(()=>parseRoadmap(data,['courses.example.org']),error=>error.kind==='contract');
  }
  const data=fixture('new_hire');stage(data,'training').actions=[base,base];assert.throws(()=>parseRoadmap(data,['courses.example.org']),error=>error.kind==='contract');
});

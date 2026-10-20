import {createStationMap} from './station-map.js';
import {DISTRICTS,normalizeName} from './dashboard-model.js';
import {observeAnalysisRevision} from './research-tabs.js';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=(v,d=0)=>v==null?'—':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:d});
const labels={AVAILABLE:'사용가능',CHARGING:'충전중',STOPPED:'운영중지 · 복구 검토 대상',MAINTENANCE:'점검중',COMM_ERROR:'통신이상',UNKNOWN:'상태미확인'};
const district=s=>DISTRICTS.find(d=>String(s?.addr||'').includes(d))||'미확인';
const key=(s,c)=>`ME:${s.statId}:${c.chgerId}`;
const states=Object.fromEntries(['priorities','simulation'].map(t=>[t,{mode:t==='priorities'?'operational':'real',district:'',query:'',searchStation:null,station:null,charger:null,open:false,exact:false,radius:500,weight:'equal',replay:false,preview:false,selected:new Set(),after:false}]));
let generation=0,map=null,searchTimer=null,observationAt=null,forceLatest=false;
export function disposeRecovery(){generation++;clearTimeout(searchTimer);map?.destroy();map=null;}
export function stageRecoverySelection(ids,stamp,radius=500,replay=false){
 const s=states.simulation;s.mode='real';s.district='';s.query='';s.searchStation=null;s.station=null;s.charger=ids[0]||null;s.selected=new Set(ids);s.after=false;s.radius=radius;s.replay=replay;observationAt=stamp;
}
async function read(path,body){
 const r=await fetch(path,{cache:'no-store',...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});
 const d=await r.json();if(!r.ok){const e=new Error(typeof d.detail==='string'?d.detail:d.error_type||`HTTP ${r.status}`);e.status=r.status;throw e;}return d;
}
const buttons=(active,values,name)=>values.map(([id,label])=>`<button data-r-${name}="${id}" class="${String(active)===String(id)?'active':''}" aria-pressed="${String(active)===String(id)}">${label}</button>`).join('');
function graph(rows,title){
 let kw=0;const curve=rows.map((r,i)=>({n:i+1,kw:kw+=r.power_kw}));
 if(!curve.length)return '<p>누적 회복을 계산할 설비가 없습니다.</p>';
 const points=curve.map((p,i)=>`${40+i/Math.max(1,curve.length-1)*620},${180-p.kw/(kw||1)*150}`).join(' ');
 return `<h3>${title}</h3><svg class="research-cumulative" viewBox="0 0 720 230" role="img" aria-label="${title}"><path d="M40 20V180H680" fill="none" stroke="#ccd6dc"/><polyline points="40,180 ${points}" fill="none" stroke="#07988a" stroke-width="3"/><text x="45" y="20">${num(kw)} kW</text><text x="40" y="205">1</text><text x="650" y="205">${curve.length}</text><text x="270" y="225">복구 설비 수</text></svg>`;
}

export async function mountRecovery(host,tab,lib,onQuality,context={}){
 disposeRecovery();const run=generation,s=states[tab];host.onclick=null;host.onchange=null;host.oninput=null;host.onfocusin=null;host.onkeydown=null;
 const active=()=>run===generation&&host.isConnected;
 host.dataset.loadState='LOADING';host.innerHTML='<article class="panel empty-cell" role="status">데이터 불러오는 중</article>';
 let renderVersion=0;
 const remount=()=>mountRecovery(host,tab,lib,onQuality,context);
 try{
  let wanted=forceLatest?null:observationAt||context.observationAt;forceLatest=false;
  let pinChanged=false;
  const operationPath=stamp=>'/api/operations/recovery?'+new URLSearchParams({radius:s.radius,replay:s.replay,...(stamp?{observationAt:stamp}:{})});
  let op;
  try{op=await read(operationPath(wanted));}catch(e){if(e.status!==409)throw e;op=await read(operationPath(null));s.selected.clear();s.after=false;pinChanged=true;}
  if(!active())return;
  observationAt=op.observationAt;
  host.dispatchEvent(new CustomEvent('research-observation',{bubbles:true,detail:{observationAt}}));
  const potentialMode=tab==='priorities'&&s.mode==='potential';
  const hypothetical=tab==='simulation'&&s.mode==='hypothetical';
  const research=potentialMode||hypothetical?await read('/api/analysis/overview?'+new URLSearchParams({radius:s.radius,weight:s.weight,preview:s.preview,replay:s.replay})):null;
  if(!active())return;
  const stations=research?research.items:op.stations;
  const allRows=research?research.potential:op.items;
  const candidates=hypothetical?allRows.filter(r=>['AVAILABLE','CHARGING'].includes(r.status)):allRows;
  const byId=new Map(stations.map(x=>[x.statId,x]));
  const currentStamp=research?.last_success_at||op.observationAt;
  const stale=research?.stale??op.stale;
  const scopeStationIds=()=>stations.filter(x=>(!s.district||district(x)===s.district)&&x.lat!=null&&x.lng!=null).map(x=>x.statId);
  const inDistrict=r=>!s.district||district(byId.get(r.statId))===s.district;
  const eligible=r=>hypothetical||r.selectable;
  s.selected=new Set([...s.selected].filter(id=>candidates.some(r=>r.charger_id===id&&eligible(r))));
  if(s.charger&&!s.station)s.station=candidates.find(r=>r.charger_id===s.charger)?.statId||null;
  observeAnalysisRevision(()=>{if(active()&&!s.selected.size)void remount();},revision=>{if(active())host.dataset.analysisRevision=revision;});
  const fail=e=>{if(active()){host.dataset.loadState='ERROR';const error=host.querySelector('#research-error');if(error)error.textContent='조회 오류 · '+e.message;const sim=host.querySelector('#research-simulation');if(sim&&sim.textContent==='계산 중')sim.textContent='계산 요청 실패 · '+e.message;}};

  function shownRows(){return candidates.filter(r=>inDistrict(r)&&(!s.exact||!potentialMode||!r.scoreIsUpperBound)&&(!s.searchStation||r.statId===s.searchStation)&&(!s.query||normalizeName(r.name).includes(normalizeName(s.query))));}
  function searchCandidates(){
   const ids=new Set(candidates.filter(r=>inDistrict(r)&&(!s.query||normalizeName(r.name).includes(normalizeName(s.query)))).map(r=>r.statId));
   return stations.filter(x=>ids.has(x.statId)).sort((a,b)=>String(a.statNm).localeCompare(String(b.statNm),'ko')||a.statId.localeCompare(b.statId));
  }
  function autocomplete(){
   const list=host.querySelector('#recovery-options');if(!list)return;
   list.hidden=!s.open;host.querySelector('#research-search')?.setAttribute('aria-expanded',String(s.open));
   if(!s.open)return;
   list.innerHTML=searchCandidates().map(x=>`<button type="button" role="option" data-r-search="${esc(x.statId)}"><span>${esc(x.statNm)}</span><small>${esc(district(x))} · ${research?'대상 '+candidates.filter(r=>r.statId===x.statId).length+'기':'운영중지 '+x.stoppedChargerCount+'기'}</small></button>`).join('')||'<p>검색 조건에 해당하는 충전소가 없습니다.</p>';
  }

  async function render(){
   const version=++renderVersion;map?.destroy();map=null;
   const rows=shownRows();
   const visibleIds=new Set(rows.map(r=>r.statId));const mapStations=stations.filter(x=>visibleIds.has(x.statId));
   const cityCandidates=candidates.filter(inDistrict);
   const selectedRows=candidates.filter(r=>s.selected.has(r.charger_id));
   const controls=`<div class="research-controls research-filters"><label>자치구<select id="research-district"><option value="">서울시 전체</option>${DISTRICTS.map(d=>`<option ${s.district===d?'selected':''}>${d}</option>`).join('')}</select></label><label class="recovery-search-label">시설명 검색<div class="recovery-search"><input id="research-search" role="combobox" aria-label="복구 시설명 검색" aria-controls="recovery-options" aria-expanded="${s.open}" autocomplete="off" value="${esc(s.query)}" placeholder="충전소 이름 검색"><div id="recovery-options" role="listbox" hidden></div></div></label><div class="segmented">${buttons(s.radius,[[500,'500m'],[1000,'1km']],'radius')}</div>${research?`<label>가중치<select id="research-weight">${[['equal','동일가중'],['demand','수요강조'],['power','출력강조'],['alternative','대체망강조']].map(([id,label])=>`<option value="${id}" ${s.weight===id?'selected':''}>${label}</option>`).join('')}</select></label>`:''}<button data-r-refresh>최신 관측 새로고침</button></div>`;
   const heading=tab==='priorities'?`<div class="segmented">${buttons(s.mode,[['operational','운영 복구 우선순위'],['potential','잠재 고장 영향']],'ranking')}</div>${potentialMode?`<div class="segmented">${buttons(s.exact,[['false','전체'],['true','정확 점수만']],'exact')}</div>`:'<p>D1 이용수요를 포함하지 않은 운영 관점 복구 우선순위 · OperationalImpact = (Q + B) / 2</p>'}`:`<div class="segmented scenario-modes">${buttons(s.mode,[['real','서울 실제 운영중지 복구'],['hypothetical','핵심시설 가정 시나리오']],'mode')}</div><div class="research-warning"><strong>${hypothetical?'가정 시나리오 · 실제 운영중지가 아님':'명목 정격출력 기반 가상 복구 시뮬레이션'}</strong></div>`;
   host.innerHTML=`${heading}${stale?`<div class="research-observation">${s.replay?'저장 관측 재현 · 현재 상태가 아님':'최신 관측 확인 필요'} · ${esc(currentStamp)}${s.replay?'':'<button data-r-observed>저장 관측으로 분석 보기</button>'}</div>`:''}${pinChanged?'<p class="research-observation">관측이 갱신되어 이전 선택을 초기화했습니다.</p>':''}${controls}${research?`<label class="research-options"><input id="research-preview" type="checkbox" ${s.preview?'checked':''}> 검토용 Preview · 최종 연구결과가 아님</label>`:''}${s.preview&&research?'<div class="research-warning">검토용 미확정 분석 · 최종 연구결과가 아님</div>':''}<p id="research-error" role="alert"></p><p class="recovery-scope" id="recovery-observation">관측 ${esc(currentStamp)} · ${s.district||'서울시 전체'} · ${mapStations.length}개 시설 / ${rows.length}기${!research?' · 운영중지 '+num(op.diagnostics.knownStoppedOutputKw)+' kW':''}</p>${tab==='simulation'?`<div class="research-controls recovery-bulk"><span>운영 복구순위 일괄 선택</span>${[1,3,5,10].map(n=>`<button data-r-top="${n}" ${hypothetical?'disabled':''}>상위 ${n}기</button>`).join('')}<button data-r-clear>직접선택 / 초기화</button></div><p id="recovery-selection-prompt">${s.selected.size?'선택 '+s.selected.size+'기':'복구할 충전기를 선택하세요.'}</p><div class="segmented">${buttons(s.after,[['false','개선 전'],['true','개선 후']],'view')}</div><div id="research-simulation">계산 중</div><div class="recovery-selection-chips">${selectedRows.map(r=>`<button data-r-remove="${esc(r.charger_id)}">${esc(r.name)} · ${esc(r.chgerId)} · ${num(r.power_kw)} kW ×</button>`).join('')}</div>`:''}<div class="research-layout recovery-layout"><article class="panel research-map-panel"><div id="research-map"><div id="tile-notice" hidden>배경지도 연결 대기 · 실제 좌표는 표시됩니다.</div></div><div id="research-detail"><p>충전소나 순위 행을 선택하세요.</p></div></article><article class="panel research-rank-panel"><h2>${tab==='simulation'?'운영중지 충전기 선택':potentialMode?'잠재 고장 영향':'운영 복구 우선순위'}</h2><p id="research-result-count">${tab==='simulation'&&s.station?rows.filter(r=>r.statId===s.station).length:rows.length}기${tab==='simulation'?` · 전체 선택가능 ${cityCandidates.filter(eligible).length}기`:''}</p><div class="table-wrap" id="recovery-table"></div></article></div><article class="panel" id="research-curve"></article>${tab==='priorities'?'<p class="recovery-explanation">잠재 고장 영향은 설비가 향후 운영중지될 경우의 영향을 실제 이용수요·출력 비중·주변 대체망으로 평가한 사전 위험관리 지표입니다. 현재 고장 상태를 의미하지 않습니다.</p>':''}`;
   const tableItems=tab==='simulation'&&s.station?rows.filter(r=>r.statId===s.station):rows;
   const potentialColumns='<th>D</th><th>Q</th><th>B</th><th>Impact</th><th>평가구분</th>';
   const operationalColumns='<th>Q</th><th>B</th><th>운영 영향점수</th><th>D1 연결</th><th>D</th><th>수요반영 Impact</th>';
   host.querySelector('#recovery-table').innerHTML=`<table><thead><tr>${tab==='simulation'?'<th>선택</th>':''}<th>순위</th><th>충전소명</th><th>자치구</th><th>statId</th><th>chgerId</th><th>출력(kW)</th><th>현재상태</th>${potentialMode||hypothetical?potentialColumns:operationalColumns}${tab==='priorities'&&!potentialMode?'<th>시뮬레이션</th>':''}</tr></thead><tbody>${tableItems.map(r=>`<tr data-r-station="${esc(r.statId)}" data-r-charger="${esc(r.charger_id)}" class="${s.station===r.statId?'selected-row':''}" ${s.charger===r.charger_id?'data-focused="true"':''}>${tab==='simulation'?`<td><input type="checkbox" data-r-select="${esc(r.charger_id)}" aria-label="${esc(r.name)} ${esc(r.chgerId)} 복구 선택" ${s.selected.has(r.charger_id)?'checked':''} ${eligible(r)?'':'disabled'}></td>`:''}<td>${r.rank}</td><td>${esc(r.name)}</td><td>${esc(district(byId.get(r.statId)))}</td><td>${esc(r.statId)}</td><td>${esc(r.chgerId)}</td><td>${num(r.power_kw)}</td><td>${esc(labels[r.status])}</td>${potentialMode||hypothetical?['D','Q','B','score'].map(k=>`<td data-value="${k}">${num(r[k],3)}</td>`).join('')+`<td>${r.scoreIsUpperBound?'상한검토용':'정확'}</td>`:`<td data-value="Q">${num(r.Q,3)}</td><td data-value="B">${num(r.B,3)}</td><td data-value="operationalImpact">${num(r.operationalImpact,3)}</td><td>${r.d1Connected?'연결':'미연결'}</td><td>${num(r.D,3)}</td><td>${num(r.demandImpact,3)}</td>`}${tab==='priorities'&&!potentialMode?`<td><button data-r-simulate="${esc(r.charger_id)}" ${r.selectable?'':'disabled'}>시뮬레이션</button></td>`:''}</tr>`).join('')||`<tr><td colspan="15">${stale&&!s.replay?'최신 관측 확인이 필요합니다.':s.query||s.district?'현재 검색·자치구 조건에 해당하는 설비가 없습니다.':'현재 관측에 운영중지 복구 검토 대상이 없습니다.'}</td></tr>`}</tbody></table>`;
   host.querySelector('.research-rank-panel').dataset.loadState=tableItems.length?'READY':'EMPTY';
   host.dataset.loadState=stale&&!s.replay?'STALE':rows.length?'READY':'EMPTY';
   host.dataset.observationAt=currentStamp;host.dataset.recoveryMode=s.mode;host.dataset.recoveryCount=String(op.count);host.dataset.selectableCount=String(op.selectableCount);
   const mapRows=mapStations.map(x=>({id:x.statId,name:x.statNm,lat:x.lat==null?null:Number(x.lat),lon:x.lng==null?null:Number(x.lng),virtualRestoredCount:tab==='simulation'&&s.after?x.chargers.filter(c=>s.selected.has(key(x,c))).length:0,chargers:x.chargers.map(c=>({...c,display_status:tab==='simulation'&&s.selected.has(key(x,c))?(s.after?'RESTORED':hypothetical?'STOPPED':c.status):c.status}))}));
   map=createStationMap(host.querySelector('#research-map'),lib,sid=>{s.station=sid;s.charger=null;s.open=false;if(tab==='simulation')void render().catch(fail);else detail(sid);},{hostId:'research-leaflet-map',zoomAnimation:false,fadeAnimation:false,markerZoomAnimation:false});
   map.update(mapRows,s.station,s.radius);if(s.district)map.district(s.district);
   host.querySelector('#research-map').dataset.scenario=s.after?'after':'before';host.querySelector('#research-map').dataset.recoveredCount=String(s.after?s.selected.size:0);
   function detail(sid,charger){
    const x=byId.get(sid);if(!x)return;s.station=sid;s.charger=charger||s.charger;
    map.update(mapRows,sid,s.radius);map.flyTo(mapRows.find(x=>x.id===sid));
    const units=x.chargers.filter(c=>hypothetical?candidates.some(r=>r.charger_id===key(x,c)):potentialMode?allRows.some(r=>r.charger_id===key(x,c)):String(c.stat)==='4');
    host.querySelector('#research-detail').innerHTML=`<h3>${esc(x.statNm)}</h3><p>${esc(x.addr)} · statId ${esc(sid)} · ${research?'분석 대상':'운영중지'} ${units.length}기</p>${units.map(c=>{
     const id=key(x,c),r=candidates.find(r=>r.charger_id===id),selected=s.selected.has(id);
     return `<article class="recovery-unit ${selected?'selected-unit':''}" data-detail-unit="${esc(id)}"><b>chgerId ${esc(c.chgerId)} · ${num(c.output_kw)} kW</b><p>원본 stat=${esc(c.stat)} · ${esc(labels[c.status])}<br>statUpdDt ${esc(c.statUpdDt)}</p>${tab==='simulation'&&selected?`<strong class="scenario-unit-state" data-scenario-state="${s.after?'AVAILABLE':hypothetical?'STOPPED':c.status}">가상 상태: ${s.after?'사용가능':hypothetical?'운영중지':labels[c.status]}</strong>`:''}${r?`<p>Q ${num(r.Q,3)} · B ${num(r.B,3)}${r.P!=null?' · 시설 P '+num(r.P)+'kW · 주변 A '+num(r.A)+'kW':''}<br>D ${num(r.D,3)}${r.d1Connected?' · D1 실제 급속충전량 '+num(r.annualFastKwh2025)+'kWh':''}</p>`:''}${tab==='simulation'?`<button data-r-add="${esc(id)}" ${r&&eligible(r)?'':'disabled'}>${selected?'선택 해제':'시뮬레이션에 추가'}</button>`:''}</article>`;
    }).join('')}<p>운영중지는 물리적 고장 확정을 뜻하지 않습니다.${s.after?' 다른 운영중지 설비가 남은 충전소는 주황색을 유지하고 선택 복구 설비는 초록색 배지로 표시합니다.':''}</p>`;
    host.querySelectorAll('tr[data-r-station]').forEach(el=>el.classList.toggle('selected-row',el.dataset.rStation===sid));
    if(charger)host.querySelector(`tr[data-r-charger="${CSS.escape(charger)}"]`)?.scrollIntoView({block:'nearest'});
   }
   if(s.station)detail(s.station,s.charger);
   host.querySelectorAll('tr[data-r-station]').forEach(el=>el.onclick=e=>{if(e.target.closest('button,input'))return;detail(el.dataset.rStation,el.dataset.rCharger);});
   autocomplete();
   const curveRows=hypothetical?cityCandidates.filter(r=>s.selected.has(r.charger_id)):op.items.filter(r=>inDistrict(r)&&r.selectable);
   host.querySelector('#research-curve').innerHTML=potentialMode?'':graph(curveRows,hypothetical?'가정 시나리오 · 누적 회복 정격출력':'운영 복구순위에 따른 가상 누적 회복 정격출력');
   if(tab==='simulation'){
    if(stale&&!s.replay){host.querySelector('#research-simulation').textContent='최신 관측 확인 필요 · 저장 관측을 선택하면 같은 관측으로 전후 비교할 수 있습니다.';return;}
    const result=await read(hypothetical?'/api/analysis/simulate':'/api/operations/simulate',hypothetical?{chargerIds:[...s.selected],radius:s.radius,weight:s.weight,preview:s.preview,hypothetical:true,replay:s.replay}:{chargerIds:[...s.selected],stationIds:scopeStationIds(),replay:s.replay,observationAt:op.observationAt});
    if(!active()||version!==renderVersion)return;
    if(result.observationAt!==currentStamp)throw new Error('관측이 변경되었습니다. 최신 관측을 다시 선택하세요.');
    const shown=s.after?result.after:result.before;
    host.querySelector('#research-simulation').innerHTML=`<div class="simulation-metrics">${[['정상 가용 정격출력','normalKw','kW'],['운영중지 정격출력','stoppedKw','kW'],['운영중지 충전기 수','stoppedCount','기']].map(([label,k,u])=>`<div><small>${s.after?'개선 후':'개선 전'} · ${label}</small><strong data-sim="${k}">${num(shown[k])} ${u}</strong><small>${num(result.before[k])} → ${num(result.after[k])} ${u}</small></div>`).join('')}<div><small>선택 충전기 출력 / 회복 정격출력</small><strong data-sim="recoveredKw">${num(result.recoveredKw)} kW</strong></div><div><small>회복률 · 개선 전 정상출력 대비</small><strong data-sim="recoveryRate">${num(result.recoveryRate,2)}${result.recoveryRate==null?'':'%'}</strong></div></div><p>명목 정격출력 기반 가상 복구 시뮬레이션 · ${hypothetical?'핵심시설 전체':'현재 자치구의 운영중지 시설 전체'} 기준. 검색은 선택용이며 계산 범위를 줄이지 않습니다.</p>`;
   }
  }
  function choose(sid){s.station=sid;s.searchStation=sid;s.query=byId.get(sid)?.statNm||'';s.open=false;void render().catch(fail);}
  function select(id){if(!candidates.some(r=>r.charger_id===id&&eligible(r)))return;s.selected.has(id)?s.selected.delete(id):s.selected.add(id);s.after=false;void render().catch(fail);}
  host.onclick=e=>{
   if(e.target.id==='research-search'){s.open=true;autocomplete();return;}
   const b=e.target.closest('button');if(!b)return;
   if(b.dataset.rSearch){choose(b.dataset.rSearch);return;}
   if(b.hasAttribute('data-r-refresh')){observationAt=null;forceLatest=true;s.selected.clear();s.after=false;void remount();return;}
   if(b.hasAttribute('data-r-observed')){s.replay=true;void remount();return;}
   if(b.dataset.rRanking){s.mode=b.dataset.rRanking;s.query='';s.searchStation=null;s.station=null;s.open=false;void remount();return;}
   if(b.dataset.rMode){s.mode=b.dataset.rMode;s.district='';s.query='';s.searchStation=null;s.station=null;s.selected.clear();s.after=false;void remount();return;}
   if(b.dataset.rRadius){s.radius=Number(b.dataset.rRadius);void remount();return;}
   if(b.dataset.rExact){s.exact=b.dataset.rExact==='true';void render().catch(fail);return;}
   if(b.dataset.rView){s.after=b.dataset.rView==='true';void render().catch(fail);return;}
   if(b.dataset.rAdd){select(b.dataset.rAdd);return;}
   if(b.dataset.rRemove){select(b.dataset.rRemove);return;}
   if(b.dataset.rSimulate){stageRecoverySelection([b.dataset.rSimulate],op.observationAt,s.radius,s.replay);host.dispatchEvent(new CustomEvent('research-open-simulation',{bubbles:true}));return;}
   if(b.dataset.rTop){s.selected=new Set(op.items.filter(r=>r.selectable&&inDistrict(r)).slice(0,Number(b.dataset.rTop)).map(r=>r.charger_id));s.query='';s.searchStation=null;s.station=null;s.after=false;void render().catch(fail);return;}
   if(b.hasAttribute('data-r-clear')){s.selected.clear();s.after=false;void render().catch(fail);}
  };
  host.onchange=e=>{
   const t=e.target;
   if(t.id==='research-district'){s.district=t.value;s.query='';s.searchStation=null;s.station=null;s.selected.clear();s.after=false;void render().catch(fail);}
   if(t.id==='research-weight'){s.weight=t.value;void remount();}
   if(t.id==='research-preview'){s.preview=t.checked;void remount();}
   if(t.dataset.rSelect)select(t.dataset.rSelect);
  };
  host.onfocusin=e=>{if(e.target.id==='research-search'){s.open=true;autocomplete();}};
  host.oninput=e=>{if(e.target.id!=='research-search')return;s.query=e.target.value;s.searchStation=null;s.open=true;const position=e.target.selectionStart;clearTimeout(searchTimer);searchTimer=setTimeout(()=>{if(!active())return;const pending=render();const input=host.querySelector('#research-search');input.focus();input.setSelectionRange(position,position);void pending.catch(fail);},180);};
  host.onkeydown=e=>{if(e.key==='Escape'){s.open=false;autocomplete();}if(e.key==='ArrowDown'&&e.target.id==='research-search'){e.preventDefault();s.open=true;autocomplete();host.querySelector('[data-r-search]')?.focus();}if(e.key==='Enter'&&e.target.id==='research-search'){e.preventDefault();const first=searchCandidates()[0];if(first)choose(first.statId);}};
  await render().catch(fail);
 }catch(e){if(active()){host.dataset.loadState='ERROR';host.innerHTML=`<article class="panel empty-cell" role="alert">조회 오류 · ${esc(e.message)}<button id="recovery-retry">다시 불러오기</button></article>`;host.querySelector('#recovery-retry').onclick=()=>{forceLatest=true;void remount();};}}
}

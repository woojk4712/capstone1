import {createStationMap} from './station-map.js';
import {DISTRICTS} from './dashboard-model.js';

const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = (v, d=0) => v == null ? '—' : Number(v).toLocaleString('ko-KR', {maximumFractionDigits:d});
const labels = {AVAILABLE:'사용가능',CHARGING:'충전중',STOPPED:'운영중지 · 복구 검토',MAINTENANCE:'점검중',COMM_ERROR:'통신이상',UNKNOWN:'상태미확인'};
const days = ['월','화','수','목','금','토','일'];
const districtOf = s => DISTRICTS.find(d => String(s.addr || '').includes(d)) || '미확인';
const clock = m => `${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`;
const keyOf = (s,c) => `ME:${s.statId}:${c.chgerId}`;
const stores = Object.fromEntries(['priorities','maintenance','simulation'].map(tab => [tab, {
  district:'', search:'', station:null, preview:false, replay:false, radius:500,
  weight:'equal', ranking:'potential', mode:'actual', selected:new Set(), after:false,
}]));
let generation=0, map=null, searchTimer=null, revisionTimer=null;
export function disposeResearchTabs(){ generation++; clearTimeout(searchTimer); clearInterval(revisionTimer); map?.destroy(); map=null; }
export function observeAnalysisRevision(onChange,onRevision=()=>{}){
  let previous=null, busy=false;
  const poll=async()=>{if(busy)return;busy=true;try{const data=await read('/api/analysis/revision');onRevision(data.revision);if(previous!==null&&previous!==data.revision)onChange();previous=data.revision;}catch{}finally{busy=false;}};
  void poll();clearInterval(revisionTimer);revisionTimer=setInterval(poll,10000);
}
async function read(path, body){
  const r=await fetch(path,{cache:'no-store',...(body ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)} : {})});
  const data=await r.json();
  if(!r.ok) throw new Error(typeof data.detail==='string' ? data.detail : data.error_type || `HTTP ${r.status}`);
  return data;
}
const buttons=(active,values,key)=>values.map(([id,label])=>`<button data-r-${key}="${id}" class="${String(active)===String(id)?'active':''}">${label}</button>`).join('');
const sumCurve = rows => {let total=0;return rows.map((r,i)=>({rank:i+1,cumulativeKw:total+=r.power_kw}));};
function cumulative(rows, hypothetical=false, simple=false){
  if(!rows.length) return '<p>누적 회복 그래프에 표시할 선택 설비가 없습니다.</p>';
  const max=rows.at(-1).cumulativeKw || 1;
  const points=rows.map((r,i)=>`${30+i/Math.max(1,rows.length-1)*650},${180-r.cumulativeKw/max*150}`).join(' ');
  return `<h3>${hypothetical?'가정 · ':''}${simple?'선택 설비에 따른':'복구순위에 따른'} 가상 누적 회복 정격출력</h3><svg viewBox="0 0 720 220" class="research-cumulative" role="img" aria-label="가상 누적 회복 정격출력"><path d="M30 20V180H700" fill="none" stroke="#ccd6dc"/><polyline points="30,180 ${points}" fill="none" stroke="#07988a" stroke-width="3"/><text x="35" y="20">${num(max)} kW</text><text x="30" y="210">1개 복구</text><text x="600" y="210">${rows.length}개 복구</text></svg>`;
}

export async function mountResearch(host, tab, lib, onQuality){
  disposeResearchTabs(); const run=generation, state=stores[tab];
  host.dataset.loadState='LOADING';
  host.onclick=null; host.onchange=null; host.oninput=null;
  host.innerHTML='<article class="panel empty-cell" role="status">데이터 불러오는 중</article>';
  const params=()=>new URLSearchParams({radius:state.radius,weight:state.weight,preview:state.preview,replay:state.replay});
  const active=()=>run===generation && host.isConnected;
  try {
    // Maintenance never waits for a ranking or current-network calculation.
    const data = tab==='maintenance' ? await read('/api/analysis/stations') :
      tab==='simulation' && state.mode==='simple' ? await read('/api/operations/stations?stopped_only=true') :
      await read('/api/analysis/overview?'+params());
    if(!active())return;
    if(!Array.isArray(data.items)||(tab!=='maintenance'&&!(tab==='simulation'&&state.mode==='simple')&&!Array.isArray(data.potential)))throw new Error('분석 API 응답 구조 확인 필요');
    host.dataset.loadState=data.stale&&!state.replay?'STALE':data.items.length?'READY':'EMPTY';
    observeAnalysisRevision(()=>{if(active())void mountResearch(host,tab,lib,onQuality);},revision=>{if(active())host.dataset.analysisRevision=revision;});
    const all=data.items || [], byId=new Map(all.map(s=>[s.statId,s]));
    const potential=data.potential || [], priorities=data.priorities || [];
    const simple=tab==='simulation' && state.mode==='simple';
    if(!simple)state.actualAvailable=priorities.length>0;
    const candidates = simple ? all.flatMap(s=>s.chargers.filter(c=>c.status==='STOPPED' && c.output_kw>0).map(c=>({
      charger_id:keyOf(s,c),statId:s.statId,chgerId:c.chgerId,name:s.statNm,power_kw:c.output_kw,status:c.status,raw_stat:c.stat,
    }))) : state.mode==='hypothetical' ? potential.filter(r=>['AVAILABLE','CHARGING'].includes(r.status)) : priorities;
    state.selected=new Set([...state.selected].filter(id=>candidates.some(r=>r.charger_id===id)));
    const matches=s=>(!state.district || districtOf(s)===state.district) &&
      (!state.search || String(s.statNm || '').replace(/\s/g,'').toLocaleLowerCase().includes(state.search.replace(/\s/g,'').toLocaleLowerCase()));
    let revision=0;
    const isCurrent=(v)=>active() && revision===v;
    const remount=()=>mountResearch(host,tab,lib,onQuality);
    const fail=e=>{if(active()){
      host.querySelector('#research-error').textContent='조회 오류 · '+e.message;
      for(const selector of ['#research-maintenance','#research-simulation']){
        const output=host.querySelector(selector);
        if(output&&['계산 중','계산 중…','데이터 불러오는 중'].includes(output.textContent.trim())){
          output.textContent='요청 실패 · '+e.message;output.dataset.loadState='ERROR';
        }
      }
    }};
    async function render(){
      const version=++revision; map?.destroy(); map=null;
      const eligible=tab==='maintenance' ? all.filter(s=>s.maintenance_analysis_status==='READY') : all;
      const scoped=eligible.filter(matches);
      const selectable=tab==='simulation' ? scoped.filter(s=>candidates.some(r=>r.statId===s.statId)) : scoped;
      if(!selectable.some(s=>s.statId===state.station))state.station=selectable[0]?.statId || null;
      const scopeIds=new Set(scoped.map(s=>s.statId));
      const ranked=(state.ranking==='potential'?potential:priorities).filter(r=>scopeIds.has(r.statId));
      const choices=candidates.filter(r=>scopeIds.has(r.statId));
      state.selected=new Set([...state.selected].filter(id=>choices.some(r=>r.charger_id===id)));
      const facilityOptions=tab==='simulation'?selectable:scoped;
      const controls=`<div class="research-controls research-filters"><label>자치구<select id="research-district"><option value="">서울시 전체</option>${DISTRICTS.map(d=>`<option ${state.district===d?'selected':''}>${d}</option>`).join('')}</select></label><label>시설명 검색<input id="research-search" value="${esc(state.search)}" placeholder="충전소 이름" autocomplete="off"></label>${tab!=='priorities'?`<label>충전소 선택<select id="research-facility"><option value="">${facilityOptions.length?'충전소 선택':'선택 가능한 시설 없음'}</option>${facilityOptions.map(s=>`<option value="${esc(s.statId)}" ${s.statId===state.station?'selected':''}>${esc(s.statNm)}</option>`).join('')}</select></label>`:''}${tab!=='maintenance'&&!simple?`<label>가중치<select id="research-weight">${[['equal','동일가중'],['demand','수요강조'],['power','출력강조'],['alternative','대체망강조']].map(([id,label])=>`<option value="${id}" ${state.weight===id?'selected':''}>${label}</option>`).join('')}</select></label><div class="segmented">${buttons(state.radius,[[500,'500m'],[1000,'1km']],'radius')}</div>`:''}<button data-r-refresh>새로고침</button></div>`;
      const observation=tab!=='maintenance'&&data.stale?`<div class="research-observation" role="status">${state.replay?'과거 관측 재현 · 현재 운영상태가 아님':'최신 관측 대기 · 저장된 관측으로 분석하려면 아래 항목을 선택하세요.'} · 관측시각 ${esc(data.last_success_at)}${!state.replay?'<button data-r-observed>저장 관측으로 분석 보기</button>':''}</div>`:'';
      const toggles=tab==='maintenance'?'':`<div class="research-options">${!simple?`<label><input id="research-preview" type="checkbox" ${state.preview?'checked':''}> 검토용 Preview (기본 Final)</label>`:''}<label><input id="research-replay" type="checkbox" ${state.replay?'checked':''}> 과거 관측 재현 (현재 결과 아님)</label></div>`;
      const modeButtons=tab==='simulation'?`<div class="segmented scenario-modes">${buttons(state.mode,[['actual','실제 복구'],['hypothetical','가정 시나리오'],['simple','서울 운영현황 단순 시나리오']],'mode').replace('data-r-mode="actual"',`${state.actualAvailable?'':'disabled title="현재 선택 가능한 실제 복구후보 없음" '}data-r-mode="actual"`)}</div>`:'';
      const actualMessage=priorities.length===0 && !simple && tab!=='maintenance'?`<p id="research-actual-empty">${data.stale&&!state.replay?'최신 관측 대기 중으로 실제 복구후보를 확정할 수 없습니다.':'현재 확인된 핵심 분석시설에는 운영중지 복구 대상이 없습니다.'}</p>`:'';
      host.innerHTML=`${modeButtons}${state.preview&&!simple?'<div class="research-warning"><strong>검토용 미확정 분석 · 최종 연구결과가 아님</strong></div>':''}${observation}${controls}${toggles}<p id="research-error" role="alert"></p>${actualMessage}<div id="research-body"></div>`;
      const body=host.querySelector('#research-body');
      if(tab==='maintenance'){
        body.innerHTML=`<article class="panel"><h2>2025년 계획정비 후보시간</h2><p id="maintenance-ready-count">분석가능 시설 ${eligible.length}개 · 현재 필터 ${scoped.length}개</p><div id="research-maintenance" role="status">${state.station?'데이터 불러오는 중':'현재 필터에 분석가능 시설이 없습니다.'}</div><details><summary>정비시간 분석 보류 시설</summary>${all.filter(s=>s.maintenance_analysis_status!=='READY').map(s=>`<p>${esc(s.statNm)} · ${s.maintenance_analysis_status==='HOLD_MIXED'?'정비시간 분석 보류 · 급속/완속 혼합시설':'설비 확인 필요'}</p>`).join('')}</details></article>`;
        if(!state.station)return;
        const sid=state.station;
        const m=await read('/api/analysis/maintenance/'+encodeURIComponent(sid));
        if(!isCurrent(version))return;
        const rec=(title,list=[])=>`<article class="research-candidate"><h3>${title}</h3>${list.length?list.map((c,i)=>`<div><b>${i+1}. ${days[c.weekday]}요일 ${clock(c.startMinute)}~${clock(c.startMinute+c.duration)}</b><p>평균 시작건수 ${num(c.avgStarts,3)}건 · 유효일 ${num(c.validDays)}일<br>시작 시 진행중 기록 평균 ${num(c.avg_active_at_window_start,3)}건<br>계절 안정성 (반기 평균 차이) ${num(c.seasonalStability,3)}건 · 추천 신뢰도 ${esc(c.confidence)}</p></div>`).join(''):'<p>분석자료 없음 · 추천 보류</p>'}</article>`;
        const max=Math.max(1,...(m.heatmap || []).flat().filter(v=>v!=null));
        host.querySelector('#research-maintenance').innerHTML=`<h3>${esc(byId.get(sid)?.statNm)}</h3><p>분석연도 2025 · 유효 관측일 ${num((m.validDaysByWeekday || []).reduce((a,b)=>a+b,0))}일 · ${esc(m.message)}</p><div class="research-candidates">${rec('추천 1시간',m.oneHour)}${rec('추천 2시간',m.twoHour)}</div><h3>요일 × 시간 · 유효 관측일 평균 충전 시작건수</h3>${m.heatmap?`<div class="heatmap"><span></span>${Array.from({length:24},(_,h)=>`<span>${h}</span>`).join('')}${m.heatmap.map((row,w)=>`<span>${days[w]}</span>${row.map((v,h)=>`<div title="${days[w]} ${h}시 · ${num(v,3)}건" style="background:${v==null?'#eee':`rgba(11,149,133,${.08+.9*v/max})`}">${v==null?'—':''}</div>`).join('')}`).join('')}</div>`:'<p>분석자료 없음</p>'}<p>${esc(m.coverageNote)}</p><small>진행중 기록은 실제 충전기 대수가 아닙니다. 1시간·2시간 결과는 별도 후보이며 긴급복구를 미루도록 권고하지 않습니다.</small>`;
        return;
      }
      const tableRows=tab==='simulation'?choices.filter(r=>r.statId===state.station):ranked;
      const emptyReason=data.stale&&!state.replay?'최신 관측이 없어 현재 대상의 유무를 확정할 수 없습니다. 저장 관측으로 분석 보기를 선택할 수 있습니다.':tab==='simulation' ? state.mode==='actual'?'현재 핵심 분석시설에는 실제 운영중지 복구 대상이 없습니다. 가정 또는 서울 운영현황 단순 시나리오를 선택하세요.':'현재 필터에 선택 가능한 설비가 없습니다.' : state.ranking==='recovery'?'현재 확인된 핵심 분석시설에는 운영중지 복구 대상이 없습니다.':'현재 조건에 잠재 영향순위가 없습니다.';
      const scenarioLabel=simple?'환경공단 실제 운영상태 기반 단순 복구 시나리오':state.mode==='hypothetical'?'가정 시나리오 · 실제 운영중지 결과가 아님':'가상 복구 시나리오 · 실제 복구 결과가 아님';
      body.innerHTML=`${tab==='priorities'?`<div class="segmented">${buttons(state.ranking,[['recovery','현재 복구 검토'],['potential','잠재 고장 영향']],'ranking')}</div><p>실제 운영중지 복구 검토와 잠재 고장 영향순위는 별개입니다.</p>`:`<div class="research-warning"><strong>${scenarioLabel}</strong>${simple?'<p>D1 이용량 미연결 시설은 고장 영향도 순위 대상이 아님</p>':''}</div><p>자치구 → 충전소 → 충전기 선택 → 개선 전/후 비교 · 선택 ${state.selected.size}기${state.selected.size?'':' · 복구할 충전기를 선택하세요.'}</p><div class="segmented">${buttons(state.after,[['false','개선 전'],['true','개선 후']],'view')}</div><div id="research-simulation">계산 중</div>`}<div class="research-layout"><article class="panel research-map-panel"><div id="research-map"><div id="tile-notice" hidden>배경지도를 불러올 수 없습니다. 실제 시설 좌표는 표시됩니다.</div></div><div id="research-detail"><p>지도 또는 순위 행을 선택해 상세정보를 확인하세요.</p></div></article><article class="panel research-rank-panel"><h2>${tab==='simulation'?'충전기 선택':state.ranking==='potential'?'잠재 고장 영향':'운영중지 · 복구 검토'}</h2><p id="research-result-count">${tableRows.length}기</p><div class="table-wrap"><table><thead><tr>${tab==='simulation'?'<th>선택</th>':''}<th>순위</th><th>충전소명</th><th>자치구</th><th>statId</th><th>chgerId</th><th>출력(kW)</th><th>현재상태</th>${simple?'':'<th>D</th><th>Q</th><th>B</th><th>Impact</th><th>점수구분</th>'}</tr></thead><tbody>${tableRows.map((r,i)=>`<tr data-r-station="${esc(r.statId)}" data-r-charger="${esc(r.charger_id)}">${tab==='simulation'?`<td><input type="checkbox" data-r-select="${esc(r.charger_id)}" aria-label="${esc(r.name)} ${esc(r.chgerId)} 선택" ${state.selected.has(r.charger_id)?'checked':''}></td>`:''}<td>${r.rank || i+1}</td><td>${esc(r.name)}</td><td>${esc(districtOf(byId.get(r.statId)))}</td><td>${esc(r.statId)}</td><td>${esc(r.chgerId)}</td><td>${num(r.power_kw)}</td><td>${esc(labels[r.status] || r.status)}</td>${simple?'':['D','Q','B','score'].map(k=>`<td>${num(r[k],3)}</td>`).join('')+`<td>${r.scoreIsUpperBound?'상한검토용':'정확'}</td>`}</tr>`).join('')||`<tr><td colspan="14" class="empty-cell">${emptyReason}</td></tr>`}</tbody></table></div>${!simple?`<p class="chart-note">D: 실제 급속 kWh 상대순위 · Q: 충전기/P · B: P/(P+A)<br>가중치 ${data.weights?.map(v=>num(v,3)).join(' / ')} · ${state.radius}m<br>상한검토용 점수는 미분류 주변망을 제외한 상한이며 Final 복구순위에서 제외합니다.</p>`:''}</article></div><article class="panel" id="research-curve"></article>`;
      const mapStations=(tab==='simulation'?selectable:scoped);
      host.querySelector('.research-rank-panel').dataset.loadState=tableRows.length?'READY':data.stale&&!state.replay?'STALE':'EMPTY';
      const mapRows=mapStations.map(s=>({id:s.statId,name:s.statNm,lat:Number(s.lat),lon:Number(s.lng),chargers:s.chargers.map(c=>({...c,display_status:tab==='simulation'&&state.selected.has(keyOf(s,c))?(state.after?'RESTORED':state.mode==='hypothetical'?'STOPPED':c.status):c.status}))}));
      function detail(sid,charger){
        const s=byId.get(sid); if(!s)return;
        state.station=sid;
        const r=potential.find(r=>r.statId===sid && (!charger || r.charger_id===charger));
        const target=mapRows.find(s=>s.id===sid);
        map?.update(mapRows,sid,state.radius);map?.flyTo(target);
        host.querySelector('#research-detail').innerHTML=`<h3>${esc(s.statNm)}</h3><p>${esc(s.addr)} · statId ${esc(s.statId)}</p>${!simple?`<p>2025 실제 급속충전량 ${num(s.annualFastKwh2025)} kWh<br>D ${num(r?.D,3)} · Q ${num(r?.Q,3)} · B ${num(r?.B,3)}<br>500m 대체망 ${num(s.alternativeOutput?.['500'])} kW / 1km ${num(s.alternativeOutput?.['1000'])} kW</p>`:''}${s.chargers.map(c=>`<p>chgerId ${esc(c.chgerId)} · ${num(c.output_kw)} kW · ${esc(labels[c.status])}${tab==='simulation'&&state.selected.has(keyOf(s,c))?` <strong class="scenario-unit-state">가상 비교: ${state.after?'사용가능':state.mode==='hypothetical'?'운영중지':esc(labels[c.status])}</strong>`:''}<br>원본 stat ${esc(c.stat)} · chgerType ${esc(c.chgerType)} · statUpdDt ${esc(c.statUpdDt)}</p>`).join('')}`;
      }
      map=createStationMap(host.querySelector('#research-map'),lib,sid=>{
        if(tab==='simulation'){state.station=sid;void render().catch(fail);}else detail(sid);
      },{hostId:'research-leaflet-map',zoomAnimation:false,fadeAnimation:false,markerZoomAnimation:false});
      map.update(mapRows,state.station,state.radius);
      if(state.district)map.district(state.district);
      if(state.station)detail(state.station);
      host.querySelector('#research-map').dataset.scenario=state.after?'after':'before';
      host.querySelector('#research-map').dataset.recoveredCount=String(state.after?state.selected.size:0);
      host.querySelectorAll('[data-r-station]').forEach(el=>el.onclick=e=>{if(!e.target.matches('input'))detail(el.dataset.rStation,el.dataset.rCharger);});
      const curve=tab==='simulation'?sumCurve(choices.filter(r=>state.selected.has(r.charger_id))):state.ranking==='recovery'?sumCurve(ranked):[];
      host.querySelector('#research-curve').innerHTML=cumulative(curve,tab==='simulation'&&state.mode==='hypothetical',simple);
      if(tab==='simulation'){
        if(data.stale&&!state.replay){
          host.querySelector('#research-simulation').textContent='최신 관측 필요 · 과거 관측 재현을 선택하면 저장된 실제 관측으로 계산할 수 있습니다.';
          return;
        }
        const result=await read(simple?'/api/operations/simulate':'/api/analysis/simulate',simple?{
          chargerIds:[...state.selected],stationIds:scoped.map(s=>s.statId),replay:state.replay,
        }:{chargerIds:[...state.selected],radius:state.radius,weight:state.weight,preview:state.preview,hypothetical:state.mode==='hypothetical',replay:state.replay});
        if(!isCurrent(version))return;
        const shown=state.after?result.after:result.before;
        host.querySelector('#research-simulation').innerHTML=`<div class="simulation-metrics">${[['정상 가용출력','normalKw','kW'],['운영중지 출력','stoppedKw','kW'],['남은 운영중지 설비수','stoppedCount','기']].map(([label,k,unit])=>`<div><small>${label} · ${state.after?'개선 후':'개선 전'}</small><strong data-sim="${k}">${num(shown[k])} ${unit}</strong><small>${num(result.before[k])} → ${num(result.after[k])} ${unit}</small></div>`).join('')}<div><small>선택 복구출력 / 회복 kW</small><strong data-sim="recoveredKw">${num(result.recoveredKw)} kW</strong></div><div><small>회복률 · 개선 전 정상출력 대비</small><strong data-sim="recoveryRate">${num(result.recoveryRate,2)}${result.recoveryRate==null?'':'%'}</strong></div></div><p>명목 정격출력 기반 가상 시나리오 · 실제 API 상태와 DB 원자료는 변경하지 않습니다.${simple?' · 계산 범위: 현재 자치구/검색 조건의 시설':' · 계산 범위: 현재 분석모드의 핵심시설 전체'}</p>`;
      }
    }
    host.onclick=e=>{
      const b=e.target.closest('button');if(!b)return;
      if(b.hasAttribute('data-r-refresh')){void remount();return;}
      if(b.dataset.rMode){state.mode=b.dataset.rMode;state.district='';state.search='';state.selected.clear();state.station=null;state.after=false;void remount();return;}
      if(b.hasAttribute('data-r-observed')){state.replay=true;void remount();return;}
      if(b.dataset.rRadius){state.radius=Number(b.dataset.rRadius);void remount();return;}
      if(b.dataset.rRanking){state.ranking=b.dataset.rRanking;void render().catch(fail);}
      if(b.dataset.rView){state.after=b.dataset.rView==='true';void render().catch(fail);}
    };
    host.onchange=e=>{
      const t=e.target;
      if(t.id==='research-preview'||t.id==='research-replay'){state[t.id.endsWith('preview')?'preview':'replay']=t.checked;state.selected.clear();state.after=false;void remount();return;}
      if(t.id==='research-weight'){state.weight=t.value;void remount();return;}
      if(t.id==='research-district'){state.district=t.value;state.station=null;state.selected.clear();state.after=false;}
      if(t.id==='research-facility'){state.station=t.value;}
      if(t.dataset.rSelect){t.checked?state.selected.add(t.dataset.rSelect):state.selected.delete(t.dataset.rSelect);}
      void render().catch(fail);
    };
    host.oninput=e=>{
      if(e.target.id!=='research-search')return;
      const pos=e.target.selectionStart;state.search=e.target.value;state.station=null;
      clearTimeout(searchTimer);
      searchTimer=setTimeout(()=>{
        if(!active())return;
        const pending=render();
        const input=host.querySelector('#research-search');input?.focus();input?.setSelectionRange(pos,pos);
        void pending.catch(fail);
      },180);
    };
    await render().catch(fail);
  } catch(e){if(active()){host.dataset.loadState='ERROR';host.innerHTML=`<article class="panel empty-cell" role="alert">조회 오류 · ${esc(e.message)}<p>다른 탭은 독립적으로 사용할 수 있습니다.</p><button id="research-retry">다시 불러오기</button></article>`;}
    host.querySelector('#research-retry')?.addEventListener('click',()=>mountResearch(host,tab,lib,onQuality));}
}

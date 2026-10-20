import {inventoryRows,liveConnection} from './dashboard-model.js';
const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels={AVAILABLE:'이용가능',CHARGING:'충전중',STOPPED:'운영중지',MAINTENANCE:'점검중',COMM_ERROR:'상태 불확실/통신이상',UNKNOWN:'상태 불확실/통신이상'};
const colors={AVAILABLE:'#0b9585',CHARGING:'#3976cf',STOPPED:'#e87e35',MAINTENANCE:'#b79423',UNKNOWN:'#8796a6',COMM_ERROR:'#8796a6'};
const time=v=>v?new Date(v).toLocaleString('ko-KR',{timeZone:'Asia/Seoul',hour12:false}):'마지막 성공 수집 없음';
async function get(path){const response=await fetch(path,{cache:'no-store'});const body=await response.json();if(!response.ok){const error=new Error(body.error_type?'환경공단 API 연결 실패 · 데이터 미수집 · '+body.error_type:body.detail?.message||'내부 API 요청 실패');error.detail=body.detail;throw error;}return body;}
export function stationStatus(rows){return ['STOPPED','MAINTENANCE','UNKNOWN','COMM_ERROR','CHARGING','AVAILABLE'].find(s=>rows.some(r=>r.status===s))||'UNKNOWN';}

export function mountLiveAPI(root,{L=globalThis.L}={}){
 let disposed=false,map=null,layer=null,rows=[],stations=[],selected=null,radius=500,system=null,loadId=0,selectId=0,poll=null;
 root.innerHTML=`<header class="live-header"><div><p class="live-brand">SEOUL CHARGE OPS / LIVE</p><h1>환경공단 전국 원자료 확인</h1></div><div class="live-actions"><a href="/analysis">이용실적 분석</a><button id="live-refresh">새로고침</button></div></header><main class="live-shell"><p class="live-intro">한국환경공단 관측 데이터 · 직선거리 기준</p><section id="live-system" class="live-system" aria-label="API 연결 상태"></section><div id="live-notice" aria-live="polite"></div><div class="live-workspace"><section class="live-card live-map-panel"><div class="live-map-head"><h2>충전소 지도 <small id="live-count"></small></h2><div class="live-radius"><button data-radius="500" class="active">500m</button><button data-radius="1000">1km</button></div></div><div id="live-map" class="live-map" aria-label="실제 충전소 Leaflet 지도"></div><div class="live-legend">${['AVAILABLE','CHARGING','STOPPED','MAINTENANCE','UNKNOWN'].map(s=>`<span><i style="background:${colors[s]}"></i>${labels[s]}</span>`).join('')}</div><div id="live-stations" class="live-stations"></div></section><aside id="live-detail" class="live-card live-detail" aria-live="polite"><h2>충전소 상세</h2><p class="live-empty">지도에서 충전소를 선택하세요.</p></aside></div><p class="live-footer">제공기관 상태 변경시각과 백엔드 수집시각은 별도로 표시합니다. 충전중 설비를 포함한 정상 급속망은 즉시 이용 가능 대수와 다릅니다.</p></main>`;
 const $=s=>root.querySelector(s);
 if(L){map=L.map($('#live-map')).setView([37.5665,126.978],11);layer=L.layerGroup().addTo(map);L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors'}).addTo(map).on('tileerror',()=>{$('#live-map').dataset.tiles='unavailable';});}
 else $('#live-map').innerHTML='<p class="live-map-unavailable">Leaflet 지도 라이브러리 연결 실패<br>인터넷 연결 후 새로고침하세요. 아래 충전소 목록에서도 상세정보를 확인할 수 있습니다.</p>';
 function statusView(){if(!system)return;$('#live-system').innerHTML=['ME'].map(p=>{const s=system.providers[p];return `<article class="live-card"><small>${p==='ME'?'한국환경공단':'한국전력공사 · 교차검증'}</small><strong>${s.connected&&s.current_error===null?'환경공단 연결됨':'환경공단 연결 실패'}</strong><p>${escape(s.error?.message||'수집 완료')}<br>${escape(s.error?.kind||'')}<br>마지막 성공: ${time(s.last_success_at)}<br>수집 데이터: ${s.count}건</p></article>`;}).join('')+`<article class="live-card"><small>데이터 기준</small><strong>${system.collecting?'수집 중':system.stale?'최신 상태 확인 필요':'최근 수집 완료'}</strong><p>${system.statusClassificationVerified?'운영상태 코드: 검증 완료':'운영상태 코드: 확인 필요'}<br>${system.chargerTypeClassificationVerified?'급속/완속 코드: 검증 완료':'커넥터 코드 확인 / 급속 분류 보류'}<br>${system.network?.error?escape(system.network.error.message):'외부 연결 진단 기록 확인'}<br>네트워크 진단: ${escape(system.network?.error?.kind||'정상')}</p></article>`;}
 function notice(message,error=false){$('#live-notice').innerHTML=message?`<div class="live-notice ${error?'error':''}">${escape(message)}</div>`:'';}
 function draw(alternatives=[]){
  const ids=new Set(alternatives.map(r=>String(r.statId)));layer?.clearLayers();
  for(const station of stations){
   const position=station.rows.find(r=>Number.isFinite(r.latitude)&&Number.isFinite(r.longitude));if(!position||!map)continue;
   const status=stationStatus(station.rows),isSelected=selected===station.id;
   const marker=L.marker([position.latitude,position.longitude],{icon:L.divIcon({className:`live-marker ${ids.has(station.id)?'alternative':''} ${isSelected?'selected':''}`,html:`<span style="background:${colors[status]||colors.UNKNOWN}">${status==='UNKNOWN'?'?':status==='STOPPED'?'!':'⚡'}</span>`,iconSize:[28,28],iconAnchor:[14,14]})}).addTo(layer);
   const tooltip=document.createElement('span');tooltip.textContent=station.name;marker.bindTooltip(tooltip,{className:'live-tooltip'});marker.on('click',()=>select(station.id));
   marker.getElement()?.setAttribute('data-live-station',station.id);marker.getElement()?.setAttribute('aria-label',station.name);marker.getElement()?.setAttribute('data-status',status);
  }
  if(selected&&map){const station=stations.find(s=>s.id===selected),p=station?.rows.find(r=>Number.isFinite(r.latitude)&&Number.isFinite(r.longitude));if(p)L.circle([p.latitude,p.longitude],{radius,color:'#0b9585',weight:1,fillOpacity:.06}).addTo(layer);}
  $('#live-count').textContent=`${stations.length}개소 / ${rows.length}기`;
  $('#live-stations').innerHTML=stations.length?stations.map(s=>`<button data-station="${escape(s.id)}">${escape(s.name)}</button>`).join(''):'<p class="live-empty">데이터 미수집 · 표시할 충전소 없음</p>';
 }
 async function select(id){
  selected=id;const request=++selectId;draw();$('#live-detail').textContent='충전소 상세를 불러오고 있습니다…';
  try{
   const detail=await get('/api/chargers/'+encodeURIComponent(id));if(disposed||request!==selectId)return;
   const first=detail.chargers[0]||{},s=stations.find(s=>s.id===id);
   $('#live-detail').innerHTML=`<h2>${escape(first.statNm||id)}</h2><p>${escape(first.addr||'주소 미제공')}</p>${detail.stale?'<p class="live-notice error">이전 수집 데이터 · 최신 상태 확인 필요</p>':''}${detail.chargers.map(c=>`<article class="live-charger"><b>충전기 ${escape(c.chgerId)}</b><p class="live-state" style="color:${colors[c.status]||colors.UNKNOWN}">${escape(c.status_label||labels[c.status]||labels.UNKNOWN)}</p><dl><dt>출력</dt><dd>${c.output_kw??'미제공'} ${c.output_kw!=null?'kW':''}</dd><dt>이용시간</dt><dd>${escape(c.useTime??'미제공')}</dd><dt>이용제한</dt><dd>${escape(c.limitDetail??c.limitYn??'미제공')}</dd><dt>상태 변경시각</dt><dd>${escape(c.statUpdDt??'미제공')}</dd><dt>수집시각</dt><dd>${time(c.collected_at)}</dd></dl></article>`).join('')}<h3>주변 정상 급속충전기 · ${radius}m</h3><div id="live-alternatives">조회 중…</div>`;
   if(s&&map){const p=s.rows.find(r=>Number.isFinite(r.latitude)&&Number.isFinite(r.longitude));if(p)map.setView([p.latitude,p.longitude],15);}
   try{const alternatives=await get(`/api/chargers/${encodeURIComponent(id)}/alternatives?radius=${radius}`);if(disposed||request!==selectId)return;draw(alternatives.items);$('#live-alternatives').textContent=alternatives.items.length?`${alternatives.items.length}기 · 이용가능/충전중 포함`:alternatives.stale?'최신 상태 확인 불가 · 대체망 추천 보류':'검증된 정상 급속 대체망 없음';}
   catch{if(!disposed&&request===selectId)$('#live-alternatives').textContent='대체망 조회 실패 · 좌표 또는 분류 검증 필요';}
  }catch(error){if(!disposed&&request===selectId)$('#live-detail').textContent=error.message;}
 }
 async function load(){const request=++loadId;notice('백엔드 수집 상태를 확인하고 있습니다…');try{system=await get('/api/system/status');if(disposed||request!==loadId)return;statusView();try{const data=await get('/api/chargers');if(disposed||request!==loadId)return;rows=inventoryRows(data);const groups=new Map();for(const row of rows){const id=String(row.statId);if(!groups.has(id))groups.set(id,{id,name:row.statNm||id,rows:[]});groups.get(id).rows.push(row);}stations=[...groups.values()];draw();notice(data.stale?'오래된 관측 · 최신 상태 확인 필요 · 마지막 성공 수집 데이터를 상태 불확실로 표시합니다.':!data.classification_verified?'실제 수집 목록 · 급속 유형 분류 대기. 운영상태 검증과는 별개입니다. 분석·대체망 추천은 보류합니다.':'',data.stale);if(selected&&stations.some(s=>s.id===selected))await select(selected);}
  catch(error){rows=[];stations=[];selected=null;selectId++;draw();$('#live-detail').textContent='데이터 미수집 · 마지막 성공 수집 없음';notice(`${error.message}${error.detail?.cause?.message?' · '+error.detail.cause.message:''}`,true);}}
  catch{if(disposed||request!==loadId)return;rows=[];stations=[];draw();notice('백엔드 API 연결 실패 · 데이터 미수집 · 마지막 성공 수집 상태 확인 불가',true);}}
 function click(event){if(event.target.closest('#live-refresh'))load();const button=event.target.closest('[data-station],[data-radius]');if(button?.dataset.station)select(button.dataset.station);if(button?.dataset.radius){radius=Number(button.dataset.radius);root.querySelectorAll('[data-radius]').forEach(b=>b.classList.toggle('active',Number(b.dataset.radius)===radius));if(selected)select(selected);}}
 root.addEventListener('click',click);load();poll=setInterval(load,30000);
 return ()=>{disposed=true;clearInterval(poll);root.removeEventListener('click',click);map?.remove();};
}

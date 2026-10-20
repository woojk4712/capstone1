import { DISTRICT_BOUNDS } from './district-bounds.js';
export const DISTRICTS=['강남구','강동구','강북구','강서구','관악구','광진구','구로구','금천구','노원구','도봉구','동대문구','동작구','마포구','서대문구','서초구','성동구','성북구','송파구','양천구','영등포구','용산구','은평구','종로구','중구','중랑구'];
export const SEOUL_BOUNDS=Object.values(DISTRICT_BOUNDS).reduce((a,b)=>[Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.max(a[2],b[2]),Math.max(a[3],b[3])],[180,90,-180,-90]);
export { DISTRICT_BOUNDS };
export const normalizeName=s=>String(s??'').normalize('NFKC').toLowerCase().replace(/[\s()_·.,-]/g,'');
function editDistance(a,b){let prev=Array.from({length:b.length+1},(_,i)=>i);for(let i=1;i<=a.length;i++){const next=[i];for(let j=1;j<=b.length;j++)next[j]=Math.min(next[j-1]+1,prev[j]+1,prev[j-1]+(a[i-1]===b[j-1]?0:1));prev=next;}return prev[b.length];}
export function nameMatch(name,query){const n=normalizeName(name),q=normalizeName(query);if(!q)return 3;if(n===q)return 0;if(n.includes(q))return 1;if(q.length<2)return null;const threshold=Math.min(2,Math.max(1,Math.floor(q.length/3)));for(let i=0;i<=Math.max(0,n.length-q.length);i++){if(editDistance(n.slice(i,i+q.length),q)<=threshold)return 2;}return null;}
export function searchStations(stations,query='',district=''){return stations.filter(s=>nameMatch(s.name,query)!==null).sort((a,b)=>Number(b.district===district)-Number(a.district===district)||(query?nameMatch(a.name,query)-nameMatch(b.name,query):0)||a.name.localeCompare(b.name,'ko')||a.id.localeCompare(b.id));}
export function filterStations(stations,filters){return stations.filter(s=>(!filters.district||s.district===filters.district)&&(!filters.searchStation||s.id===filters.searchStation)&&nameMatch(s.name,filters.search)!==null&&(!filters.status||s.chargers.some(c=>filters.status==='NORMAL'?['AVAILABLE','CHARGING','RESTORED'].includes(c.display_status):filters.status==='UNKNOWN'?['UNKNOWN','COMM_ERROR'].includes(c.display_status):c.display_status===filters.status))&&(!filters.qualityFilter||(filters.qualityFilter==='held')===(s.quality_flags.length>0))&&(!filters.powerMin||s.totals.total_kw>=Number(filters.powerMin))&&(!filters.powerMax||s.totals.total_kw<=Number(filters.powerMax)));}
export function mapStations(data,targets){const ids=new Set(targets.map(s=>s.id));return (data?.map_stations||data?.stations||[]).filter(s=>(data?.provider_inventory&&!data.inventory_only)||ids.has(s.id)||s.near_target_ids?.some(id=>ids.has(id))).map(s=>({...s,map_role:ids.has(s.id)?'target':data?.provider_inventory?'inventory':'alternative'}));}

// Leaflet/SVG share the same real /api/chargers coordinates. Missing coordinates
// are omitted; no default location or replacement station is generated.
export function attachChargerInventory(base,inventory){
 const lookup=new Map();
 for(const row of [...(inventory.items||[]),...(inventory.unclassified_items||[])]){
  if(row.statId==null||!Number.isFinite(row.latitude)||!Number.isFinite(row.longitude))continue;
  const id='ME:'+String(row.statId);if(!lookup.has(id))lookup.set(id,row);
 }
 return {...base,map_stations:(base.map_stations||[]).filter(s=>lookup.has(s.id)).map(s=>{const row=lookup.get(s.id);return {...s,lat:row.latitude,lon:row.longitude};})};
}

export function inventoryRows(data){
 const rows=Array.isArray(data)?data:[...(data?.items||[]),...(data?.unclassified_items||[])],unique=new Map();
 const number=v=>v==null||String(v).trim()===''?null:Number.isFinite(Number(v))?Number(v):null;
 for(const raw of rows){
  if(raw.statId==null||raw.chgerId==null)continue;
  const latitude=number(raw.lat??raw.latitude),longitude=number(raw.lng??raw.longitude);
  const valid=latitude!=null&&longitude!=null&&Math.abs(latitude)<=90&&Math.abs(longitude)<=180&&(latitude!==0||longitude!==0);
  unique.set(JSON.stringify([String(raw.statId),String(raw.chgerId)]),{...raw,latitude:valid?latitude:null,longitude:valid?longitude:null,output_kw:number(raw.output??raw.output_kw)});
 }
 return [...unique.values()];
}

export function liveConnection(system,inventory){
 const me=system?.providers?.ME;
 const connected=me?.connected===true&&me.current_error===null;
 const rows=inventoryRows(inventory);
 return {connected,dataConnected:inventory!=null&&rows.length>0,count:rows.length,
  stored:system?.stored_charger_count??inventory?.inventory_count??rows.length,
  ...classificationState(inventory??system)};
}

// ME-only evidence flags. An explicit false must override the legacy flag.
// KEPCO connectivity and schema are never classification evidence.
export function classificationState(inventory={}){
 const legacy=inventory?.classification_verified===true;
 const status=inventory?.statusClassificationVerified??inventory?.status_classification_verified??legacy;
 const type=inventory?.chargerTypeClassificationVerified??inventory?.charger_type_classification_verified??legacy;
 return {statusClassificationVerified:status===true,chargerTypeClassificationVerified:type===true,
  classificationVerified:status===true&&type===true};
}

export function inventoryDashboard(inventory){
 const groups=new Map(),verification=classificationState(inventory),verified=verification.classificationVerified;
 const keys=['total_kw','normal_kw','stopped_kw','uncertain_kw','charger_count','normal_count','stopped_count','maintenance_count','uncertain_count','missing_power_count'];
 for(const row of inventoryRows(inventory)){
  const id='ME:'+row.statId;
  if(!groups.has(id))groups.set(id,{id,name:row.statNm||String(row.statId),address:row.addr||'',
   district:DISTRICTS.find(d=>String(row.addr||'').includes(d))||'미확인',lat:null,lon:null,chargers:[],
   annual_kwh:null,monthly_kwh:null,quality_flags:verified?['분석 근거 검토 필요']:['충전기 유형 분류 기준 검증 필요'],
   totals:Object.fromEntries(keys.map(k=>[k,0]))});
  const s=groups.get(id);
  if(s.lat==null&&row.latitude!=null){s.lat=row.latitude;s.lon=row.longitude;}
  const status=verification.statusClassificationVerified&&['AVAILABLE','CHARGING','STOPPED','MAINTENANCE','COMM_ERROR','UNKNOWN'].includes(row.status)?row.status:'UNKNOWN';
  s.chargers.push({...row,id:id+':'+row.chgerId,source_charger_id:row.chgerId,power_kw:row.output_kw,
    display_status:status,last_verified_at:verification.statusClassificationVerified?row.collected_at:null});
  const t=s.totals,power=row.output_kw??0;t.charger_count++;t.total_kw+=power;
  if(row.output_kw==null)t.missing_power_count++;
  if(['AVAILABLE','CHARGING'].includes(status)){t.normal_count++;t.normal_kw+=power;}
  else if(status==='STOPPED'){t.stopped_count++;t.stopped_kw+=power;}
  else{t.uncertain_kw+=power;if(status==='MAINTENANCE')t.maintenance_count++;else t.uncertain_count++;}
 }
 const stations=[...groups.values()],stamp=inventory?.last_success_at;
 return {stations,map_stations:stations.filter(s=>s.lat!=null&&s.lon!=null),provider_inventory:true,
  ...verification,classification_verified:verified,inventory_only:true,mode:'live',observed_at:stamp,snapshot_id:'ME:'+stamp,
  priorities:[],held:[],quality_flags:[],totals:Object.fromEntries(keys.map(k=>[k,stations.reduce((a,s)=>a+s.totals[k],0)]))};
}

// Operational geography is independent of D1 matching and KEPCO validation.
// Without reviewed ME codes, show explicitly labelled raw Seoul observations;
// never infer rapid charging from power, or status meaning from numeric codes.
export function seoulOperationsDashboard(inventory={}){
 const verification=classificationState(inventory),verified=verification.classificationVerified;
 const rows=inventoryRows(inventory).filter(c=>String(c.addr||'').trim().startsWith('서울특별시')&&
  c.delYn!=='Y'&&c.latitude!=null&&c.longitude!=null&&(!verified||inventory.include_all===true||c.analysis_eligible===true));
 const result=inventoryDashboard({...inventory,items:rows,unclassified_items:[],classification_verified:verified});
 for(const station of result.stations){
  const district=station.address.trim().match(/^서울특별시\s+([^\s]+구)(?:\s|$)/)?.[1];
  station.district=DISTRICTS.includes(district)?district:'미확인';
  station.statId=station.id.slice(3);
  station.quality_flags=verified?[]:['급속/상태 코드 분류 검증 중'];
  if(!verification.statusClassificationVerified||(inventory.stale===true&&!inventory.observation_only)){
   for(const k of ['normal_kw','stopped_kw','uncertain_kw','normal_count','stopped_count','maintenance_count','uncertain_count'])station.totals[k]=null;
  }
 }
 return {...result,operations_dataset:true,scope:verified?'seoul_verified_fast':'seoul_raw_unclassified',
  stale:inventory.stale===true,observation_only:inventory.observation_only===true,
  displayedChargerCount:rows.length,displayedStationCount:result.stations.length,
  classification_verified:verified,core_dataset:false};
}

export function coreDashboard(data={}){
 const stations=(data.items||[]).filter(s=>s.matchStatus==='confirmed').map(s=>{
  const chargers=(s.chargers||[]).map(c=>({...c,id:s.analysisStationId+':'+c.chgerId,power_kw:c.output_kw,
   display_status:data.classificationVerified?c.status||'UNKNOWN':'UNKNOWN',last_verified_at:data.classificationVerified?c.collected_at:null}));
  const counts=s.statusCounts||{},normal=counts.AVAILABLE==null||counts.CHARGING==null?null:counts.AVAILABLE+counts.CHARGING;
  return {id:s.analysisStationId||'ME:'+s.statId,statId:s.statId,name:s.statNm||s.d1StationName,address:s.addr||'',
   district:DISTRICTS.find(d=>String(s.addr||'').includes(d))||'미확인',lat:s.lat==null||String(s.lat).trim()===''?null:Number(s.lat),lon:s.lng==null||String(s.lng).trim()===''?null:Number(s.lng),chargers,
   annual_kwh:s.annualFastKwh2025,monthly_kwh:s.monthlyFastKwh2025,match_status:'confirmed',
   quality_flags:data.classificationVerified?[]:['분류 기준 검증 필요'],
   totals:{charger_count:s.chargerCount,total_kw:s.totalRatedOutputKw,normal_kw:s.availableRatedOutputKw,
    stopped_kw:s.stoppedRatedOutputKw,uncertain_kw:s.totalRatedOutputKw==null||s.availableRatedOutputKw==null||s.stoppedRatedOutputKw==null?null:s.totalRatedOutputKw-s.availableRatedOutputKw-s.stoppedRatedOutputKw,
    normal_count:normal,stopped_count:counts.STOPPED??null,maintenance_count:counts.MAINTENANCE??null,
    uncertain_count:counts.UNKNOWN==null||counts.COMM_ERROR==null?null:counts.UNKNOWN+counts.COMM_ERROR,missing_power_count:null}};
 });
 return {stations,map_stations:stations.filter(s=>Number.isFinite(s.lat)&&Number.isFinite(s.lon)&&Math.abs(s.lat)<=90&&Math.abs(s.lon)<=180&&(s.lat!==0||s.lon!==0)),core_dataset:true,
  provider_inventory:false,mode:'live',observed_at:data.last_success_at,snapshot_id:'CORE:'+data.last_success_at,
  classification_verified:data.classificationVerified===true,priorities:[],held:[],quality_flags:[]};
}
export function markerStatus(s){const cs=s.chargers.filter(c=>c.display_status!=='DELETED');if(cs.some(c=>c.display_status==='STOPPED'))return 'STOPPED';if(cs.some(c=>c.display_status==='MAINTENANCE'))return 'MAINTENANCE';if(!cs.length||cs.some(c=>['UNKNOWN','COMM_ERROR'].includes(c.display_status)))return 'UNKNOWN';return 'NORMAL';}
export function zoomForBounds(bounds,width=750,height=430){const [a,b,c,d]=bounds;const rad=y=>Math.log(Math.tan(Math.PI/4+y*Math.PI/360));const dx=Math.max((c-a)/360,1e-6),dy=Math.max((rad(d)-rad(b))/(2*Math.PI),1e-6);return Math.max(8,Math.min(16,Math.floor(Math.log2(Math.min((width-70)/(256*dx),(height-70)/(256*dy))))));}
export function scenarioMetrics(before,after,selected,stations,priorities){const ids=new Set(stations.map(s=>s.id));const selectedIds=new Set(selected);const recovered=after.normal_kw-before.normal_kw;const top=priorities.filter(r=>ids.has(r.station_id)).slice(0,10);return {recovered_kw:recovered,recovery_rate:before.stopped_kw?recovered/before.stopped_kw:0,stopped_kw_reduction:before.stopped_kw-after.stopped_kw,baseline_top_count:top.length,baseline_top_remaining:top.filter(r=>!selectedIds.has(r.charger_id)).length};}

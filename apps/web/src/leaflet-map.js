import {DISTRICT_BOUNDS,SEOUL_BOUNDS} from './dashboard-model.js';
const colors={AVAILABLE:'#07988a',CHARGING:'#3976cf',STOPPED:'#e87e35',MAINTENANCE:'#ad8b26',UNKNOWN:'#94a3b8',COMM_ERROR:'#94a3b8',RESTORED:'#07988a'};
const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function createLeafletMap(container,L,onSelect,options={}){
 const host=document.createElement('div');host.id=options.hostId||'leaflet-map';container.querySelector('#offline-map')?.remove();container.prepend(host);
 const map=L.map(host,{zoomControl:false,preferCanvas:true,...options}).setView([37.56,126.98],11),layer=L.layerGroup().addTo(map);
 L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors'}).addTo(map).on('tileerror',()=>{container.querySelector('#tile-notice').hidden=false;});
 function record(){const c=map.getCenter();container.dataset.longitude=String(c.lng);container.dataset.latitude=String(c.lat);container.dataset.zoom=String(map.getZoom());}map.on('moveend',record);
 function fit(b){map.fitBounds([[b[1],b[0]],[b[3],b[2]]],{padding:[35,35],maxZoom:16});record();}
 let destroyed=false;const resize=new ResizeObserver(()=>{if(!destroyed)map.invalidateSize();});resize.observe(container);fit(SEOUL_BOUNDS);
 return {update(rows,selected,radius){layer.clearLayers();let count=0;for(const s of rows){if(!Number.isFinite(s.lat)||!Number.isFinite(s.lon))continue;count++;const states=s.chargers.map(c=>c.display_status||c.status||'UNKNOWN'),status=['STOPPED','MAINTENANCE','UNKNOWN','COMM_ERROR','CHARGING','AVAILABLE','RESTORED'].find(v=>states.includes(v))||'UNKNOWN';
  const marker=rows.length>1500?L.circleMarker([s.lat,s.lon],{radius:s.id===selected?9:5,color:colors[status],fillColor:colors[status],fillOpacity:.85,weight:1}).addTo(layer):L.marker([s.lat,s.lon],{icon:L.divIcon({className:'dashboard-leaflet-marker',html:`<button class="map-marker ${s.id===selected?'highlighted-marker':''} ${s.map_role==='alternative'?'alternative-marker':''}" data-map-station="${escape(s.id)}" data-marker-status="${status}" aria-label="${escape(s.name)}" style="background:${colors[status]}">${status==='UNKNOWN'?'?':status==='STOPPED'?'!':'ϟ'}${s.virtualRestoredCount?`<span class="virtual-restored-badge" data-virtual-restored="${s.virtualRestoredCount}">+${s.virtualRestoredCount}</span>`:''}</button>`,iconSize:[30,30],iconAnchor:[15,15]})}).addTo(layer);
  const name=document.createElement('span');name.textContent=s.name;marker.bindTooltip(name);marker.on('click',()=>onSelect(s.id));
  if(s.id===selected)L.circle([s.lat,s.lon],{radius,color:'#0b9585',weight:1,fillOpacity:.10,interactive:false}).addTo(layer);
 }container.dataset.markerCount=String(count);record();},district(name){fit(DISTRICT_BOUNDS[name]||SEOUL_BOUNDS);},flyTo(s){if(Number.isFinite(s?.lat)&&Number.isFinite(s?.lon)){map.setView([s.lat,s.lon],15);record();}},zoomBy(d){map.setZoom(Math.min(18,Math.max(8,map.getZoom()+d)));record();},reset(){fit(SEOUL_BOUNDS);},destroy(){destroyed=true;resize.disconnect();map.stop();map.remove();host.remove();}};
}

import test from 'node:test';
import assert from 'node:assert/strict';
import {attachChargerInventory,inventoryRows,inventoryDashboard,liveConnection,coreDashboard,filterStations,searchStations,seoulOperationsDashboard,classificationState} from '../apps/web/src/dashboard-model.js';

test('ME status approval works independently from charger type approval and KEPCO',()=>{
 const data={statusClassificationVerified:true,chargerTypeClassificationVerified:false,classification_verified:false,
  items:[{statId:'A',chgerId:'1',addr:'서울특별시 강남구',delYn:'N',lat:37.5,lng:127,stat:'4',status:'STOPPED',output:100}]};
 const connection=liveConnection({providers:{ME:{connected:true,current_error:null},KEPCO:{connected:false,schema_verified:false}}},data);
 assert.equal(connection.statusClassificationVerified,true);
 assert.equal(connection.chargerTypeClassificationVerified,false);
 assert.equal(connection.classificationVerified,false);
 const operations=seoulOperationsDashboard(data);
 assert.equal(operations.stations[0].chargers[0].display_status,'STOPPED');
 assert.equal(operations.stations[0].chargers[0].stat,'4');
 assert.equal(operations.stations[0].totals.stopped_count,1);
 assert.equal(operations.priorities.length,0);
 assert.equal(classificationState({classification_verified:true,statusClassificationVerified:false}).statusClassificationVerified,false);
 assert.equal(classificationState({classification_verified:false,KEPCO_STATUS_MAP:{4:'STOPPED'}}).statusClassificationVerified,false);
});

test('real inventory controls marker coordinates; missing coordinates never get a default marker',()=>{
 const base={map_stations:[{id:'ME:A',lat:0,lon:0},{id:'ME:B',lat:1,lon:1}],stations:[],totals:{}};
 const updated=attachChargerInventory(base,{items:[{statId:'A',latitude:37.5,longitude:127.1},{statId:'B',latitude:null,longitude:null}],unclassified_items:[]});
 assert.equal(updated.map_stations.length,1);assert.equal(updated.map_stations[0].lat,37.5);assert.equal(updated.map_stations[0].lon,127.1);
 assert.equal(base.map_stations[0].lat,0);
 assert.equal(attachChargerInventory(base,{items:[],unclassified_items:[]}).map_stations.length,0);
});

test('successful API and actual unclassified inventory are independent from classification approval',()=>{
 const inventory={items:[],unclassified_items:[{statId:'A',chgerId:'1',statNm:'Actual response fixture',addr:'서울 강남구',lat:'37.5',lng:'127',output:'100',stat:'2'}],classification_verified:false,inventory_count:1};
 const state=liveConnection({providers:{ME:{connected:true,current_error:null}},stored_charger_count:1},inventory);
 assert.equal(state.connected,true);assert.equal(state.dataConnected,true);assert.equal(state.classificationVerified,false);
 const base=inventoryDashboard(inventory);
 assert.equal(base.stations.length,1);assert.equal(base.map_stations.length,1);
 assert.equal(base.stations[0].chargers[0].display_status,'UNKNOWN');
 assert.equal(base.stations[0].chargers[0].stat,'2');
 assert.equal(base.stations[0].lat,37.5);assert.equal(base.stations[0].totals.charger_count,1);
 assert.equal(base.priorities.length,0);
});

test('coordinates parse strings, reject empty and out of range; group only by real station IDs',()=>{
 const data={items:[{statId:'A',chgerId:'1',lat:'37',lng:'127'},{statId:'A',chgerId:'2',latitude:37,longitude:127},
  {statId:'B',chgerId:'1',lat:'',lng:''},{statId:'C',chgerId:'1',lat:'91',lng:'127'}]};
 const rows=inventoryRows(data),base=inventoryDashboard(data);
 assert.equal(rows.length,4);assert.equal(base.stations.length,3);assert.equal(base.map_stations.length,1);
 assert.equal(base.stations[0].chargers.length,2);assert.equal(rows[2].latitude,null);assert.equal(rows[3].latitude,null);
});

test('a current API error does not become connected through stored data or classification',()=>{
 assert.equal(liveConnection({providers:{ME:{connected:true,current_error:{kind:'timeout'}}}},{items:[],classification_verified:true}).connected,false);
 assert.equal(liveConnection(null,null).dataConnected,false);
});

test('main dataset and search contain confirmed core stations only, not raw network or review candidates',()=>{
 const data={classificationVerified:false,items:[
  {analysisStationId:'ME:A',statId:'A',statNm:'가 시설',matchStatus:'confirmed',addr:'서울특별시 강남구',lat:'37.5',lng:'127',chargerCount:null},
  {analysisStationId:'ME:B',statId:'B',statNm:'나 시설',matchStatus:'review',addr:'서울특별시 종로구',lat:37.6,lng:127},
  {analysisStationId:'ME:C',statId:'C',statNm:'다 시설',matchStatus:'confirmed',addr:'서울특별시 종로구',lat:null,lng:null} ]};
 const core=coreDashboard(data);
 assert.equal(core.stations.length,2);assert.equal(core.map_stations.length,1);
 assert.equal(core.stations[0].totals.charger_count,null);
 assert.equal(filterStations(core.stations,{district:'강남구'}).length,1);
 assert.equal(searchStations(core.stations,'나').length,0);
 assert.equal(coreDashboard({items:[]}).map_stations.length,0);
});

test('Seoul operating observations remain visible with classification false and zero D1 confirmations',()=>{
 const row=(statId,extra={})=>({statId,chgerId:'1',statNm:statId,addr:'서울특별시 강남구 실제주소 형식 테스트',lat:'37.5',lng:'127',delYn:'N',output:'100',stat:'9',chgerType:'UNREVIEWED_CODE',...extra});
 const data={classification_verified:false,items:[],unclassified_items:[row('SEOUL'),row('OUTSIDE',{addr:'경기도 성남시'}),row('DELETED',{delYn:'Y'}),row('BAD_COORDS',{lat:''}),row('SEOUL',{chgerId:'2',output:'50'})]};
 const result=seoulOperationsDashboard(data);
 assert.equal(result.displayedChargerCount,2);assert.equal(result.displayedStationCount,1);
 assert.equal(result.stations[0].district,'강남구');assert.equal(result.stations[0].chargers[0].stat,'9');
 assert.equal(result.stations[0].chargers[0].display_status,'UNKNOWN');
 assert.equal(result.stations[0].totals.normal_kw,null);assert.equal(result.stations[0].totals.total_kw,150);
 assert.equal(result.scope,'seoul_raw_unclassified');assert.equal(result.classification_verified,false);
 assert.equal(coreDashboard({items:[],total:0}).stations.length,0);
 assert.equal(result.stations.length,1);
});

test('verified rapid operating scope relies on backend approval, not power or guessed codes',()=>{
 const row=(statId,extra={})=>({statId,chgerId:'1',addr:'서울특별시 종로구 테스트',lat:'37.57',lng:'126.98',delYn:'N',output:'200',...extra});
 const result=seoulOperationsDashboard({classification_verified:true,items:[row('KNOWN_FAST',{analysis_eligible:true,status:'AVAILABLE'}),row('UNKNOWN_TYPE',{analysis_eligible:false})]});
 assert.equal(result.displayedChargerCount,1);assert.equal(result.stations[0].statId,'KNOWN_FAST');
 assert.equal(result.stations[0].totals.normal_count,1);assert.equal(result.scope,'seoul_verified_fast');
});

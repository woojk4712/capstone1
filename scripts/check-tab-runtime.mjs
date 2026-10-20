// End-to-end tests against actual localhost responses, no dataset mocks.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {spawn} from 'node:child_process';
let pw;try{pw=await import('playwright');}catch{pw=await import(pathToFileURL(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs')).href);}
const base=process.env.APP_URL || 'http://127.0.0.1:8000';
const browser=await pw.chromium.launch({channel:'chrome',headless:true});
const page=await browser.newPage({viewport:{width:1600,height:1100}});
page.setDefaultTimeout(90000);
const errors=[],apiResponses=[];
page.on('pageerror',e=>errors.push(e.message));
page.on('response',r=>{if(r.url().startsWith(base+'/api/'))apiResponses.push({path:new URL(r.url()).pathname,status:r.status()});});
// Isolate third-party tile availability; no local API requests are intercepted.
await page.route('https://tile.openstreetmap.org/**',r=>r.abort());
let stage='load';
const result={base,errors,checks:{},tabs:{}};
const tab=async name=>{await page.locator(`.tabs [data-tab="${name}"]`).click();assert.equal(await page.locator('#notice').isVisible(),false);};
const waitRank=()=>page.locator('.research-rank-panel').waitFor();
const waitSim=()=>page.locator('[data-sim="recoveredKw"]').waitFor();
try{
 const get=async path=>{const r=await page.request.get(base+path,{timeout:120000});assert.equal(r.status(),200);return r.json();};
 const status=await get('/api/system/status');
 const quality=await get('/api/analysis/quality');
 const replay=status.stale===true;
 const overview=await get('/api/analysis/overview?replay='+replay);
 const ops=await get('/api/operations/stations?stopped_only=true');
 result.observationAt=status.last_me_success_at;result.stale=status.stale;
 result.counts={confirmed:quality.matching.confirmed,review:quality.matching.review,
  recovery:overview.priorities.length,potential:overview.potential.length,maintenance:quality.maintenanceReadyFacilities,
  hypotheticalChargers:overview.potential.filter(r=>['AVAILABLE','CHARGING'].includes(r.status)).length,
  simpleStations:ops.total,simpleChargers:ops.items.flatMap(s=>s.chargers).filter(c=>c.status==='STOPPED'&&c.output_kw>0).length};
 await page.goto(base+'/',{waitUntil:'domcontentloaded',timeout:120000});
 await page.waitForFunction(()=>Number(document.querySelector('#map')?.dataset.markerCount)>0,null,{timeout:180000});
 const operationCount=Number(await page.locator('#map').getAttribute('data-marker-count'));
 assert(Number(await page.locator('[data-kpi="facility_count"]').innerText().then(t=>t.replace(/[^\d]/g,'')))>0);
 await page.locator('#district').selectOption('강남구');
 const gangnamCount=Number(await page.locator('#map').getAttribute('data-marker-count'));assert(gangnamCount>0&&gangnamCount<operationCount);
 await page.locator('#status').selectOption('STOPPED');
 const markers=page.locator('#map [data-map-station]');assert(await markers.count()>0);
 await markers.first().hover();await page.locator('.leaflet-tooltip').waitFor();
 await markers.first().click();await page.locator('#detail-title').waitFor();
 assert.match(await page.locator('.detail-drawer').innerText(),/statId/);
 await page.locator('button[data-action="close-detail"]').click();
 await page.locator('#status').selectOption('');
 await page.locator('#search').fill('강남');assert(Number(await page.locator('#map').getAttribute('data-marker-count'))<gangnamCount);
 await page.locator('#search').fill('');
 result.tabs.overview={markers:operationCount,seoulChargers:Number(await page.locator('#root').getAttribute('data-seoul-charger-count')),district:true,search:true,hover:true,click:true,kpi:true};
 stage='ranking';console.log('CHECK '+stage);await tab('priorities');await waitRank();
 if(replay){await page.locator('#research-replay').check();await waitRank();}
 assert.equal(await page.locator('tr[data-r-station]').count(),overview.potential.length);
 assert.equal(await page.locator('[data-r-ranking="potential"]').getAttribute('class'),'active');
 assert.match(await page.locator('.research-rank-panel thead').innerText(),/D[\s\S]*Q[\s\S]*B[\s\S]*Impact/);
 await page.locator('tr[data-r-station]').first().click();await page.locator('#research-detail h3').waitFor();
 await page.locator('[data-r-ranking="recovery"]').click();
 if(overview.priorities.length===0)assert.match(await page.locator('#research-body').innerText(),/現在|현재 확인된 핵심 분석시설에는 운영중지 복구 대상이 없습니다/);
 await page.locator('[data-r-ranking="potential"]').click();
 await page.locator('[data-r-radius="1000"]').click();await waitRank();
 await page.locator('#research-weight').selectOption('demand');await waitRank();
 assert.match(await page.locator('#content .chart-note').innerText(),/0.5/);
 const sid=overview.potential[0].statId,station=overview.items.find(s=>s.statId===sid);
 const district=station.addr.match(/서울특별시\s+(\S+구)/)?.[1];
 if(district){await page.locator('#research-district').selectOption(district);assert(await page.locator('tr[data-r-station]').count()>0);}
 await page.locator('#research-search').fill(station.statNm);
 await page.waitForFunction(name=>{const rows=[...document.querySelectorAll('tr[data-r-station]')];return rows.length>0&&rows.every(r=>r.textContent.includes(name));},station.statNm);
 result.tabs.priorities={potential:overview.potential.length,recovery:overview.priorities.length,rowClick:true,weights:true,radius:true,district:true,search:true};
 stage='maintenance';console.log('CHECK '+stage);await tab('maintenance');await page.locator('.heatmap').waitFor();
 assert.match(await page.locator('#maintenance-ready-count').innerText(),new RegExp(String(quality.maintenanceReadyFacilities)));
 assert.equal(await page.locator('#research-facility option[value]:not([value=""])').count(),quality.maintenanceReadyFacilities);
 assert.equal(await page.locator('.research-candidate').count(),2);
 const facilityOptions=await page.locator('#research-facility').evaluate(s=>[...s.options].filter(o=>o.value).map(o=>o.value));
 await page.locator('#research-facility').selectOption(facilityOptions[1]);await page.locator('.heatmap').waitFor();
 assert.equal(await page.locator('.research-candidate div').count(),6);
 result.tabs.maintenance={facilities:facilityOptions.length,heatmap:true,oneHour:true,twoHour:true,selection:true};
 stage='simulation';console.log('CHECK '+stage);await tab('simulation');await waitRank();
 if(replay){await page.locator('#research-replay').check();await waitRank();}
 if(!overview.priorities.length)assert.match(await page.locator('#content').innerText(),/実際|実|현재 핵심 분석시설에는 실제 운영중지 복구 대상이 없습니다/);
 await page.locator('[data-r-mode="hypothetical"]').click();await waitSim();
 const simFacility=await page.locator('#research-facility').inputValue();
 const simStation=overview.items.find(s=>s.statId===simFacility);
 const simDistrict=simStation.addr.match(/서울특별시\s+(\S+구)/)?.[1];
 await page.locator('#research-district').selectOption(simDistrict);await waitSim();
 await page.locator('#research-search').fill(simStation.statNm);
 await page.waitForFunction(()=>document.querySelectorAll('#research-facility option[value]:not([value=""])').length===1);await waitSim();
 await page.locator('[data-r-select]').first().check();
 await page.waitForFunction(()=>{const s=document.querySelector('[data-sim="recoveredKw"]');return s&&parseFloat(s.textContent.replaceAll(',',''))>0;});
 const recovered=await page.locator('[data-sim="recoveredKw"]').innerText();
 const before=await page.locator('[data-sim="normalKw"]').innerText();
 await page.locator('[data-r-view="true"]').click();await waitSim();
 assert.notEqual(await page.locator('[data-sim="normalKw"]').innerText(),before);
 assert.equal(await page.locator('#research-map').getAttribute('data-recovered-count'),'1');
 assert(await page.locator('.research-cumulative').isVisible());
 await page.locator('[data-r-view="false"]').click();await waitSim();assert.equal(await page.locator('[data-sim="normalKw"]').innerText(),before);
 await page.locator('[data-r-mode="simple"]').click();await waitRank();
 // Filters remain local to the simulation, reset explicitly for the new source.
 await page.locator('#research-search').fill('');await page.locator('#research-district').selectOption('');await waitSim();
 assert(await page.locator('[data-r-select]').count()>0);
 const simpleId=await page.locator('#research-facility').inputValue();
 const simpleStation=ops.items.find(s=>s.statId===simpleId);
 await page.locator('#research-search').fill(simpleStation.statNm);
 await page.waitForFunction(()=>document.querySelectorAll('#research-facility option[value]:not([value=""])').length===1);await waitSim();
 await page.locator('[data-r-select]').first().check();
 await page.waitForFunction(()=>parseFloat(document.querySelector('[data-sim="recoveredKw"]')?.textContent.replaceAll(',',''))>0);
 await page.locator('[data-r-view="true"]').click();await waitSim();
 assert.match(await page.locator('#content').innerText(),/D1 利用|D1 이용량 미연결 시설은 고장 영향도 순위 대상이 아님/);
 assert.equal(await page.locator('.research-rank-panel thead').innerText().then(t=>t.includes('Impact')),false);
 result.tabs.simulation={hypothetical:true,simple:true,actualEmpty:overview.priorities.length===0,recovered,beforeAfter:true,mapAfter:true,curve:true,district:true,search:true};
 await page.screenshot({path:'reports/tab-runtime-simulation.png',fullPage:true});
 stage='quality';console.log('CHECK '+stage);await page.locator('.tabs [data-tab="quality"]').click();await page.locator('#research-review-filter').waitFor();
 assert(await page.locator('#notice').isVisible());result.tabs.quality={matching:quality.matching,visible:true};
 await page.locator('#analysis-funnel').waitFor();result.tabs.quality.funnel=true;
 if(process.env.CHECK_REVISION==='1'){
   await page.waitForFunction(()=>Boolean(document.querySelector('#content')?.dataset.analysisRevision));
   const previous=await page.locator('#content').getAttribute('data-analysis-revision');
   await new Promise((resolve,reject)=>{const child=spawn(path.resolve('.venv/Scripts/python.exe'),['scripts/prepare_analysis.py','--all'],{stdio:'ignore',windowsHide:true});child.on('error',reject);child.on('exit',code=>code===0?resolve():reject(new Error('Actual source prepare failed')));});
   await page.waitForFunction(previous=>document.querySelector('#content')?.dataset.analysisRevision!==previous,previous,{timeout:60000});
   await page.locator('#analysis-funnel').waitFor();
   result.checks.analysisRevisionRefresh=true;
 }
 stage='reload';console.log('CHECK '+stage);await page.reload({waitUntil:'domcontentloaded'});await page.waitForFunction(()=>Number(document.querySelector('#map')?.dataset.markerCount)>0,null,{timeout:180000});
 const asset=await page.request.get(base+'/apps/web/src/research-tabs.js');assert.equal(asset.headers()['cache-control'],'no-store');
 result.checks.ordinaryReload=true;result.checks.cacheNoStore=true;
 // A failed core API must not prevent real operational inventory rendering.
 await page.route(base+'/api/analysis/stations',route=>route.abort());
 await page.reload({waitUntil:'domcontentloaded'});
 await page.waitForFunction(()=>Number(document.querySelector('#map')?.dataset.markerCount)>0,null,{timeout:180000});
 result.checks.coreFailureDoesNotBlockOperations=true;
 assert.deepEqual(errors,[]);result.apiResponses=apiResponses;
 await fs.writeFile('reports/tab-runtime-verification.json',JSON.stringify(result,null,2));
 console.log(JSON.stringify({...result,apiResponses:undefined}));
}catch(e){await page.screenshot({path:'reports/tab-runtime-failure.png',fullPage:true}).catch(()=>{});console.log(JSON.stringify({stage,error:e.name,message:e.message.slice(0,500),errors}));process.exitCode=1;}
finally{await browser.close();}

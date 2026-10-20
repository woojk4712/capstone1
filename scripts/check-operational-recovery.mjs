// Real rendered Chrome and local APIs; no injected data or API mocks.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
let pw;try{pw=await import('playwright');}catch{pw=await import(pathToFileURL(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs')).href);}
const base=process.env.APP_URL||'http://127.0.0.1:8000';
const browser=await pw.chromium.launch({channel:'chrome',headless:true});
const page=await browser.newPage({viewport:{width:1700,height:1100}});page.setDefaultTimeout(90000);
const errors=[],responses=[],result={base,checks:{}};let stage='load';
page.on('pageerror',e=>errors.push(e.message));
page.on('response',r=>{if(r.url().startsWith(base+'/api/'))responses.push({path:new URL(r.url()).pathname,status:r.status()});});
const get=async url=>{const r=await page.request.get(base+url,{timeout:120000});assert.equal(r.status(),200,url);return r.json();};
const rows=()=>page.locator('tr[data-r-station]');
const ready=()=>page.locator('#recovery-table table').waitFor();
const sim=()=>page.locator('[data-sim="recoveredKw"]').waitFor();
const tab=async name=>{await page.locator(`.tabs [data-tab="${name}"]`).click();};
try{
 const op=await get('/api/operations/recovery');result.observationAt=op.observationAt;result.diagnostics=op.diagnostics;result.stale=op.stale;
 const stations=await get('/api/operations/stations?stopped_only=true&observationAt='+encodeURIComponent(op.observationAt));
 assert.equal(stations.stoppedChargerCount,op.count);assert.equal(stations.total,op.stationCount);
 result.counts={stopped:op.count,facilities:op.stationCount,selectable:op.selectableCount};
 await page.goto(base+'/',{waitUntil:'domcontentloaded',timeout:120000});
 await page.waitForFunction(()=>Number(document.querySelector('#map')?.dataset.markerCount)>0,null,{timeout:180000});
 result.checks.operations=true;
 await tab('priorities');await ready();
 if(op.stale){await page.locator('[data-r-observed]').click();await ready();}
 assert.equal(await rows().count(),op.count);assert.equal(await page.locator('[data-r-ranking="operational"]').getAttribute('aria-pressed'),'true');
 await page.locator('#research-search').click();assert.equal(await page.locator('[data-r-search]').count(),op.stationCount);
 await page.locator('[data-r-search]').first().click();await page.locator('#research-detail h3').waitFor();
 assert(await rows().count()>0);assert(await rows().count()<op.count);
 await page.locator('#research-search').fill('');await page.waitForFunction(n=>document.querySelectorAll('tr[data-r-station]').length===n,op.count);
 const district=op.stations[0].addr.match(/서울특별시\s+(\S+구)/)?.[1];
 if(district){await page.locator('#research-district').selectOption(district);assert(await rows().count()>0);await page.locator('#research-district').selectOption('');}
 await page.locator('[data-r-radius="1000"]').click();await ready();assert.equal(await rows().count(),op.count);
 await page.locator('[data-r-radius="500"]').click();await ready();
 result.checks.operationalRanking={rows:op.count,autocomplete:true,district:true,radius:true};
 await page.screenshot({path:'reports/operational-ranking.png',fullPage:true});
 stage='rank to simulation';console.log(stage);
 await page.locator('[data-r-simulate]:not([disabled])').first().click();await sim();
 assert.equal(await page.locator('[data-r-mode="real"]').getAttribute('aria-pressed'),'true');
 const metric=async k=>Number((await page.locator(`[data-sim="${k}"]`).innerText()).replace(/[^\d.\-]/g,''));
 const before=await metric('normalKw'),stopped=await metric('stoppedKw'),delta=await metric('recoveredKw');assert(delta>0);
 await page.locator('[data-r-view="true"]').click();await sim();assert.equal(await metric('normalKw'),before+delta);assert.equal(await metric('stoppedKw'),stopped-delta);
 assert(await page.locator('[data-virtual-restored]').count()>0);
 assert.equal(await page.locator('#research-map').getAttribute('data-scenario'),'after');
 await page.locator('[data-r-view="false"]').click();await sim();assert.equal(await metric('normalKw'),before);
 result.checks.singleBeforeAfter=true;result.checks.rankToSimulation=true;
 stage='bulk';console.log(stage);
 for(const n of [1,3,5,10]){
  await page.locator(`[data-r-top="${n}"]`).click();await sim();
  const expected=op.items.filter(r=>r.selectable).slice(0,n).reduce((a,r)=>a+r.power_kw,0);
  assert.equal(await metric('recoveredKw'),expected);
  await page.locator('[data-r-view="true"]').click();await sim();assert.equal(await metric('normalKw'),before+expected);
 }
 assert.equal(Number(await page.locator('#research-map').getAttribute('data-marker-count')),op.stationCount);
 assert(await page.locator('#research-curve svg').count());result.checks.bulkAndCurve=true;
 await page.screenshot({path:'reports/operational-simulation.png',fullPage:true});
 await page.locator('[data-r-clear]').click();await sim();
 await page.locator('#research-search').click();assert.equal(await page.locator('[data-r-search]').count(),op.stationCount);
 await page.locator('[data-r-search]').first().click();await sim();
 await page.locator('[data-r-add]:not([disabled])').first().click();await sim();assert(await metric('recoveredKw')>0);
 await page.locator('#research-search').fill('');await page.waitForFunction(n=>Number(document.querySelector('#research-map')?.dataset.markerCount)===n,op.stationCount);
 await page.locator('#research-search').press('Escape');
 await page.locator('#research-map .highlighted-marker').hover();await page.locator('.leaflet-tooltip').waitFor();
 await page.locator('#research-map .highlighted-marker').click();await page.locator('#research-detail h3').waitFor();
 result.checks.simulationSearchMarkerAdd=true;
 stage='potential';console.log(stage);await tab('priorities');await ready();await page.locator('[data-r-ranking="potential"]').click();await ready();
 const potential=await get('/api/analysis/overview?replay='+op.stale);assert.equal(await rows().count(),potential.potential.length);
 result.counts.potential=potential.potential.length;result.counts.exact=potential.potential.filter(r=>!r.scoreIsUpperBound).length;
 await page.locator('[data-r-exact="true"]').click();assert.equal(await rows().count(),result.counts.exact);
 await page.locator('[data-r-exact="false"]').click();
 await page.locator('#research-weight').selectOption('demand');await ready();assert(await rows().count()>0);
 await page.locator('#research-weight').selectOption('equal');await ready();result.checks.potential=true;
 stage='maintenance';console.log(stage);await tab('maintenance');await page.locator('.heatmap').waitFor();
 const quality=await get('/api/analysis/quality');result.counts.confirmed=quality.matching.confirmed;result.counts.review=quality.matching.review;result.counts.maintenance=quality.maintenanceReadyFacilities;
 assert.equal(await page.locator('#research-facility option[value]:not([value=""])').count(),quality.maintenanceReadyFacilities);assert.equal(await page.locator('.research-candidate').count(),2);result.checks.maintenance=true;
 await tab('simulation');await ready();await page.locator('[data-r-mode="hypothetical"]').click();await sim();
 if(potential.potential.some(r=>['AVAILABLE','CHARGING'].includes(r.status))){await page.locator('[data-r-select]:not([disabled])').first().check();await sim();assert(await metric('recoveredKw')>0);}result.checks.hypothetical=true;
 await tab('quality');await page.locator('#analysis-funnel').waitFor();result.checks.quality=true;
 assert.deepEqual(errors,[]);assert(!responses.some(r=>r.status>=400));
 result.passed=true;
}catch(e){result.passed=false;result.failure={stage,message:e.message};console.error(stage,e.message);process.exitCode=1;}
finally{result.errors=errors;result.responses=responses;await page.screenshot({path:'reports/operational-recovery-browser.png',fullPage:true});await fs.writeFile('reports/operational-recovery-browser.json',JSON.stringify(result,null,2));console.log(JSON.stringify({...result,responses:undefined},null,2));await browser.close();}

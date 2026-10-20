import assert from 'node:assert/strict';import fs from 'node:fs/promises';import path from 'node:path';import os from 'node:os';import {pathToFileURL} from 'node:url';
let pw;try{pw=await import('playwright');}catch{pw=await import(pathToFileURL(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs')).href);}
const browser=await pw.chromium.launch({channel:'chrome',headless:true});const page=await browser.newPage({viewport:{width:1440,height:1100}});let verified=false,overview=0;const errors=[];page.on('pageerror',()=>errors.push('runtime_error'));
const raw=[{statId:'TEST_CORE_A',chgerId:'1',statNm:'\uac00 \uc2dc\uc124',addr:'\uc11c\uc6b8\ud2b9\ubcc4\uc2dc \uac15\ub0a8\uad6c \ud14c\uc2a4\ud2b8',lat:'37.5',lng:'127',output_kw:100,status:'AVAILABLE',delYn:'N',analysis_eligible:true},
{statId:'TEST_CORE_B',chgerId:'1',statNm:'\ub098 \uc2dc\uc124',addr:'\uc11c\uc6b8\ud2b9\ubcc4\uc2dc \uc885\ub85c\uad6c \ud14c\uc2a4\ud2b8',lat:'37.57',lng:'126.98',output_kw:100,status:'AVAILABLE',delYn:'N',analysis_eligible:true},
{statId:'TEST_RAW_ONLY',chgerId:'1',statNm:'Seoul operational-only fixture',addr:'\uc11c\uc6b8\ud2b9\ubcc4\uc2dc \uac15\ub3d9\uad6c',lat:'37.55',lng:'127.1',output_kw:100,delYn:'N',analysis_eligible:true}];
await page.route('https://**',r=>r.abort());
await page.route('**/api/system/status',r=>r.fulfill({json:{providers:{ME:{connected:true,current_error:null,count:3}},stored_charger_count:3,classification_verified:verified}}));
await page.route('**/api/chargers',r=>r.fulfill({json:{items:verified?raw:[],unclassified_items:verified?[]:raw,classification_verified:verified,inventory_count:3}}));
await page.route('**/api/analysis/stations',r=>r.fulfill({json:{items:raw.slice(0,2).map(c=>({analysisStationId:'ME:'+c.statId,statId:c.statId,statNm:c.statNm,addr:c.addr,lat:c.lat,lng:c.lng,matchStatus:'confirmed',annualFastKwh2025:1000,monthlyFastKwh2025:[1000,...Array(11).fill(null)],chargerCount:verified?1:null,chargers:[c]})),total:2,d1Available:true,stationMatchingReady:true,analysisDatasetReady:true,classificationVerified:verified,matching:{confirmed:2,review:1,unmatched:0},d1:{available:true},last_success_at:new Date().toISOString()}}));
await page.route('**/api/analysis/stations/*/alternatives?*',r=>r.fulfill({json:{items:[],total:0,totalRatedOutputKw:null,status:'classification_required',message:'\uBD84\uB958 \uAC80\uC99D \uD544\uC694'}}));
await page.route('**/api/v1/overview?*',r=>{overview++;return r.fulfill({status:503,json:{detail:'Analysis not ready - fixture only'}});});
try{
 await page.goto('http://127.0.0.1:8000/');await page.waitForFunction(()=>document.querySelectorAll('[data-map-station]').length===3);
 assert.equal(await page.locator('[data-map-station="ME:TEST_RAW_ONLY"]').count(),1);
 assert.match(await page.locator('#api-connection').innerText(),/\uc5f0\uacb0\ub428/);assert.match(await page.locator('#data-connection').innerText(),/\uc5f0\uacb0\ub428/);
 assert.match(await page.locator('#classification-status').innerText(),/\ucf54\ub4dc/);
 await page.locator('#district').selectOption('\uac15\ub0a8\uad6c');assert.equal(await page.locator('[data-map-station]').count(),1);assert.match(await page.locator('[data-kpi="facility_count"]').innerText(),/1/);
 await page.locator('[data-action="filters-reset"]').click();await page.locator('#search').click();assert.equal(await page.locator('#station-options [role="option"]').count(),3);
 assert(!(await page.locator('#station-options').innerText()).includes('National'));
 await page.locator('#station-options [role="option"]').first().click();await page.locator('#detail-title').waitFor();await page.keyboard.press('Escape');
 verified=true;await page.locator('[data-action="refresh"]').click();await page.waitForFunction(()=>document.querySelector('#root').dataset.classificationVerified==='true');
 await page.locator('.tabs [data-tab="priorities"]').click();assert.equal(overview,1);
 assert.match(await page.locator('#api-connection').innerText(),/\uc5f0\uacb0\ub428/);assert.match(await page.locator('#data-connection').innerText(),/\uc5f0\uacb0\ub428/);
 assert(!(await page.locator('body').innerText()).includes('\ubbf8\uc5f0\uacb0'));assert.deepEqual(errors,[]);
 const result={scope:'isolated browser-only fixtures, never production DB or matching confirmations',passed:true,checks:['Seoul operational map independent of D1','Seoul operational search','district KPI/marker filter','classification independent','overview failure independent','no mock fallback in live mode'],errors};
 console.log(JSON.stringify(result));await fs.writeFile('reports/core-scope-ui-tests.json',JSON.stringify(result,null,2));
}finally{await browser.close();}

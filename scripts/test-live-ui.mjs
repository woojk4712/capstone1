// Isolated browser fixtures never reach the backend database or production UI.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {pathToFileURL} from 'node:url';
let playwright;try{playwright=await import('playwright');}catch{playwright=await import(pathToFileURL(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs')).href);}
const browser=await playwright.chromium.launch({channel:'chrome',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const results=[],errors=[];page.on('pageerror',()=>errors.push('browser_runtime_error'));
const base=process.env.DASHBOARD_URL||'http://127.0.0.1:8000/live';
let leafletSource=null;
try{leafletSource=await fs.readFile(new URL(import.meta.resolve('leaflet/dist/leaflet.js')),'utf8');}catch{try{leafletSource=await fs.readFile('apps/web/vendor/leaflet.js','utf8');}catch{}}
const check=async(name,fn)=>{try{await fn();results.push({name,status:'passed'});console.log('PASS',name);}catch{results.push({name,status:'failed'});console.log('FAIL',name);}};
// Abort third-party requests for deterministic error UI tests. This does not fake Leaflet.
await page.route('https://**',route=>route.abort());
if(leafletSource)await page.route('https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',route=>route.fulfill({contentType:'application/javascript',body:leafletSource}));
try{
 await page.goto(base,{waitUntil:'domcontentloaded'});
 await check('actual_backend_error_ui',async()=>{await page.locator('.live-notice.error').waitFor();assert.match(await page.locator('#live-notice').innerText(),/API 연결 실패/);assert.match(await page.locator('#live-stations').innerText(),/데이터 미수집/);assert.equal(await page.locator('[data-live-station]').count(),0);await page.screenshot({path:'reports/live-api-error.png',fullPage:true});});
 await check('no_environment_values_in_backend_response',async()=>{const response=await page.request.get(new URL('/api/system/status',base).href);assert.equal(response.status(),200);const data=await response.json();assert(Object.values(data.environment).every(v=>typeof v==='boolean'));assert.equal(data.providers.ME.last_success_at,null);const chargers=await page.request.get(new URL('/api/chargers',base).href);assert.equal(chargers.status(),503);});
 if(!leafletSource)await check('leaflet_unavailable_message',async()=>assert.match(await page.locator('#live-map').innerText(),/Leaflet 지도 라이브러리 연결 실패/));
 // Fixture-only browser responses exercise click/detail/radius without claiming live API success.
 const collected=new Date().toISOString();const fixture={statId:'TEST_ONLY',chgerId:'01',statNm:'브라우저 테스트 전용 충전소',addr:'테스트 주소',latitude:37.5665,longitude:126.978,output_kw:100,status:'AVAILABLE',collected_at:collected,useTime:'테스트 이용시간',statUpdDt:'20260101120000',analysis_eligible:true};
 const state={connected:true,last_success_at:collected,count:1,error:null};
 await page.route('**/api/system/status',route=>route.fulfill({json:{runtime:'test_fixture_only',providers:{ME:state,KEPCO:state},network:{reachable:true},stale:false,classification_verified:true}}));
 await page.route('**/api/chargers',route=>route.fulfill({json:{items:[fixture],unclassified_items:[],total:1,classification_verified:true,stale:false}}));
 await page.route('**/api/chargers/TEST_ONLY',route=>route.fulfill({json:{chargers:[fixture],cross_validation:[],cross_validation_status:'검증된 대응표 없음',stale:false}}));
 await page.route('**/api/chargers/TEST_ONLY/alternatives?*',route=>route.fulfill({json:{items:[],stale:false}}));
 await page.locator('#live-refresh').click();
 await check('fixture_station_click_and_detail',async()=>{await page.locator('[data-station="TEST_ONLY"]').click();await page.waitForFunction(()=>document.querySelector('#live-detail')?.textContent.includes('테스트 이용시간'));assert.match(await page.locator('#live-detail').innerText(),/이용가능/);assert.match(await page.locator('#live-detail').innerText(),/상태 변경시각/);assert.match(await page.locator('#live-detail').innerText(),/수집시각/);});
 await check('fixture_alternatives_radius_request',async()=>{const response=page.waitForResponse(r=>r.url().endsWith('/alternatives?radius=1000'));await page.locator('[data-radius="1000"]').click();assert.equal((await response).status(),200);});
 if(leafletSource)await check('real_leaflet_fixture_marker_hover_click',async()=>{const marker=page.locator('[data-live-station="TEST_ONLY"]');await marker.hover();await page.locator('.leaflet-tooltip').waitFor();assert.equal(await page.locator('.leaflet-tooltip').innerText(),fixture.statNm);await marker.click();await page.waitForFunction(()=>document.querySelector('#live-detail')?.textContent.includes('테스트 이용시간'));});
 else results.push({name:'real_leaflet_marker_hover_click',status:'blocked',reason:'Leaflet package/CDN unavailable; no substitute library used'});
 await check('mobile_layout',async()=>{await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.body.scrollWidth<=window.innerWidth));});
 await check('browser_runtime_errors',async()=>assert.deepEqual(errors,[]));
}finally{await fs.writeFile('reports/live-ui-verification.json',JSON.stringify({scope:'real disconnected backend + browser-only fixtures; no fixture persistence',results},null,2));await browser.close();}
if(results.some(r=>r.status==='failed'))process.exitCode=1;

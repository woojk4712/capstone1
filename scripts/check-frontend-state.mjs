import assert from 'node:assert/strict';import fs from 'node:fs/promises';import path from 'node:path';import os from 'node:os';import {pathToFileURL} from 'node:url';
let pw;try{pw=await import('playwright');}catch{pw=await import(pathToFileURL(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs')).href);}
const browser=await pw.chromium.launch({channel:'chrome',headless:true});const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',()=>errors.push('runtime_error'));
let connected=true,overviewCalls=0;
const items=[{statId:'TEST_ONLY_A',chgerId:'1',statNm:'Browser fixture A',addr:'Fixture address',lat:'37.56',lng:'126.98',output:'100',stat:'2',chgerType:'UNVERIFIED_TEST_TYPE',statUpdDt:'20260101120000'},
{statId:'TEST_ONLY_B',chgerId:'1',statNm:'Browser fixture B',lat:'37.57',lng:'126.99',output:'50'},
{statId:'TEST_ONLY_BAD',chgerId:'1',statNm:'Invalid coords fixture',lat:'',lng:''}];
await page.route('https://**',r=>r.abort());
await page.route('**/api/system/status',r=>r.fulfill({json:{providers:{ME:{connected,current_error:connected?null:{kind:'timeout'},count:3}},stored_charger_count:3,classification_verified:false}}));
await page.route('**/api/chargers',r=>r.fulfill(connected?{json:{items:[],unclassified_items:items,inventory_count:3,classification_verified:false,last_success_at:new Date().toISOString()}}:{status:503,json:{error_type:'timeout'}}));
await page.route('**/api/v1/overview?*',r=>{overviewCalls++;return r.abort();});
try{
 await page.goto('http://127.0.0.1:8000/');
 await page.waitForFunction(()=>document.querySelector('#data-connection')?.textContent.includes('\uc5f0\uacb0\ub428'));
 assert.equal(await page.locator('#leaflet-map').count(),1);
 assert.equal(await page.locator('[data-map-station]').count(),2);
 assert.match(await page.locator('#classification-status').innerText(),/\uac80\uc99d \ud544\uc694/);
 const marker=page.locator('[data-map-station="ME:TEST_ONLY_A"]');await marker.hover();await page.locator('.leaflet-tooltip').waitFor();assert.equal(await page.locator('.leaflet-tooltip').innerText(),'Browser fixture A');
 await marker.click();assert.equal(await page.locator('#detail-title').innerText(),'Browser fixture A');assert.match(await page.locator('.detail-address').innerText(),/Fixture address/);assert.match(await page.locator('.detail-drawer').innerText(),/20260101120000/);assert.match(await page.locator('.detail-drawer').innerText(),/UNVERIFIED_TEST_TYPE/);
 await page.keyboard.press('Escape');connected=false;await page.locator('[data-action="refresh"]').click();await page.locator('.notice.error').waitFor();assert.equal(await page.locator('[data-map-station]').count(),0);
 connected=true;await page.locator('[data-action="refresh"]').click();await page.waitForFunction(()=>document.querySelectorAll('[data-map-station]').length===2);
 assert.equal(overviewCalls,0);assert.deepEqual(errors,[]);
 console.log('PASS: isolated UI fixture - raw mapping, Leaflet hover/click, classification separation, error clearing and recovery, no legacy overview dependency');
 await fs.writeFile('reports/frontend-ui-regression.json',JSON.stringify({scope:'browser-only injected test responses; not actual API data',passed:true,checks:7},null,2));
}finally{await browser.close();}

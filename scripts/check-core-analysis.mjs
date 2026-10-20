import assert from 'node:assert/strict';import fs from 'node:fs/promises';import path from 'node:path';import os from 'node:os';import {pathToFileURL} from 'node:url';
let pw;try{pw=await import('playwright');}catch{pw=await import(pathToFileURL(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs')).href);}
const browser=await pw.chromium.launch({channel:'chrome',headless:true});const page=await browser.newPage({viewport:{width:1440,height:1100}});const errors=[],http={};
const base=process.env.ANALYSIS_UI_URL||'http://127.0.0.1:8766/';
page.on('pageerror',()=>errors.push('JavaScript runtime error'));
page.on('response',r=>{const p=new URL(r.url()).pathname;if(['/api/system/status','/api/chargers','/api/analysis/stations'].includes(p))http[p]=r.status();});
await page.route('https://tile.openstreetmap.org/**',r=>r.abort());
try{
 await page.goto(base,{waitUntil:'domcontentloaded',timeout:120000});
 await page.waitForFunction(()=>Number(document.querySelector('#root')?.dataset.chargerCount)>0,{},{timeout:240000});
 const response=await page.request.get(new URL('/api/analysis/stations',base).href);assert.equal(response.status(),200);const data=await response.json();
 assert.equal(data.total,0);assert.equal(data.matching.confirmed,0);assert.equal(data.matching.review,187);assert.equal(data.d1.fast_station_names,187);
 assert.match(await page.locator('#api-connection').innerText(),/\uc5f0\uacb0\ub428/);assert.match(await page.locator('#data-connection').innerText(),/\uc5f0\uacb0\ub428/);
 assert.equal(await page.locator('#map').getAttribute('data-marker-count'),'0');
 assert.equal(await page.locator('#district option').count(),26);await page.locator('#district').selectOption('\uac15\ub0a8\uad6c');
 assert.equal(await page.locator('#map').getAttribute('data-marker-count'),'0');
 await page.locator('#search').click();assert.equal(await page.locator('#station-options [role="option"]').count(),0);
 assert(!(await page.locator('body').innerText()).includes('\ubbf8\uc5f0\uacb0'));
 await page.locator('.tabs [data-tab="priorities"]').click();assert.match(await page.locator('#api-connection').innerText(),/\uc5f0\uacb0\ub428/);
 assert.deepEqual(errors,[]);
 const result={base,scope:'actual D1 + live collector SQLite opened read-only; no external requests or mock data',http,storedChargers:data.rawChargerCount,d1Rows:data.d1.rows,d1Names:data.d1.unique_station_names,d1FastNames:data.d1.fast_station_names,matching:data.matching,coreStations:data.total,markers:0,classificationVerified:data.classificationVerified,districtOptions:26,searchOptions:0,errors};
 await page.locator('.tabs [data-tab="overview"]').click();await page.screenshot({path:'reports/core-analysis-live.png',fullPage:false});
 await fs.writeFile('reports/core-analysis-browser.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));
} catch(e){console.log(JSON.stringify({base,error_type:e.name,http,errors}));process.exitCode=1;}
finally{await browser.close();}

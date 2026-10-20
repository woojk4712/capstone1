import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';import os from 'node:os';import {pathToFileURL} from 'node:url';
let pw;try{pw=await import('playwright');}catch{pw=await import(pathToFileURL(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs')).href);}
const browser=await pw.chromium.launch({channel:'chrome',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[],http={};
page.on('pageerror',()=>errors.push('JavaScript runtime error'));
page.on('response',r=>{const url=new URL(r.url());if(['/api/system/status','/api/chargers'].includes(url.pathname))http[url.pathname]=r.status();});
await page.route('https://tile.openstreetmap.org/**',route=>route.abort());
let stage='load';
try{
 await page.goto('http://127.0.0.1:8000/',{waitUntil:'domcontentloaded',timeout:120000});
 await page.waitForFunction(()=>document.querySelector('#data-connection')?.textContent.includes('\uc2e4\uc81c \ucda9\uc804\uae30 \ub370\uc774\ud130 \uc5f0\uacb0\ub428'),{},{timeout:240000});
 const result=await page.evaluate(()=>({status:document.querySelector('#api-connection')?.textContent,chargerCount:document.querySelector('#root')?.dataset.chargerCount,storedCount:document.querySelector('#root')?.dataset.storedChargerCount,classification:document.querySelector('#classification-status')?.textContent,markerCount:document.querySelector('#map')?.dataset.markerCount,domMarkers:document.querySelectorAll('[data-map-station]').length,leaflet:!!document.querySelector('#leaflet-map'),tableRows:document.querySelectorAll('#content tbody tr').length}));
 if(result.leaflet){stage='detail';
  await page.locator('#content .station-link').first().click();
  await page.locator('#detail-title').waitFor();await page.keyboard.press('Escape');
  await page.waitForFunction(()=>Number(document.querySelector('#map').dataset.zoom)===15);
  stage='hover';await page.locator('#leaflet-map').scrollIntoViewIfNeeded();const box=await page.locator('#leaflet-map').boundingBox();
  await page.mouse.move(box.x+box.width/2,box.y+box.height/2);
  await page.locator('.leaflet-tooltip').waitFor({timeout:10000});
  const hoveredName=await page.locator('.leaflet-tooltip').innerText();
  result.hover=hoveredName.length>0;stage='click';
  await page.mouse.click(box.x+box.width/2,box.y+box.height/2);
  await page.locator('#detail-title').waitFor();
  result.click=(await page.locator('#detail-title').innerText())===hoveredName;
  await page.keyboard.press('Escape');
 }
 result.http=http;result.errors=errors;console.log(JSON.stringify(result));
 await fs.writeFile('reports/frontend-live-result.json',JSON.stringify(result,null,2));
 await page.screenshot({path:'reports/frontend-live.png',fullPage:false});
} catch(e){console.log(JSON.stringify({result:'not_completed',stage,error_type:e.name,http,errors}));}
finally{await browser.close();}

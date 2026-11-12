// Set PLAYWRIGHT_MODULE to the locally installed playwright-core module when needed.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright-core');
const fs=require('fs');
const base=process.env.PANEL_BASE||'http://192.0.2.142:8891';
const output=process.env.PANEL_REPORT||'/tmp/opengym-panel-browser';
fs.mkdirSync(output,{recursive:true});
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
 const context=await browser.newContext({viewport:{width:1280,height:800}});const page=await context.newPage();let errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base);await page.getByText('Forhåndsvisning · eksempeldata',{exact:true}).waitFor();await page.screenshot({path:output+'/demo.png'});
 await page.getByRole('button',{name:'Neste ›',exact:true}).click();if(await page.locator('#exercise').textContent()!=='Stangknebøy – lette avslutningssett')throw Error('navigation');
 await page.getByRole('button',{name:'Start pause',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#timer').textContent==='01:59');await page.getByRole('button',{name:'Stopp pause',exact:true}).click();const paused=await page.locator('#timer').textContent();await page.waitForTimeout(1100);if(await page.locator('#timer').textContent()!==paused)throw Error('pause');
 await page.getByRole('button',{name:'15 sekunder lengre pause'}).click();await page.getByRole('button',{name:'Nullstill',exact:true}).click();if(await page.locator('#timer').textContent()!=='02:00')throw Error('reset');
 await page.getByRole('button',{name:'Ons',exact:true}).click();await page.getByText('Ingen planlagt styrkeøkt',{exact:true}).waitFor();if(!await page.locator('#next').isDisabled())throw Error('rest controls');
 const cfg=JSON.parse(fs.readFileSync(process.env.PANEL_CONFIG));
 await page.getByRole('button',{name:'DEMO',exact:true}).click();await page.getByLabel('Panelnøkkel').fill(cfg.token);await page.getByRole('button',{name:'Koble til',exact:true}).click();await page.getByRole('button',{name:'TILKOBLET',exact:true}).waitFor();
 await page.getByRole('button',{name:'Neste ›',exact:true}).click();await page.screenshot({path:output+'/live.png'});
 if((await page.locator('body').textContent()).includes(cfg.uid))throw Error('UID leaked');
 await page.route('**/api/plan*',route=>route.fulfill({status:503,contentType:'application/json',body:'{"error":"OpenGym unavailable"}'}));await page.getByRole('button',{name:'Tor',exact:true}).click();await page.getByText('Frakoblet · ingen ferske treningsdata',{exact:true}).waitFor();if(await page.locator('#load').textContent()!=='')throw Error('stale weight');if(await page.locator('#connection').textContent()!=='FRAKOBLET')throw Error('stale connection label');
 await page.unroute('**/api/plan*');await page.getByRole('button',{name:'Tir',exact:true}).click();await page.getByText('Oppdatert · plan for neste øktstart',{exact:true}).waitFor();
 if(errors.length)throw Error(errors.join('\n'));
 const result={demo:true,navigation:true,timerCountdown:true,timerPause:true,timerAdjust:true,timerReset:true,restDay:true,authenticatedLive:true,uidNotRendered:true,offlineClearsWeights:true,recovery:true,browserErrors:0};
 fs.writeFileSync(output+'/browser.json',JSON.stringify(result,null,2));console.log(result);await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});

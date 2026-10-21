/* Run against a local server. Requires Playwright and Chromium; no remote site access. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 try{
 const {inspectPage}=require('../scripts/inspect_posting.cjs');
 const fixture=await browser.newPage();
 for(const [name,result,id] of [['apply-enabled','apply_enabled','55251835'],['apply-closed','closed','55166027']]){await fixture.setContent(require('fs').readFileSync(require('path').join(__dirname,'fixtures',name+'.html'),'utf8'));assert.equal((await inspectPage(fixture,id)).result,result);}
 await fixture.setContent('<button class="sri_btn_immediately" disabled>입사지원</button>');assert.equal((await inspectPage(fixture)).result,'unknown');
 await fixture.setContent('<button class="sri_btn_immediately" style="display:none">입사지원</button>');assert.equal((await inspectPage(fixture)).result,'unknown');
 await fixture.setContent('<button class="sri_btn_immediately" aria-disabled="true">입사지원</button>');assert.equal((await inspectPage(fixture)).result,'unknown');
 await fixture.setContent('<button class="sri_btn_immediately" onclick="quickApplyMobile(\'99999999\')">입사지원</button>');assert.equal((await inspectPage(fixture,'55251835')).result,'unknown');
 await fixture.close();
 const page=await browser.newPage({viewport:{width:1280,height:900}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
 const base=process.env.GYUL_TEST_URL||'http://127.0.0.1:8001';
 await page.goto(base);await page.locator('.card').first().waitFor();
 assert.equal(await page.locator('#sort').inputValue(),'recommended');
 const first=page.locator('.card').first();const company=await first.locator('.company').innerText();
 await first.locator('[data-action="favorite"]').click();
 await page.locator('[data-view="favorites"]').click();assert.equal(await page.locator('.card').count(),1);assert.equal(await page.locator('.company').innerText(),company);
 await page.reload();await page.locator('.card').first().waitFor();await page.locator('[data-view="favorites"]').click();assert.equal(await page.locator('.card').count(),1);
 await page.locator('[data-action="applied"]').click();await page.locator('[data-view="applied"]').click();assert.equal(await page.locator('.card').count(),1);
 await page.locator('[data-action="hide"]').click();assert.equal(await page.locator('.card').count(),0);
 await page.locator('[data-view="hidden"]').click();assert.equal(await page.locator('.card').count(),1);await page.locator('[data-action="hide"]').click();assert.equal(await page.locator('.card').count(),0);
 await page.locator('[data-view="all"]').click();
 await page.locator('#search').fill('존재하지않는회사테스트1234');assert.equal(await page.locator('.card').count(),0);await page.locator('#search').fill('');
 for(const sort of ['salary','size','distance','transit','recommended']){await page.locator('#sort').selectOption(sort);assert.ok(await page.locator('.card').count()>0);}
 await page.locator('#role').selectOption({index:1});assert.ok(await page.locator('.card').count()>0);await page.locator('#role').selectOption('');
 await page.locator('#reviewForm').evaluate(e=>e.closest('details').open=true);
 await page.locator('[name="url"]').fill('https://m.saramin.co.kr/job-search/view?rec_idx=55251835');
 await page.locator('[name="observed"]').fill('2026-10-21T11:17');
 await page.locator('[name="company"]').fill('리나소프트');await page.locator('[name="title"]').fill('웹/앱 디자이너');
 await page.locator('[name="result"]').selectOption('apply_enabled');await page.locator('[name="evidence"]').fill('사용자 화면의 빨간 입사지원 버튼 확인');
 await page.locator('#reviewForm button[type="submit"]').click();
 const payload=JSON.parse(await page.locator('#reviewOutput').inputValue());assert.equal(payload.jobs[0].application_button_state,'apply_enabled');assert.equal(payload.observations[0].observed_at,'2026-10-21T11:17:00+09:00');
 require('fs').writeFileSync('/tmp/gyul-browser-review-batch.json',JSON.stringify(payload));
 await page.setViewportSize({width:390,height:844});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
 await page.screenshot({path:'/tmp/gyul-mobile-after.png',fullPage:false});
 await page.setViewportSize({width:1280,height:900});await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:'/tmp/gyul-desktop-after.png',fullPage:false});
 // Malformed preferences recover without an exception.
 await page.evaluate(()=>localStorage.setItem('gyul-radar-preferences-v3',JSON.stringify({favorites:'bad',hidden:null})));
 await page.reload();await page.locator('.card').first().waitFor();
 // Data failure is explicit and retry restores the page.
 await page.route('**/data/meta.json',route=>route.fulfill({status:503,body:'unavailable'}));
 await page.reload();await page.locator('#loadError').waitFor({state:'visible'});
 await page.unroute('**/data/meta.json');await page.locator('#retry').click();await page.locator('.card').first().waitFor();assert.equal(await page.locator('#loadError').isVisible(),false);
 assert.deepEqual(errors,[]);
 console.log('Browser checks passed: actual user HTML open/closed, disabled/hidden/aria-disabled/wrong ID, favorites persistence, applied, hide/restore, search, filters, 5 sorts, review export, mobile layout, corrupt storage, load failure/retry; no page errors.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});

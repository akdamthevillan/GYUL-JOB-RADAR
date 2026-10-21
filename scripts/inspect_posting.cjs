/* One posting at a time. No submissions, login, access bypass or bulk traversal. */
const R=require('../assets/radar.js');
async function inspectPage(page, expectedId=null){
 return page.evaluate(expectedId=>{
  const visible=el=>{const s=getComputedStyle(el),r=el.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0;};
  const text=el=>(el.innerText||el.value||el.textContent||'').replace(/\s+/g,' ').trim();
  const controls=[...document.querySelectorAll('button,a,input[type=button],input[type=submit],[role=button]')].filter(visible).filter(el=>{const handler=el.getAttribute('onclick')||'',m=handler.match(/quickApply(?:Mobile|Form)\(['"](\d+)['"]/);return !expectedId||!m||m[1]===expectedId;}).map(el=>({text:text(el),className:el.className,disabled:el.disabled===true||el.getAttribute('aria-disabled')==='true'||el.hasAttribute('disabled')||!!el.closest('[inert]')||getComputedStyle(el).pointerEvents==='none',href:el.getAttribute('href')||null}));
  const root=document.querySelector('main,[role=main],#content,#contents')||document.body;
  const body=root.innerText||'';
  const closed=/본\s*채용정보는\s*마감되었습니다|본\s*공고는\s*마감되었습니다/.test(body)||controls.some(c=>String(c.className).split(/\s+/).includes('sri_btn_expired_apply')||/^접수\s*마감$/.test(c.text));
  const active=controls.filter(c=>/^(입사지원|사람인\s*입사지원|즉시지원|지원하기)$/.test(c.text)&&!c.disabled&&!String(c.className).split(/\s+/).includes('sri_btn_expired_apply')&&c.href!=='#');
  const blocked=/접근이 제한|접근 제한|비정상적인 접근|Access Denied|자동입력 방지|로봇이 아닙니다/i.test(body);
  // A sign-in-only or error document cannot prove the original posting's state.
  const unavailable=blocked||/HTTP_BAD_REQUEST|페이지를 찾을 수 없|요청하신 페이지가 없/.test(body);
  const result=unavailable?'unknown':closed?'closed':active.length?'apply_enabled':'unknown';
  return {result,controls:controls.filter(c=>/지원|마감/.test(c.text)).slice(0,20),reason:unavailable?'접근·오류 페이지':closed?'명시적 마감 안내/컨트롤':active.length?'표시된 지원 컨트롤이 비활성 상태가 아님':'사용 가능한 지원 경로 미확인'};
 },expectedId);
}
async function main(){
 const url=process.argv[2],id=R.postingId({url});if(!id)throw Error('Usage: node scripts/inspect_posting.cjs <individual Saramin HTTPS URL>');
 const {chromium}=require('playwright');
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 const page=await browser.newPage();
 try{
  const response=await page.goto(url,{waitUntil:'domcontentloaded',timeout:30000});
  let outcome=await inspectPage(page,id);
  if(!response?.ok()||R.postingId({url:page.url()})!==id)outcome={result:'unknown',reason:'공고 URL 불일치 또는 HTTP 오류'};
  console.log(JSON.stringify({id,source_url:url,observed_at:new Date().toISOString(),method:'page_dom',evidence:(outcome.reason+' '+JSON.stringify(outcome.controls||[])).slice(0,4000),...outcome},null,2));
 }catch(error){console.log(JSON.stringify({id,source_url:url,result:'unknown',method:'page_dom',observed_at:new Date().toISOString(),reason:error.message,evidence:'페이지 접근 실패: '+error.message.slice(0,3000)},null,2));process.exitCode=2;}
 finally{await browser.close();}
}
module.exports={inspectPage};
if(require.main===module)main().catch(e=>{console.error(e.message);process.exitCode=1;});

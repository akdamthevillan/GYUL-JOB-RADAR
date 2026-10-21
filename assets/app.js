"use strict";
const $=id=>document.getElementById(id),LOCAL_KEY="gyul-radar-preferences-v3",MANUAL_KEY="gyul-radar-manual-v3";
const escapeHTML=x=>String(x??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const KST=()=>new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Seoul",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date());
let today=KST();
const dateMinus=(str,n)=>{const x=new Date(str+"T12:00:00+09:00");x.setTime(x.getTime()-n*86400000);return new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Seoul",year:"numeric",month:"2-digit",day:"2-digit"}).format(x)};
let recentThreshold=dateMinus(today,7);
const store=(k,obj)=>{try{localStorage.setItem(k,JSON.stringify(obj))}catch{ $("storageNotice").textContent="브라우저 저장에 실패했습니다. 현재 선택은 새로고침하면 사라질 수 있습니다."; }};
const load=(k,otherwise)=>{try{const x=JSON.parse(localStorage.getItem(k)||"null");return x??otherwise}catch{return otherwise}};
const R=GyulRadar;
const prefs=R.preferences(load(LOCAL_KEY,{}));let dataset=[],localData=load(MANUAL_KEY,[]),config=null,view="all",closedIds=new Set(),shown=0;
const PAGE_SIZE=40,chips=new Set(),STAT_CHIPS=["new","soon"];
const validUrl=u=>{try{const p=new URL(u);return p.protocol==="https:"&&["saramin.co.kr","www.saramin.co.kr","www2.saramin.co.kr","m.saramin.co.kr"].includes(p.host)?p.href:""}catch{return""}};
const normalize=s=>String(s||"").normalize("NFKC").toLowerCase().replace(/[\s()[\]\-_.]+/g,"");
const sourceId=R.postingId;
const mobilePostingUrl=j=>sourceId(j)?"https://m.saramin.co.kr/job-search/view?rec_idx="+sourceId(j):validUrl(j.url);
const identity=j=>sourceId(j)?"r:"+sourceId(j):"f:"+[j.company,j.title,j.location].map(normalize).join("|");
const isClosed=j=>["closed_by_ui","expired_by_date"].includes(R.status(j,today));
const isVerified=j=>R.status(j,today)==="verified_open";
const profile=()=>config?.advisor_profile||{};
const closingSoon=j=>j.deadline&&j.deadline>=today&&j.deadline<=dateMinus(today,-7);
const isNew=j=>{const d=R.validDate(j.posted_at)?j.posted_at:j.first_seen;return !!d&&d>=recentThreshold&&d<=today};
const text=x=>String(x??"").trim(),label=(x,fallback="공고 확인")=>text(x)||fallback;
function unique(list){const ids=new Set(),fallbacks=new Set(),out=[];for(const j of list){if(!j||!sourceId(j)||!j.company||!j.title||!validUrl(j.url)||isClosed(j)||closedIds.has(String(sourceId(j)||j.id)))continue;const r=sourceId(j),f=[j.company,j.title,j.location].map(normalize).join("|");if(r){if(ids.has(r))continue;ids.add(r)}else{if(fallbacks.has(f))continue;fallbacks.add(f)}out.push(j)}return out}
function allJobs(){return unique([...(Array.isArray(localData)?localData:[]),...dataset]);}
const hasFit=(j,key)=>R.fit(j,profile()).some(x=>x.key===key);
const chipTests={
 newbie:j=>hasFit(j,"newbie"),pay:j=>hasFit(j,"pay"),salaryOpen:j=>R.salary(j)!==null,new:isNew,soon:closingSoon};
function matches(j,{skip=[],mode=view}={}){
 const query=normalize($("search").value),region=$("region").value,role=$("role").value,hidden=prefs.hidden.includes(identity(j));
 // Saved views keep postings that are briefly between checks; the main list shows confirmed ones only.
 return (mode==="hidden"?hidden:!hidden)&&(mode!=="all"||isVerified(j))&&(mode==="all"||mode==="hidden"||prefs[mode].includes(identity(j)))
  &&(!query||normalize([j.company,j.title,j.location,j.salary,j.benefits,j.considerations,j.category,j.experience,j.employment,j.job_sectors].join(" ")).includes(query))
  &&(!region||String(j.location||"").includes(region))&&(!role||String(j.category||"")===role)
  &&[...chips].filter(c=>!skip.includes(c)).every(c=>chipTests[c](j));
}
const dueToday=j=>j.deadline===today;
function filtered(){
 const sort=$("sort").value;
 // Postings closing today stay on top of the default sweetness order.
 return allJobs().filter(j=>matches(j)).sort((a,b)=>(sort==="recommended"?dueToday(b)-dueToday(a):0)||R.compare(a,b,sort,profile(),today));
}

const fact=(name,value)=>'<div class="fact"><dt>'+escapeHTML(name)+'</dt><dd>'+escapeHTML(value)+'</dd></div>';
const destinationAddress=j=>{
 const v=String(j.location||"").trim();
 if(!v||/확인 필요|미공개|주소 없음|미확인|정확하지 않음/.test(v))return null;
 const address=v.replace(/\s*\([^)]*\)/g,"").trim();
 const street=/(?:로|길|대로|번길)\s*\d+(?:-\d+)?(?:[\s,]|$)/.test(address);
 const lot=/(?:동|읍|면)\s+\d+(?:-\d+)?(?:[\s,]|$)/.test(address);
 return /(부산|김해|양산)/.test(address)&&(street||lot)?address:null;
};
const shortText=(x,n)=>{const v=text(x).replace(/\s+/g," ");return v.length>n?v.slice(0,n-1)+"…":v};
const monthDay=d=>d.slice(5).replace("-","/");
function deadlineLabel(j){
 if(R.validDate(j.deadline)){const days=Math.round((Date.parse(j.deadline)-Date.parse(today))/86400000);return {text:(days<=0?"오늘 마감":"D-"+days)+" · "+monthDay(j.deadline),soon:days<=7,urgent:days<=3};}
 return {text:shortText(String(j.deadline_text||"").replace(/^~\s*/,"~"),16)||"마감일 확인",soon:false,urgent:false};
}
// Saramin detail text packs sections and bullets into one line; break them for reading.
const readable=x=>String(x||"").replace(/\s*(📋|🎁)\s*/g,"\n").replace(/\s+(•|ㆍ|·\s)/g,"\n$1").replace(/\s+(\d+\)|\d+\.)\s/g,"\n$1 ").trim();
// Older records captured tooltip text after the value ("… 상세보기 …"); keep only the value.
const cleanValue=x=>String(x||"").split(/\s*(?:근무형태\s*)?상세보기/)[0].trim();
const cleanBenefits=x=>String(x||"").replace(/^\s*🎁?\s*복지 및 혜택\s*/,"");
function payText(j){
 const v=cleanValue(j.salary).replace(/\([^)]*\)/g,"").replace(/\s+/g," ").replace(/(\d)\s*만\s*원/g,"$1만원").trim();
 return v.replace(/^월급\s*/,"월 ").replace(/^연봉\s*/,"연 ").replace(/^시급\s*/,"시급 ");
}
function benefitTags(j){
 // "• 리프레시 : 연차, 휴가비지원 • 급여제도 : 상여금" → short tags.
 const items=readable(cleanBenefits(j.benefits)).split("\n").flatMap(line=>{const body=line.replace(/^[•ㆍ·\s]+/,"");return (body.includes(":")?body.split(":").slice(1).join(":"):body).split(/,|·|\//)}).map(x=>x.replace(/\.\.\.|…/g,"").trim()).filter(x=>x&&x.length<=14&&!/미공개|미기재/.test(x));
 return [...new Set(items)];
}
function companyInfo(j){
 const c=j.company_profile&&typeof j.company_profile==="object"?j.company_profile:{};
 const year=String(c.established||"").match(/(\d{4})년/);
 const size=[c.company_type,text(c.employees)?"사원 "+String(c.employees).replace(/\s+/g,""):"",text(c.revenue)?"매출 "+String(c.revenue).replace(/\s*\d+만원$/,"").replace(/\s+/g,""):"",year?year[1]+"년 설립":"",R.metric(j,"avg_salary")?"평균연봉 "+R.metric(j,"avg_salary").value:""].filter(x=>text(x));
 return {size,industry:text(c.industry||j.company_business),business:text(c.business),homepage:text(c.homepage),source:R.safeUrl(c.source_url),checked:c.checked_at||"",unavailable:!!c.unavailable};
}
function card(j){
 const id=identity(j),fav=prefs.favorites.includes(id),applied=prefs.applied.includes(id),url=mobilePostingUrl(j),score=R.recommend(j,profile(),today).score,d=deadlineLabel(j);
 // Postings found on a listing show listing facts until their own page has been read.
 const pending=j.discovered_by==="auto_sync"&&!j.details_checked_at,wait=x=>pending?"수집 중":x;
 const unknown=x=>!text(x)||/미확인|확인 필요|원문 확인|공고 확인/.test(String(x));
 const co=companyInfo(j),address=destinationAddress(j);
 // A confirmed street address opens Kakao Map; listing-only districts stay plain text.
 const addressCell=address?{html:'<a class="addr-link" href="https://map.kakao.com/?q='+encodeURIComponent(address)+'" target="_blank" rel="noopener noreferrer" title="카카오맵에서 보기">'+escapeHTML(address)+' ↗</a>'}:unknown(j.location)?wait("주소 확인 필요"):cleanValue(j.location);
 const pay=payText(j);
 const cells=[
  ["연봉",unknown(pay)||/미공개/.test(pay)?wait("미공개"):pay,!/면접|내규|협의|미공개|수집/.test(pay)&&!unknown(pay)],
  ["주소",addressCell,false],
  ["경력",unknown(j.experience)?"공고 확인":cleanValue(j.experience),false],
  ["근무",unknown(j.work_schedule)?wait("공고 확인"):cleanValue(j.work_schedule),false],
  ["고용",unknown(j.employment)?wait("공고 확인"):cleanValue(j.employment).replace(/수습기간/,"· 수습"),false],
  ["회사",co.size.length?co.size.slice(0,2).join(" · "):co.unavailable?"기업정보 없음":"확인 중",false]];
 const grid='<dl class="keygrid">'+cells.map(([k,v,strong])=>'<div><dt>'+k+'</dt><dd'+(strong?' class="strong"':'')+'>'+(v&&v.html?v.html:escapeHTML(shortText(v,28)))+'</dd></div>').join("")+'</dl>';
 const meta=['<span class="dday'+(d.urgent?' urgent':d.soon?' soon':'')+'">'+escapeHTML(d.text)+'</span>',R.validDate(j.posted_at)?'<span class="meta">등록 '+escapeHTML(monthDay(j.posted_at))+'</span>':'','<span class="cat">'+escapeHTML(label(j.category,"미분류"))+'</span>',j.apply_route==="homepage"?'<span class="badge">홈페이지 지원</span>':'',isVerified(j)?'':'<span class="badge warn">접수 확인 중</span>'].filter(Boolean).join("");
 const fits=R.fit(j,profile());
 const sweet='<div class="sweet"><span class="brix">귤 당도 <b>'+score+'</b>브릭스</span>'+fits.map(f=>'<span class="fit"><svg class="gyul-sm" aria-hidden="true"><use href="#gyul"/></svg>'+escapeHTML(f.label)+'</span>').join("")+'</div>';
 // Drop section headings ("주요업무") and "직무명 (1명)" lines; split "a - b - c" runs into items.
 const lines=readable(j.duties).split("\n").flatMap(x=>x.split(/\s+-\s+/)).map(x=>x.replace(/^[•ㆍ·-]\s*/,"").trim())
  .filter(x=>x&&!/^(주요\s*업무|담당\s*업무|자격\s*요건|지원\s*자격|우대\s*사항|필수\s*요건|근무\s*조건)\s*:?$/.test(x)&&!/\((?:\d+|0+)\s*명\)$/.test(x)),long=lines.length>4;
 const duties=lines.length?'<section class="card-section"><h3>담당 업무</h3><ul class="duty-list'+(long?' clamped':'')+'">'+lines.map(x=>'<li>'+escapeHTML(x)+'</li>').join("")+'</ul>'+(long?'<button type="button" class="text-button" data-action="expand">전체 보기</button>':'')+'</section>':'<section class="card-section"><h3>담당 업무</h3><p class="section-text muted">'+wait("공고 원문에서 확인")+'</p></section>';
 const tags=benefitTags(j),shown=tags.slice(0,8);
 const benefits=shown.length?'<section class="card-section"><h3>복지</h3><div class="tag-row">'+shown.map(x=>'<span class="tag">'+escapeHTML(x)+'</span>').join("")+(tags.length>shown.length?'<span class="tag more">+'+(tags.length-shown.length)+'</span>':'')+'</div></section>':'';
 const info=[co.industry?['업종',escapeHTML(co.industry)]:null,co.business?['사업',escapeHTML(shortText(co.business,80))]:null,
  co.homepage?['홈페이지',escapeHTML(co.homepage.replace(/^https?:\/\//,""))]:null,
  co.size.length>2?['규모',escapeHTML(co.size.join(" · "))]:null].filter(Boolean);
 const source=co.source?'<small class="note">회사 정보: 사람인 기업정보 '+escapeHTML(co.checked)+' · <a href="'+escapeHTML(co.source)+'" target="_blank" rel="noopener noreferrer">출처</a></small>':'';
 return '<article class="card'+(d.urgent?' urgent':'')+'"><div class="card-top"><div><div class="company">'+escapeHTML(j.company)+'</div><div class="jobtitle">'+escapeHTML(j.title)+'</div></div><button type="button" class="favorite" data-action="favorite" data-id="'+escapeHTML(id)+'" aria-pressed="'+fav+'" title="관심 공고" aria-label="관심 공고">'+(fav?"★":"☆")+'</button></div>'+
 sweet+'<div class="card-meta">'+meta+'</div>'+grid+
 '<div class="card-actions"><a class="button primary apply" href="'+escapeHTML(url)+'" target="_blank" rel="noopener noreferrer">지원하기 ↗</a><button type="button" class="button small" data-action="applied" data-id="'+escapeHTML(id)+'">'+(applied?"지원 완료 ✓":"지원 표시")+'</button><button type="button" class="button small ghost" data-action="hide" data-id="'+escapeHTML(id)+'" title="이 브라우저에서 숨기거나 복구">'+(view==="hidden"?"복구":"숨김")+'</button></div>'+
 duties+benefits+
 (info.length||source?'<section class="card-section"><dl class="minor">'+info.map(([k,v])=>'<div><dt>'+k+'</dt><dd>'+v+'</dd></div>').join("")+'</dl>'+source+'</section>':'')+'</article>';
}
function render(){today=KST();recentThreshold=dateMinus(today,7);
 const base=allJobs().filter(j=>matches(j,{skip:STAT_CHIPS,mode:"all"})),list=filtered();
 shown=Math.max(shown,PAGE_SIZE);
 $("statsOpen").textContent=base.length;$("statsNew").textContent=base.filter(isNew).length;$("statsSoon").textContent=base.filter(closingSoon).length;
 document.querySelectorAll("[data-chip]").forEach(b=>b.setAttribute("aria-pressed",String(chips.has(b.dataset.chip))));
 document.querySelectorAll("[data-stat]").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.stat==="open"?!STAT_CHIPS.some(c=>chips.has(c)):chips.has(b.dataset.stat))));
 $("count").textContent=list.length+"개 공고";
 $("cards").innerHTML=list.length?list.slice(0,shown).map(card).join(""):'<div class="empty"><svg class="empty-icon" aria-hidden="true"><use href="#gyul"/></svg><strong>표시할 공고가 없어요</strong>필터를 줄이거나 검색어를 바꿔 보세요.</div>';
 $("more").hidden=list.length<=shown;$("more").textContent="더 보기 ("+Math.max(0,list.length-shown)+"개 남음)";}
function renderConfig(){if(!config)return;$("region").innerHTML='<option value="">전체 지역</option>';$("role").innerHTML='<option value="">전체 직무</option>';for(const r of config.focus||[]){const op=document.createElement("option");op.value=r;op.textContent=r;$("region").append(op)}for(const name of [...new Set(dataset.map(j=>j.category).filter(Boolean))].sort()){const op=document.createElement("option");op.value=name;op.textContent=name;$("role").append(op)}
 $("profile").innerHTML='<p class="note">유니폼·SNS 디자인 실무 약 3개월 (2026-10 기준) · 브랜딩·패키지·편집·캐릭터 포트폴리오</p><p class="note">공고번호가 확인되지 않은 기존 자료는 원본을 보존하고 지원 목록에서 보류합니다.</p><p class="note">귤 당도(브릭스)는 직무 40% · 출퇴근 25% · 연봉 20% · 복지 10% · 회사 규모 5%로 계산한 종합 추천 지수입니다. 카드의 귤 아이콘은 신입 가능 · 선호 연봉 이상 · 포트폴리오 연결 직무 · 냉정역 근처(직선 8km 이내) · 정규직 중 해당하는 항목입니다. 미확인 항목은 중립값으로 계산합니다. 평가 정보 비율은 점수 산정에 필요한 항목의 확인 비율이며 접수 확인률이 아닙니다. 거리만 있으면 직선거리로 출퇴근을 참고 평가합니다.</p><div class="tags">'+(config.search_strategy?.additional_keywords||[]).map(k=>'<span class="tag">'+escapeHTML(k)+'</span>').join('')+'</div><p class="note">냉정역 좌표: <a href="https://www.openstreetmap.org/node/14102501783" target="_blank" rel="noopener noreferrer">© OpenStreetMap contributors</a> · 실제 근무지는 각 좌표 출처 참조</p>';}
$("cards").addEventListener("click",e=>{
 const btn=e.target.closest("button[data-action]");if(!btn)return;
 if(btn.dataset.action==="expand"){const box=btn.previousElementSibling;box.classList.toggle("clamped");btn.textContent=box.classList.contains("clamped")?"전체 보기":"접기";return;}
 const id=btn.dataset.id,action=btn.dataset.action,key={favorite:"favorites",applied:"applied",hide:"hidden"}[action];if(!key)return;
 const arr=prefs[key],n=arr.indexOf(id);
 if(key==="hidden"&&n<0&&!confirm("이 브라우저에서 공고를 숨기시겠습니까?"))return;
 if(n<0)arr.push(id);else arr.splice(n,1);
 store(LOCAL_KEY,prefs);render();
});
document.querySelectorAll("[data-view]").forEach(b=>b.onclick=()=>{view=b.dataset.view;shown=0;document.querySelectorAll("[data-view]").forEach(x=>x.setAttribute("aria-pressed",String(x.dataset.view===view)));render()});
["search","region","role","sort"].forEach(id=>$(id).addEventListener(id==="search"?"input":"change",()=>{shown=0;render()}));
document.querySelectorAll("[data-chip]").forEach(b=>b.addEventListener("click",()=>{const c=b.dataset.chip;chips.has(c)?chips.delete(c):chips.add(c);shown=0;render()}));
document.querySelectorAll("[data-stat]").forEach(b=>b.addEventListener("click",()=>{
 const c=b.dataset.stat;
 if(c==="open")STAT_CHIPS.forEach(x=>chips.delete(x));else{const on=chips.has(c);STAT_CHIPS.forEach(x=>chips.delete(x));if(!on)chips.add(c);}
 shown=0;render();
}));
$("more").addEventListener("click",()=>{shown+=PAGE_SIZE;render()});
async function loadData(){
 $("loadError").hidden=true;$("retry").disabled=true;
 try{
  const [jobs,meta,cfg,closed]=await Promise.all(["jobs","meta","search-config","closed-postings"].map(async name=>{const r=await fetch("./data/"+name+".json",{cache:"no-store"});if(!r.ok)throw Error(name);return r.json();}));
  if(!Array.isArray(jobs)||!cfg?.advisor_profile||!Array.isArray(closed?.postings))throw Error('invalid data');
  dataset=jobs;config=cfg;closedIds=new Set(closed.postings.map(p=>String(p.id)));
  // Narrow screens drop "데이터" and "KST" so the header stays on one line.
  $("review").innerHTML=meta.last_updated_at&&Number.isFinite(Date.parse(meta.last_updated_at))?'<span class="wide-only">데이터 </span>갱신 '+escapeHTML(new Intl.DateTimeFormat("sv-SE",{timeZone:"Asia/Seoul",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).format(new Date(meta.last_updated_at)))+'<span class="wide-only"> KST</span>':"데이터 갱신 시각 미확인";
  $("review").classList.remove("error");renderConfig();render();
 }catch{$("review").textContent="목록을 불러오지 못했습니다.";$("review").classList.add("error");$("loadError").hidden=false;}
 finally{$("retry").disabled=false;}
}
$("retry").addEventListener("click",loadData);
$("reviewForm").addEventListener("submit",e=>{
 e.preventDefault();const form=new FormData(e.target),url=String(form.get("url")),id=sourceId({url});
 const observed=String(form.get("observed")),timestamp=observed+":00+09:00",parsed=new Date(timestamp);
 if(!id||Number.isNaN(parsed.getTime())||parsed>new Date()){$("reviewMessage").textContent="올바른 사람인 개별 공고 URL과 미래가 아닌 관찰 시각을 입력해 주세요.";return;}
 const date=observed.slice(0,10),result=String(form.get("result")),kind=String(form.get("method")),evidence=String(form.get("evidence")).trim();
 const job={id,url,company:String(form.get("company")),title:String(form.get("title")),status:"재확인 필요",source_checked_at:date};
 const observation={id,observed_at:timestamp,source_url:url,result,method:kind,evidence};
 let payload;
 if(result==="closed")payload={jobs:[],closed_postings:[{id,reason:"접수마감 확인: "+evidence.slice(0,250),closed_confirmed:date,evidence_url:url,application_button_state:"closed",application_evidence_kind:kind,application_checked_at:date}],observations:[observation]};
 else{
  if(result==="apply_enabled")Object.assign(job,{status:"verified_open",verified_at:date,verified_source_url:url,verification_evidence:evidence,application_button_state:result,application_evidence_kind:kind,application_checked_at:date});
  payload={jobs:[job],closed_postings:[],observations:[observation]};
 }
 $("reviewOutput").hidden=false;$("reviewOutput").value=JSON.stringify(payload,null,2);$("reviewMessage").textContent="JSON을 만들었습니다. 내용을 검토한 뒤 저장소 소유자에게 전달해 주세요.";
});
setInterval(()=>{if(dataset.length&&KST()!==today)render();},30000);
document.addEventListener("visibilitychange",()=>{if(!document.hidden&&dataset.length)render();});
loadData();

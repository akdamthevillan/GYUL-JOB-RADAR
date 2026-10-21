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
const PAGE_SIZE=40;
const validUrl=u=>{try{const p=new URL(u);return p.protocol==="https:"&&["saramin.co.kr","www.saramin.co.kr","www2.saramin.co.kr","m.saramin.co.kr"].includes(p.host)?p.href:""}catch{return""}};
const normalize=s=>String(s||"").normalize("NFKC").toLowerCase().replace(/[\s()[\]\-_.]+/g,"");
const sourceId=R.postingId;
const mobilePostingUrl=j=>sourceId(j)?"https://m.saramin.co.kr/job-search/view?rec_idx="+sourceId(j):validUrl(j.url);
const identity=j=>sourceId(j)?"r:"+sourceId(j):"f:"+[j.company,j.title,j.location].map(normalize).join("|");
const isClosed=j=>["closed_by_ui","expired_by_date"].includes(R.status(j,today));
const isVerified=j=>R.status(j,today)==="verified_open";
const profile=()=>config?.advisor_profile||{};
const closingSoon=j=>j.deadline&&j.deadline>=today&&j.deadline<=dateMinus(today,-7);
const isNew=j=>j.first_seen&&j.first_seen>=recentThreshold&&j.first_seen<=today;
const text=x=>String(x??"").trim(),label=(x,fallback="공고 확인")=>text(x)||fallback;
function unique(list){const ids=new Set(),fallbacks=new Set(),out=[];for(const j of list){if(!j||!sourceId(j)||!j.company||!j.title||!validUrl(j.url)||isClosed(j)||closedIds.has(String(sourceId(j)||j.id)))continue;const r=sourceId(j),f=[j.company,j.title,j.location].map(normalize).join("|");if(r){if(ids.has(r))continue;ids.add(r)}else{if(fallbacks.has(f))continue;fallbacks.add(f)}out.push(j)}return out}
function allJobs(){return unique([...(Array.isArray(localData)?localData:[]),...dataset]);}
function filtered(){const query=normalize($("search").value),region=$("region").value,role=$("role").value,salary=$("salaryOnly").checked;
 const jobs=allJobs().filter(j=>{
  const id=identity(j),hidden=prefs.hidden.includes(id);
  // Saved views keep postings that are briefly between checks; the main list shows confirmed ones only.
  return (view==="hidden"?hidden:!hidden)&&(view!=="all"||isVerified(j))&&(!query||normalize([j.company,j.title,j.location,j.salary,j.benefits,j.considerations,j.category,j.experience,j.employment,j.job_sectors].join(" ")).includes(query))&&(!region||String(j.location||"").includes(region))&&(!role||String(j.category||"")===role)&&(!salary||R.salary(j)!==null)&&(view==="all"||view==="hidden"||prefs[view].includes(id));
 });
 return jobs.sort((a,b)=>R.compare(a,b,$("sort").value,profile(),today));
}

const fact=(name,value)=>'<div class="fact"><dt>'+escapeHTML(name)+'</dt><dd>'+escapeHTML(value)+'</dd></div>';
const destinationAddress=j=>{
 const v=String(j.location||"").trim();
 if(!v||/확인 필요|미공개|주소 없음|미확인|정확하지 않음/.test(v))return null;
 const address=v.replace(/\s*\([^)]*\)/g,"").trim();
 const street=/(?:로|길|대로|번길)\s*\d+(?:-\d+)?(?:\s|$)/.test(address);
 const lot=/(?:동|읍|면)\s+\d+(?:-\d+)?(?:\s|$)/.test(address);
 return /(부산|김해|양산)/.test(address)&&(street||lot)?address:null;
};
function mapHref(j){
 const address=destinationAddress(j);
 return address?"https://map.kakao.com/?sName="+encodeURIComponent("냉정역")+"&eName="+encodeURIComponent(address):"";
}
function locationFact(j){
 const address=destinationAddress(j);
 const link=address?'<a class="map-link" href="https://map.kakao.com/?q='+encodeURIComponent(address)+'" target="_blank" rel="noopener noreferrer">지도 ↗</a> <a class="map-link" href="'+escapeHTML(mapHref(j))+'" target="_blank" rel="noopener noreferrer" title="냉정역 출발 · 근무지 주소 도착 카카오맵 길찾기">길찾기 ↗</a>':'';
 const display=label(j.location,"주소 확인 필요")+(address?"":(String(j.location||"").includes("미확인")?"":" (정확한 주소 미확인)"));
 return '<div class="fact"><dt>주소</dt><dd>'+escapeHTML(display)+link+'</dd></div>';
}
const metricNames={revenue:"매출액",operating_profit:"영업이익",avg_salary:"평균연봉",employees:"직원수",recent_hires:"최근 입사",recent_leavers:"최근 퇴사"};
function metrics(j){
 const cells=Object.keys(metricNames).filter(k=>R.metric(j,k)).map(k=>{
  const item=R.metric(j,k),period=item.year||item.period||item.as_of;
  return '<div class="metric"><span>'+metricNames[k]+'</span><strong>'+escapeHTML(item.value)+'</strong><div>'+escapeHTML(period)+' <a href="'+escapeHTML(R.safeUrl(item.source_url))+'" target="_blank" rel="noopener noreferrer">출처 ↗</a></div></div>';
 });
 const business=j.company_business?'<p class="note">'+escapeHTML(j.company_business)+'</p>':'';
 const companyUrl=R.safeUrl(j.company_url);
 const link=companyUrl?'<a href="'+escapeHTML(companyUrl)+'" target="_blank" rel="noopener noreferrer">회사 정보 보기 ↗</a>':'';
 return '<details class="business-summary"><summary>회사 정보</summary>'+business+(cells.length?'<div class="business-metrics">'+cells.join('')+'</div>':'<p class="note">출처와 기준시점이 확인된 회사 규모·재무 정보가 없습니다.</p>')+link+'<small>회사 평균연봉은 이 공고의 제시 연봉과 다릅니다. 큰 회사가 좋은 근무환경을 보장하지는 않습니다.</small></details>';
}
function commuteFact(j){
 const trip=R.transit(j,today),km=R.distance(j,profile());
 let value=trip?'대중교통 '+trip.minutes+'분'+(Number.isInteger(trip.transfers)?' · 환승 '+trip.transfers+'회':'')+' ('+trip.checked_at+' 확인)':km!==null?'직선 '+km.toFixed(1)+' km · 대중교통 시간 미확인':'냉정역 출발 · 거리·대중교통 시간 미확인';
 const source=km!==null?'<a class="map-link" href="'+escapeHTML(R.safeUrl(j.workplace_coordinates.source_url))+'" target="_blank" rel="noopener noreferrer">좌표 출처</a>':'';
 return '<div class="fact"><dt>출퇴근</dt><dd>'+escapeHTML(value)+(km!==null?(j.workplace_coordinates.precision==='posting_map'?' (공고 지도 기준)':' (건물 기준)'):'')+source+'</dd></div>';
}
function advice(j){
 const a=R.recommend(j,profile(),today),pay=R.salary(j);
 return '<section class="advice" aria-label="귤 당도"><div class="advice-title">귤 당도 '+a.score+'브릭스 <span>평가 정보 '+a.coverage+'% 확인</span></div><ul>'+a.notes.map(n=>'<li>'+escapeHTML(n)+'</li>').join('')+'</ul>'+(pay?.converted?'<p class="note">'+escapeHTML(pay.label)+' · 상여·수당·퇴직금 포함 여부 확인</p>':'')+'</section>';
}
const shortText=(x,n)=>{const v=text(x).replace(/\s+/g," ");return v.length>n?v.slice(0,n-1)+"…":v};
const unknownValue=x=>!text(x)||/미확인|미공개|확인 필요|원문 확인|공고 확인/.test(String(x));
function dday(j){
 if(R.validDate(j.deadline)){const days=Math.round((Date.parse(j.deadline)-Date.parse(today))/86400000);return {text:days<=0?"오늘 마감":"D-"+days,soon:days<=7};}
 return {text:shortText(String(j.deadline_text||"").replace(/^~\s*/,"~"),14)||"마감일 확인",soon:false};
}
function summary(j){
 const km=R.distance(j,profile()),place=unknownValue(j.location)?"위치 확인 필요":String(j.location).split(/\s+/).slice(0,2).join(" ");
 const employment=String(j.employment||"").split(/\s*근무형태|\s*상세보기/)[0];
 const items=[place+(km!==null?" · 직선 "+km.toFixed(1)+"km":""),unknownValue(j.salary)?"급여 미공개":(/^(연봉|월급|시급|일급|주급|급여)/.test(text(j.salary))?"":"급여 ")+shortText(j.salary,26),[shortText(j.experience,18),unknownValue(employment)?"":shortText(employment,14)].filter(Boolean).join(" · ")];
 return '<ul class="summary">'+items.map(x=>'<li>'+escapeHTML(x)+'</li>').join("")+'</ul>';
}
function card(j){
 const id=identity(j),fav=prefs.favorites.includes(id),applied=prefs.applied.includes(id),url=mobilePostingUrl(j),a=R.recommend(j,profile(),today),d=dday(j);
 const chips=['<span class="brix" title="직무·출퇴근·연봉·복지·규모 종합">귤 당도 '+a.score+'브릭스</span>','<span class="badge'+(d.soon?' warn':'')+'">'+escapeHTML(d.text)+'</span>',isNew(j)?'<span class="badge new">NEW</span>':'',j.apply_route==="homepage"?'<span class="badge">홈페이지 지원</span>':'',isVerified(j)?'':'<span class="badge warn">접수 확인 중</span>'].filter(Boolean).join("");
 return '<article class="card"><div class="card-top"><div><div class="company">'+escapeHTML(j.company)+'</div><div class="jobtitle">'+escapeHTML(j.title)+'</div></div><button type="button" class="favorite" data-action="favorite" data-id="'+escapeHTML(id)+'" aria-pressed="'+fav+'" title="관심 공고" aria-label="관심 공고">'+(fav?"★":"☆")+'</button></div>'+
 '<div class="badge-group">'+chips+'</div>'+summary(j)+
 '<div class="card-actions"><a class="button primary apply" href="'+escapeHTML(url)+'" target="_blank" rel="noopener noreferrer">지원하기 ↗</a><button type="button" class="button small" data-action="applied" data-id="'+escapeHTML(id)+'">'+(applied?"지원 완료 ✓":"지원 표시")+'</button><button type="button" class="button small ghost" data-action="hide" data-id="'+escapeHTML(id)+'" title="이 브라우저에서 숨기거나 복구">'+(view==="hidden"?"복구":"숨김")+'</button></div>'+
 '<details class="more"><summary>자세히</summary>'+advice(j)+'<dl class="facts">'+locationFact(j)+commuteFact(j)+fact("마감",label(j.deadline||j.deadline_text,"확인 필요"))+fact("경력",label(j.experience,"경력요건 확인 필요"))+
 fact("고용형태",label(j.employment,"공고 확인"))+fact("근무시간",label(j.work_schedule,"원문 확인"))+fact("연봉",label(j.salary,"미공개"))+
 fact("복지",label(j.benefits,"미공개"))+fact("직무",label(j.category,"미분류"))+fact("지원 방식",label(j.application_method,"원문에서 확인 필요"))+'</dl>'+
 (j.duties?'<details class="business-summary"><summary>담당업무·요건</summary><p class="note">'+escapeHTML(j.duties)+'</p></details>':'')+metrics(j)+'</details></article>';
}
function render(){today=KST();recentThreshold=dateMinus(today,7);const open=allJobs().filter(j=>!prefs.hidden.includes(identity(j))&&isVerified(j)),list=filtered();
shown=Math.max(shown,PAGE_SIZE);
$("statsOpen").textContent=open.length;$("statsNew").textContent=open.filter(isNew).length;$("statsSoon").textContent=open.filter(closingSoon).length;$("count").textContent=list.length+"개 공고";
$("cards").innerHTML=list.length?list.slice(0,shown).map(card).join(""):'<div class="empty"><strong>표시할 공고가 없습니다</strong>검색 조건에 맞는 공고가 없습니다.</div>';
$("more").hidden=list.length<=shown;$("more").textContent="더 보기 ("+Math.max(0,list.length-shown)+"개 남음)";}
function renderConfig(){if(!config)return;$("region").innerHTML='<option value="">전체 지역</option>';$("role").innerHTML='<option value="">전체 직무</option>';for(const r of config.focus||[]){const op=document.createElement("option");op.value=r;op.textContent=r;$("region").append(op)}for(const name of [...new Set(dataset.map(j=>j.category).filter(Boolean))].sort()){const op=document.createElement("option");op.value=name;op.textContent=name;$("role").append(op)}
 $("profile").innerHTML='<p class="note">유니폼·SNS 디자인 실무 약 3개월 (2026-10 기준) · 브랜딩·패키지·편집·캐릭터 포트폴리오</p><p class="note">공고번호가 확인되지 않은 기존 자료는 원본을 보존하고 지원 목록에서 보류합니다.</p><p class="note">귤 당도(브릭스)는 직무 40% · 출퇴근 25% · 연봉 20% · 복지 10% · 회사 규모 5%로 계산한 종합 추천 지수입니다. 미확인 항목은 중립값으로 계산합니다. 평가 정보 비율은 점수 산정에 필요한 항목의 확인 비율이며 접수 확인률이 아닙니다. 거리만 있으면 직선거리로 출퇴근을 참고 평가합니다.</p><div class="tags">'+(config.search_strategy?.additional_keywords||[]).map(k=>'<span class="tag">'+escapeHTML(k)+'</span>').join('')+'</div><p class="note">냉정역 좌표: <a href="https://www.openstreetmap.org/node/14102501783" target="_blank" rel="noopener noreferrer">© OpenStreetMap contributors</a> · 실제 근무지는 각 좌표 출처 참조</p>';}
$("cards").addEventListener("click",e=>{
 const btn=e.target.closest("button[data-action]");if(!btn)return;
 const id=btn.dataset.id,action=btn.dataset.action,key={favorite:"favorites",applied:"applied",hide:"hidden"}[action];if(!key)return;
 const arr=prefs[key],n=arr.indexOf(id);
 if(key==="hidden"&&n<0&&!confirm("이 브라우저에서 공고를 숨기시겠습니까?"))return;
 if(n<0)arr.push(id);else arr.splice(n,1);
 store(LOCAL_KEY,prefs);render();
});
document.querySelectorAll("[data-view]").forEach(b=>b.onclick=()=>{view=b.dataset.view;shown=0;document.querySelectorAll("[data-view]").forEach(x=>x.setAttribute("aria-pressed",String(x.dataset.view===view)));render()});
["search","region","role","sort","salaryOnly"].forEach(id=>$(id).addEventListener(id==="search"?"input":"change",()=>{shown=0;render()}));
$("more").addEventListener("click",()=>{shown+=PAGE_SIZE;render()});
async function loadData(){
 $("loadError").hidden=true;$("retry").disabled=true;
 try{
  const [jobs,meta,cfg,closed]=await Promise.all(["jobs","meta","search-config","closed-postings"].map(async name=>{const r=await fetch("./data/"+name+".json",{cache:"no-store"});if(!r.ok)throw Error(name);return r.json();}));
  if(!Array.isArray(jobs)||!cfg?.advisor_profile||!Array.isArray(closed?.postings))throw Error('invalid data');
  dataset=jobs;config=cfg;closedIds=new Set(closed.postings.map(p=>String(p.id)));
  $("review").textContent=meta.last_updated_at&&Number.isFinite(Date.parse(meta.last_updated_at))?"데이터 갱신 "+new Intl.DateTimeFormat("sv-SE",{timeZone:"Asia/Seoul",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).format(new Date(meta.last_updated_at))+" KST":"데이터 갱신 시각 미확인";
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

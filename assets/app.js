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
 const c=j.company_profile&&typeof j.company_profile==="object"?j.company_profile:{},source=R.safeUrl(c.source_url);
 const year=String(c.established||"").match(/(\d{4})년/);
 const tiles=[["기업형태",c.company_type],["사원수",c.employees],["매출액",c.revenue],["설립",year?year[1]+"년"+(c.company_age?" · "+c.company_age.replace(/^업력\s*/,""):""):""]].filter(x=>text(x[1]));
 // Manually sourced metrics that the company page does not provide (e.g. average salary).
 const extra=["avg_salary","operating_profit","recent_hires","recent_leavers"].filter(k=>R.metric(j,k)).map(k=>[metricNames[k],R.metric(j,k).value]);
 const cells=[...tiles,...extra].map(([name,value])=>'<div class="metric"><span>'+escapeHTML(name)+'</span><strong>'+escapeHTML(value)+'</strong></div>').join("");
 const rows=[["업종",c.industry||j.company_business],["사업내용",c.business],["홈페이지",c.homepage]].filter(x=>text(x[1])).map(([name,value])=>fact(name,value)).join("");
 const body=cells||rows?(cells?'<div class="business-metrics">'+cells+'</div>':'')+(rows?'<dl class="facts company-facts">'+rows+'</dl>':''):'<p class="section-text muted">기업정보 확인 중</p>';
 const note=source?'<small class="note">사람인 기업정보 · '+escapeHTML(c.checked_at||"")+' 확인 · <a href="'+escapeHTML(source)+'" target="_blank" rel="noopener noreferrer">출처</a></small>':'';
 return '<section class="card-section"><h3>회사 정보</h3>'+body+note+'</section>';
}
function commuteFact(j){
 const trip=R.transit(j,today),km=R.distance(j,profile());
 let value=trip?'대중교통 '+trip.minutes+'분'+(Number.isInteger(trip.transfers)?' · 환승 '+trip.transfers+'회':'')+' ('+trip.checked_at+' 확인)':km!==null?'직선 '+km.toFixed(1)+' km · 대중교통 시간 미확인':'냉정역 출발 · 거리·대중교통 시간 미확인';
 const source=km!==null?'<a class="map-link" href="'+escapeHTML(R.safeUrl(j.workplace_coordinates.source_url))+'" target="_blank" rel="noopener noreferrer">좌표 출처</a>':'';
 return '<div class="fact"><dt>출퇴근</dt><dd>'+escapeHTML(value)+(km!==null?(j.workplace_coordinates.precision==='posting_map'?' (공고 지도 기준)':' (건물 기준)'):'')+source+'</dd></div>';
}
const shortText=(x,n)=>{const v=text(x).replace(/\s+/g," ");return v.length>n?v.slice(0,n-1)+"…":v};
const monthDay=d=>d.slice(5).replace("-","/");
function deadlineLabel(j){
 if(R.validDate(j.deadline)){const days=Math.round((Date.parse(j.deadline)-Date.parse(today))/86400000);return {text:(days<=0?"오늘 마감":"D-"+days)+" · "+monthDay(j.deadline),soon:days<=7};}
 return {text:shortText(String(j.deadline_text||"").replace(/^~\s*/,"~"),16)||"확인 필요",soon:false};
}
// Saramin detail text packs sections and bullets into one line; break them for reading.
const readable=x=>String(x||"").replace(/\s*(📋|🎁)\s*/g,"\n").replace(/\s+(•|ㆍ|·\s)/g,"\n$1").replace(/\s+(\d+\)|\d+\.)\s/g,"\n$1 ").trim();
const cleanEmployment=x=>String(x||"").split(/\s*근무형태 상세보기|\s*상세보기/)[0];
const cleanBenefits=x=>String(x||"").replace(/^\s*🎁?\s*복지 및 혜택\s*/,"");
function card(j){
 const id=identity(j),fav=prefs.favorites.includes(id),applied=prefs.applied.includes(id),url=mobilePostingUrl(j),score=R.recommend(j,profile(),today).score,d=deadlineLabel(j);
 const meta=['<span class="brix">귤 당도 '+score+'브릭스</span>','<span class="meta'+(d.soon?' soon':'')+'"><b>마감</b> '+escapeHTML(d.text)+'</span>',R.validDate(j.posted_at)?'<span class="meta"><b>등록</b> '+escapeHTML(monthDay(j.posted_at))+'</span>':'',j.apply_route==="homepage"?'<span class="badge">홈페이지 지원</span>':'',isVerified(j)?'':'<span class="badge warn">접수 확인 중</span>'].filter(Boolean).join("");
 const duties=readable(j.duties),long=duties.length>260;
 return '<article class="card"><div class="card-top"><div><div class="company">'+escapeHTML(j.company)+'</div><div class="jobtitle">'+escapeHTML(j.title)+'</div></div><button type="button" class="favorite" data-action="favorite" data-id="'+escapeHTML(id)+'" aria-pressed="'+fav+'" title="관심 공고" aria-label="관심 공고">'+(fav?"★":"☆")+'</button></div>'+
 '<div class="card-meta">'+meta+'</div>'+
 '<dl class="facts">'+locationFact(j)+commuteFact(j)+fact("경력",label(j.experience,"경력요건 확인 필요"))+fact("고용형태",label(cleanEmployment(j.employment),"공고 확인"))+
 fact("근무시간",label(j.work_schedule,"원문 확인"))+fact("연봉",label(j.salary,"미공개"))+'<div class="fact"><dt>복지</dt><dd class="benefits">'+escapeHTML(label(readable(cleanBenefits(j.benefits)),"미공개"))+'</dd></div>'+fact("직무",label(j.category,"미분류"))+'</dl>'+
 '<section class="card-section"><h3>담당 업무</h3>'+(duties?'<p class="section-text duties'+(long?' clamped':'')+'">'+escapeHTML(duties)+'</p>'+(long?'<button type="button" class="text-button" data-action="expand">전체 보기</button>':''):'<p class="section-text muted">공고 원문에서 확인</p>')+'</section>'+
 metrics(j)+
 '<div class="card-actions"><a class="button primary apply" href="'+escapeHTML(url)+'" target="_blank" rel="noopener noreferrer">지원하기 ↗</a><button type="button" class="button small" data-action="applied" data-id="'+escapeHTML(id)+'">'+(applied?"지원 완료 ✓":"지원 표시")+'</button><button type="button" class="button small ghost" data-action="hide" data-id="'+escapeHTML(id)+'" title="이 브라우저에서 숨기거나 복구">'+(view==="hidden"?"복구":"숨김")+'</button></div></article>';
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
 if(btn.dataset.action==="expand"){const box=btn.previousElementSibling;box.classList.toggle("clamped");btn.textContent=box.classList.contains("clamped")?"전체 보기":"접기";return;}
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

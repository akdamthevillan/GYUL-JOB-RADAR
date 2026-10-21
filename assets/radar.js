/* Shared browser/Node domain logic. No network requests or persistent mutations. */
(function (root) {
  'use strict';
  const normalize = value => String(value ?? '').normalize('NFKC').toLowerCase().replace(/[\s()[\]\-_.·/]+/g, '');
  const day = (date = new Date()) => new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(date);
  const validDate = s => typeof s === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(s) && !Number.isNaN(Date.parse(s)) && new Date(s).toISOString().slice(0,10) === s;
  const minusDays = (s, n) => new Date(Date.parse(s+'T12:00:00Z') - n*86400000).toISOString().slice(0,10);
  const safeUrl = value => {try {const u=new URL(value); return u.protocol==='https:'&&!u.username&&!u.password?u.href:'';}catch{return '';}};
  const saraminUrl = value => {const s=safeUrl(value); if(!s)return ''; const u=new URL(s); return ['saramin.co.kr','www.saramin.co.kr','www2.saramin.co.kr','m.saramin.co.kr'].includes(u.host)?s:'';};
  const postingId = job => {try{const u=new URL(saraminUrl(job.url)); const id=u.searchParams.get('rec_idx'); return ['/zf_user/jobs/view','/job-search/view'].includes(u.pathname)&&/^\d{5,16}$/.test(id)?id:null;}catch{return null;}};
  const sourceMatches = (url,id) => !!id && postingId({url})===id;
  // Scheduled checks run every few hours, so a button seen today or yesterday (KST) is still current.
  const VERIFIED_WINDOW_DAYS=1;
  const freshCheck = (value,today) => validDate(value)&&value<=today&&value>=minusDays(today,VERIFIED_WINDOW_DAYS);
  function status(job, today=day()) {
    const closed=['마감','접수마감','채용마감','지원마감','closed'].includes(String(job.status||'').toLowerCase());
    const id=postingId(job);
    if(job.status==='verified_open'&&id&&String(job.id)===id&&freshCheck(job.verified_at,today)&&freshCheck(job.application_checked_at,today)&&job.application_button_state==='apply_enabled'&&['user_screenshot','browser_visual','page_dom'].includes(job.application_evidence_kind)&&String(job.verification_evidence||'').trim()&&sourceMatches(job.verified_source_url,id)) return 'verified_open';
    if(closed || job.application_button_state==='closed') return 'closed_by_ui';
    if(job.status==='expired'||(validDate(job.deadline)&&job.deadline<today))return 'expired_by_date';
    if(job.status==='recently_listed'&&validDate(job.listing_checked_at)&&job.listing_checked_at<=today&&job.listing_checked_at>=minusDays(today,3)&&String(job.listing_evidence||'').trim()&&validDate(job.deadline)&&job.deadline>=today)return 'recently_listed';
    return 'unknown';
  }
  function salary(job) {
    // Annual lower bound in 만원; never substitute company average salary.
    const s=String(job.salary||'').replace(/,/g,'');
    if(/시급|일급|주급|이하|미만/.test(s))return null;
    const match=s.match(/(연봉?|월급?)\s*(\d+(?:\.\d+)?)\s*(?:[~～–-]\s*\d+(?:\.\d+)?)?\s*만\s*원/);
    if(!match)return null;
    const value=Number(match[2])*(match[1].startsWith('월')?12:1);
    return value>0&&value<=100000?{value,converted:match[1].startsWith('월'),label:(match[1].startsWith('월')?'월급 × 12 환산 ':'공고 연봉 하한 ')+value.toLocaleString('ko-KR')+'만 원'}:null;
  }
  function metric(job,key){
    const m=job.company_info?.[key];
    return m&&safeUrl(m.source_url)&&(m.year||m.period||m.as_of)&&String(m.value??'').trim()?m:null;
  }
  function employees(job){
    const m=metric(job,'employees'); if(!m)return null;
    const value=String(m.value).replace(/,/g,'').trim();
    return /^\d+\s*명?$/.test(value)&&parseInt(value)>0?parseInt(value):null;
  }
  function coordinates(value){return value&&typeof value.lat==='number'&&typeof value.lng==='number'&&Number.isFinite(value.lat)&&Number.isFinite(value.lng)&&Math.abs(value.lat)<=90&&Math.abs(value.lng)<=180;}
  function distance(job,profile){
    const origin=profile?.commute?.origin_coordinates, dest=job.workplace_coordinates;
    if(!coordinates(origin)||!coordinates(dest)||!safeUrl(dest.source_url)||!validDate(dest.checked_at))return null;
    const rad=x=>x*Math.PI/180;
    const a=Math.sin(rad(dest.lat-origin.lat)/2)**2+Math.cos(rad(origin.lat))*Math.cos(rad(dest.lat))*Math.sin(rad(dest.lng-origin.lng)/2)**2;
    return 6371*2*Math.atan2(Math.sqrt(a),Math.sqrt(1-a));
  }
  function transit(job,today=day()){
    const t=job.commute;
    if(!t||t.origin!=='냉정역'||t.mode!=='transit'||typeof t.minutes!=='number'||!Number.isFinite(t.minutes)||t.minutes<=0||!safeUrl(t.source_url)||!validDate(t.checked_at)||t.checked_at>today||t.checked_at<minusDays(today,30))return null;
    return t;
  }
  const roleGroups=[
    {name:'유니폼·의류 그래픽',terms:['유니폼','워크웨어','의류그래픽','의류디자인','패션그래픽'],score:96,why:'유니폼 디자인 실무와 연결'},
    {name:'SNS·마케팅 디자인',terms:['sns디자인','sns디자이너','sns콘텐츠','콘텐츠디자인','콘텐츠디자이너','마케팅디자인','마케팅디자이너','카드뉴스','광고디자인','광고소재'],score:96,why:'SNS 디자인 실무와 연결'},
    {name:'브랜드·그래픽',terms:['브랜딩','브랜드디자인','브랜드디자이너','그래픽','시각디자인','시각디자이너','인하우스','로고'],score:94,why:'브랜드 콘셉트·로고 포트폴리오와 연결'},
    {name:'패키지',terms:['패키지','포장디자인'],score:94,why:'패키지 콘셉트·전개도 포트폴리오와 연결'},
    {name:'편집·인쇄',terms:['편집디자인','편집디자이너','인쇄','출판','북디자인','인디자인','indesign','브로슈어','카탈로그'],score:94,why:'책·브로슈어 편집 포트폴리오와 연결'},
    {name:'캐릭터·굿즈',terms:['캐릭터','굿즈','문구디자인','일러스트'],score:88,why:'캐릭터·굿즈 포트폴리오와 연결'},
    {name:'이커머스 디자인',terms:['상세페이지','웹디자인','웹디자이너','쇼핑몰디자인','배너'],score:80,why:'그래픽 역량 활용 가능 · 웹 실무 범위 확인'},
    {name:'콘텐츠·마케팅 기획',terms:['콘텐츠','sns','마케팅','마켓팅','브랜드기획','홍보'],score:70,why:'디자인·기획 경험 활용 가능 · 운영·성과분석 비중 확인'},
    {name:'MD·상품기획',terms:['md','상품기획','쇼핑몰','이커머스'],score:58,why:'확장 지원 분야 · 매입·재고·매출 관리 요건 확인'}
  ];
  function roleFit(job){
    const text=normalize([job.title,job.duties].filter(Boolean).join(' '));
    const hits=roleGroups.filter(g=>g.terms.some(t=>text.includes(normalize(t))));
    const best=hits.sort((a,b)=>b.score-a.score)[0];
    const warnings=[];
    if(/경력\s*[1-9]\d*\s*년|[1-9]\d*\s*년\s*이상/.test(job.experience||''))warnings.push('요구 경력과 현재 실무 약 3개월의 차이 확인');
    if(/퍼포먼스|ga4|roas|ui.?ux|퍼블리|프론트엔드|모션|영상편집|패턴|봉제/.test(normalize(job.title)))warnings.push('포트폴리오에서 확인되지 않은 전문 역량 요구 확인');
    let roleScore=best?.score??(/디자인|디자이너/.test(text)?75:35);
    if(/영상편집|모션|ui.?ux|퍼블리|프론트엔드|퍼포먼스|패턴|봉제|기계설계|인테리어|건축|cad/.test(normalize(job.title)))roleScore=Math.min(roleScore,55);
    return {score:roleScore,reason:best?.why??'상세 담당 업무를 확인해 적합성 판단 필요',groups:hits.map(g=>g.name),warnings};
  }
  function recommend(job,profile={},today=day()){
    const role=roleFit(job),pay=salary(job),trip=transit(job,today),km=distance(job,profile),size=employees(job);
    const b=String(job.benefits||'');
    const benefits=/미공개|미기재|확인 필요|원문 확인/.test(b)||!b?null:Math.min(100,40+['식사','식비','중식','유연','재택','교육','휴가','연차','야근수당'].filter(k=>b.includes(k)).length*10);
    const minimum=profile.salary_preference_manwon||3000;
    const scores={role:role.score,commute:trip?Math.max(0,100-trip.minutes):km===null?null:Math.max(0,100-km*3),salary:pay?Math.min(100,pay.value/minimum*80):null,benefits,size:size===null?null:Math.min(100,Math.log10(size+1)*30)};
    const weights=profile.weights||{role:40,commute:25,salary:20,benefits:10,size:5};
    let total=0,known=0,weightTotal=0;
    for(const [key,weight] of Object.entries(weights)){weightTotal+=weight;total+=(scores[key]??50)*weight;if(scores[key]!==null&&scores[key]!==undefined)known+=weight;}
    const notes=[role.reason,...role.warnings];
    if(pay)notes.push(pay.value>=minimum?'선호 연봉 '+minimum.toLocaleString('ko-KR')+'만 원 이상': '선호 연봉 미만 · 지원 대상에 포함');else notes.push('연봉 미공개·비교 불가');
    if(!trip)notes.push(km===null?'냉정역 기준 거리·대중교통 시간 미확인':'직선거리 기준 · 실제 통근 경로 확인 필요');
    return {score:Math.round(total/weightTotal),coverage:Math.round(known/weightTotal*100),notes,role,components:scores};
  }
  // Gyul-specific checks shown as one tangerine each on a card.
  function fit(job,profile={}){
    const items=[];
    if(/신입|경력\s*무관|무관/.test(String(job.experience||'')))items.push({key:'newbie',label:'신입 가능'});
    const minimum=profile.salary_preference_manwon||3000,pay=salary(job);
    if(pay&&pay.value>=minimum)items.push({key:'pay',label:'연봉 '+minimum.toLocaleString('ko-KR')+'↑'});
    if(roleFit(job).score>=88)items.push({key:'portfolio',label:'포트폴리오 연결'});
    const km=distance(job,profile);
    if(km!==null&&km<=(profile.commute?.near_km||8))items.push({key:'near',label:(profile.commute?.origin||'냉정역')+' 근처'});
    if(/정규직/.test(String(job.employment||'')))items.push({key:'fulltime',label:'정규직'});
    return items;
  }
  function compare(a,b,sort,profile,today=day()){
    const unknownLast=(x,y,descending=false)=>x===null?(y===null?0:1):y===null?-1:descending?y-x:x-y;
    let delta=0;
    if(sort==='salary')delta=unknownLast(salary(a)?.value??null,salary(b)?.value??null,true);
    else if(sort==='size')delta=unknownLast(employees(a),employees(b),true);
    else if(sort==='distance')delta=unknownLast(distance(a,profile),distance(b,profile));
    else if(sort==='transit')delta=unknownLast(transit(a,today)?.minutes??null,transit(b,today)?.minutes??null);
    else if(sort==='newest')delta=String(b.first_seen||'').localeCompare(String(a.first_seen||''));
    else if(sort==='deadline')delta=String(a.deadline||'9999').localeCompare(String(b.deadline||'9999'));
    else if(sort==='company')delta=String(a.company).localeCompare(String(b.company),'ko');
    else if(sort==='region'){
      const order=profile.priority_regions||[];
      const rank=j=>{const n=order.findIndex(r=>String(j.location||'').includes(r));return n<0?999:n;};delta=rank(a)-rank(b);
    }
    return delta||recommend(b,profile,today).score-recommend(a,profile,today).score||String(postingId(a)||a.id).localeCompare(String(postingId(b)||b.id));
  }
  function preferences(raw){const value=raw&&typeof raw==='object'?raw:{};return Object.fromEntries(['favorites','applied','hidden'].map(k=>[k,[...new Set(Array.isArray(value[k])?value[k].filter(x=>typeof x==='string'):[])]]));}
  const api={normalize,day,validDate,minusDays,safeUrl,saraminUrl,postingId,sourceMatches,status,salary,metric,employees,distance,transit,roleFit,recommend,fit,compare,preferences};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.GyulRadar=api;
})(typeof globalThis!=='undefined'?globalThis:this);

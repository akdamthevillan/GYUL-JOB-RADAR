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
  // Gyul prefers in-house consumer brands that sell their own goods online (kids, fashion, living, food brands…)
  // over agencies, print shops and staffing firms; marketing, MD and planning work there is welcome too.
  const ONLINE_SALES=/자사\s*몰|자체\s*몰|쇼핑몰|이커머스|e-?커머스|커머스|온라인\s*(md|몰|판매|스토어|사업|플랫폼|마케|쇼핑)|스마트\s*스토어|오픈\s*마켓|기획전|상세\s*페이지|전자\s*상거래|d2c|카페\s*24|cafe\s*24|메이크샵|고도몰/i;
  const OWN_BRAND=/자사\s*브랜드|자체\s*브랜드|브랜드\s*(md|마케|기획|운영|관리|콘텐츠|컨텐츠|디자인|디자이너|그래픽|웹)/i;
  const OWN_GOODS=/유아|육아|아기|베이비|키즈|아동|출산|패션|의류|어패럴|신발|잡화|스포츠|아웃도어|리빙|생활\s*용품|가구|홈\s*데코|침구|뷰티|화장품|코스메틱|식품|건강\s*기능|반려|펫|완구|문구|굿즈|주방|제조|도매|소매|유통|md|상품\s*기획|머천다이/i;
  const CLIENT_WORK=/대행|에이전시|agency|광고·홍보·전시|헤드\s*헌|서치펌|파견|아웃소싱|용역|인쇄|간판|광고물|현수막|명함|전단|판촉물|컨벤션|mice|pco|컨설팅|고용\s*알선|인력\s*공급|디자인업|디자인·설계/i;
  const STAFFING_NAME=/써치|서치|헤드헌팅|에이치알|(?<![a-z])hr(?![a-z])/i;
  // Business types that sell services rather than goods; a 소프트웨어 도매업 still sells goods.
  const SERVICE_BUSINESS=/임대|부동산|호텔|병원|의원|학원|여행|예식|공연|소프트웨어\s*개발|시스템\s*(통합|소프트웨어)|호스팅|건설|건축|조경|인테리어|실내|변리/;
  function companyTraits(postings){
    const text=postings.map(j=>[j.title,[].concat(j.job_sectors||[]).join(' '),j.company_business,j.duties].filter(Boolean).join(' ')).join(' ');
    // In-house brands' duties mention the printers and agencies they work with, so client work is read from names, titles and business types only.
    const self=postings.map(j=>[j.company,j.title,j.company_business].filter(Boolean).join(' ')).join(' ');
    return {online:ONLINE_SALES.test(text),brand:OWN_BRAND.test(text),goods:OWN_GOODS.test(text),
      client:CLIENT_WORK.test(self)||STAFFING_NAME.test(String(postings[0]?.company||'')),
      service:SERVICE_BUSINESS.test(postings.map(j=>j.company_business||'').join(' '))};
  }
  // 0–100, or null when the postings say nothing about what kind of company it is.
  function companyFit(job){
    const t=job.company_traits||companyTraits([job]);
    if(t.client)return 35;
    if(t.service)return null;
    return [null,68,88,95][[t.online,t.brand,t.goods].filter(Boolean).length];
  }
  // Company facts (employees, average salary) and traits found on one posting apply to the company's other postings.
  function shareCompanyInfo(jobs){
    const byCompany=new Map(),postings=new Map();
    for(const j of jobs){
      const key=normalize(j?.company);
      if(!key)continue;
      if(!postings.has(key))postings.set(key,[]);
      postings.get(key).push(j);
      if(j.company_info&&typeof j.company_info==='object'&&!Array.isArray(j.company_info))byCompany.set(key,{...byCompany.get(key),...j.company_info});
    }
    const traits=new Map([...postings].map(([key,list])=>[key,companyTraits(list)]));
    return jobs.map(j=>{
      const key=normalize(j?.company);
      if(!traits.has(key))return j;
      const shared=byCompany.get(key),own=j.company_info&&typeof j.company_info==='object'?j.company_info:{};
      const out={...j,company_traits:traits.get(key)};
      return shared&&Object.keys(shared).some(k=>!(k in own))?{...out,company_info:{...shared,...own}}:out;
    });
  }
  // Company-wide average salary in 만원 ("4,112만원"); only a hint when the posting hides pay.
  function averageSalary(job){
    const m=metric(job,'avg_salary'),v=m&&String(m.value).replace(/,/g,'').match(/(\d+)\s*만/);
    return v&&Number(v[1])>0&&Number(v[1])<100000?Number(v[1]):null;
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
    {name:'콘텐츠·마케팅 기획',terms:['콘텐츠','컨텐츠','sns','마케팅','마켓팅','마케터','마켓터','브랜드기획','홍보','인스타','유튜브','숏폼','바이럴','블로그'],score:70,why:'디자인·기획 경험 활용 가능 · 운영·성과분석 비중 확인'},
    {name:'MD·상품기획',terms:['md','상품기획','쇼핑몰','이커머스','스마트스토어','오픈마켓'],score:58,why:'확장 지원 분야 · 매입·재고·매출 관리 요건 확인'}
  ];
  const OPS_DUTIES=/택배|포장(?!디자인|디자이너)|출고|입고|재고|검수|피킹|주문처리|발주|cs응대|고객응대/;
  function roleFit(job){
    const text=normalize([job.title,job.duties,...[].concat(job.job_sectors||[])].filter(Boolean).join(' '));
    const hits=roleGroups.filter(g=>g.terms.some(t=>text.includes(normalize(t))));
    const best=hits.sort((a,b)=>b.score-a.score)[0];
    const warnings=[];
    if(/경력\s*[1-9]\d*\s*년|[1-9]\d*\s*년\s*이상/.test(job.experience||''))warnings.push('요구 경력과 현재 실무 약 3개월의 차이 확인');
    if(/퍼포먼스|ga4|roas|ui.?ux|퍼블리|프론트엔드|모션|영상편집|패턴|봉제/.test(normalize(job.title)))warnings.push('포트폴리오에서 확인되지 않은 전문 역량 요구 확인');
    let roleScore=best?.score??(/디자인|디자이너/.test(text)?75:35);
    // Several portfolio-strength groups at once (e.g. brand + editorial + SNS design) mean a closer match.
    if(hits.filter(g=>g.score>=88).length>=2)roleScore=Math.min(100,roleScore+4);
    // Packing, stock and order handling make it an operations job even when the title says 브랜드 디자인.
    if(OPS_DUTIES.test(text)){roleScore-=15;warnings.push('디자인 외 포장·재고·주문 처리 업무 포함 확인');}
    if(/영상편집|모션|ui.?ux|퍼블리|프론트엔드|퍼포먼스|패턴|봉제|기계설계|인테리어|건축|cad|캐드/.test(normalize(job.title)))roleScore=Math.min(roleScore,55);
    // Video, animation and 3D work is outside Gyul's field even when titled "디자이너"; mirrors VIDEO_* in scripts/auto_sync.py.
    const title=String(job.title||'');
    if(/영상\s*편집\s*pd|3d.*(캐드|cad)|(캐드|cad).*3d/i.test(title)||/영상|동영상|편집자|(?<![a-z])(pd|cg|vj)(?![a-z])|애니메이|3d|모델러|모션|촬영/i.test(title)&&!/디자인|디자이너|그래픽|일러스트|마케터|마케팅|쇼핑몰|상세\s*페이지|시각/.test(title.replace(/(영상|모션|3d|모델링|렌더링|유튜브)[^,/&]*(디자인|디자이너|그래픽|마케터|마케팅)/gi,' ')))roleScore=Math.min(roleScore,40);
    return {score:roleScore,reason:best?.why??'상세 담당 업무를 확인해 적합성 판단 필요',groups:hits.map(g=>g.name),warnings};
  }
  // Lower bound of the required experience in years; 0 for 신입/무관, null when unknown.
  // "경력(연수 무관)" asks for some experience of any length, so it is a quarter year, not 0.
  function experienceYears(job){
    const text=String(job.experience||'');
    if(/신입/.test(text))return 0;
    if(/(연수|년수)\s*무관/.test(text))return 0.25;
    if(/무관/.test(text))return 0;
    const m=text.match(/(\d+)\s*(?:~\s*\d+\s*)?년/);
    return m?Number(m[1]):/경력/.test(text)?2:null;
  }
  function experienceScore(job){
    const years=experienceYears(job);
    return years===null?null:years===0?100:years<1?90:years===1?80:years===2?65:years<5?50:25;
  }
  // Employment type and schedule: full-time weekday daytime work scores high.
  function conditionsScore(job){
    const kind=String(job.employment||''),hours=String(job.work_schedule||'');
    if(!/[가-힣]/.test(kind+hours)||/미확인|원문 확인|공고 확인/.test(kind+hours))return null;
    let score=50;
    if(/정규직/.test(kind))score+=25;
    if(/아르바이트|알바|파트|프리랜서|인턴|위촉/.test(kind))score-=25;else if(/계약직/.test(kind)&&!/정규직/.test(kind))score-=15;
    if(/주\s*5일/.test(hours))score+=15;
    if(/주\s*6일|토요일|교대|야간|주말/.test(hours))score-=20;
    if(/유연|탄력|재택|자율/.test(hours+kind))score+=10;
    return Math.max(0,Math.min(100,score));
  }
  const BENEFIT_TERMS=[/식대|식사|식비|중식|석식|간식/,/4대\s*보험/,/퇴직금|퇴직연금/,/상여|인센티브|성과급/,/연차|휴가|리프레시/,/교육|도서|자기계발/,/장비|툴|노트북|모니터/,/야근수당|초과근무수당/,/유연|재택|탄력/,/경조사|명절|생일/];
  function benefitsScore(job){
    const text=String(job.benefits||'');
    if(!text||/^\s*(미공개|미기재|확인 필요|원문 확인)/.test(text))return null;
    return Math.min(100,30+BENEFIT_TERMS.filter(re=>re.test(text)).length*10);
  }
  function commuteScore(job,profile,today){
    const trip=transit(job,today);
    if(trip)return Math.max(0,Math.min(100,110-trip.minutes*1.2));
    const km=distance(job,profile);
    return km===null?null:Math.max(0,Math.min(100,100-Math.max(0,km-3)*3.5));
  }
  const BRAND_ROLE_GROUPS=['콘텐츠·마케팅 기획','MD·상품기획'];
  function roleScore(job){
    const role=roleFit(job);
    // Tools from the portfolio (Photoshop, Illustrator, InDesign, Figma) in the duties add a little.
    const tools=/포토샵|photoshop|일러스트레이터|illustrator|인디자인|indesign|피그마|figma/i.test([job.title,job.duties].join(' '));
    let score=role.score;
    // At an in-house online brand, marketing, MD and planning roles rank close to design roles. Only postings whose
    // best match is such a role qualify, the packing penalty carries over, and video/3D postings capped at 40 stay down.
    if(score>40&&BRAND_ROLE_GROUPS.includes(role.groups[0])&&companyFit(job)>=88)score=Math.max(score,Math.min(94,score+36));
    return Math.min(100,score+(tools?5:0));
  }
  const DEFAULT_WEIGHTS={role:45,company:20,experience:10,salary:10,commute:5,conditions:5,benefits:3,size:2};
  function recommend(job,profile={},today=day()){
    const role=roleFit(job),pay=salary(job),trip=transit(job,today),km=distance(job,profile),size=employees(job);
    const minimum=profile.salary_preference_manwon||3000;
    const proxy=pay?null:averageSalary(job);
    const company=companyFit(job);
    const scores={role:roleScore(job),company,experience:experienceScore(job),salary:pay?Math.min(100,pay.value/minimum*80):proxy?Math.min(85,proxy*0.8/minimum*80):null,
      commute:commuteScore(job,profile,today),conditions:conditionsScore(job),benefits:benefitsScore(job),
      size:size===null?null:Math.min(100,Math.log10(size+1)*40)};
    const weights=profile.weights||DEFAULT_WEIGHTS;
    let total=0,known=0,weightTotal=0;
    // Unknown parts count as neutral 50 so missing data neither helps nor sinks a posting.
    for(const [key,weight] of Object.entries(weights)){weightTotal+=weight;total+=(scores[key]??50)*weight;if(scores[key]!==null&&scores[key]!==undefined)known+=weight;}
    const notes=[role.reason,...role.warnings];
    if(company!==null)notes.push(company>=88?'자사 브랜드·온라인 판매 회사':company<50?'대행·인쇄·인력 회사 · 자사 브랜드 실무 여부 확인':'자사 상품·브랜드 운영 여부 일부 확인');
    if(pay)notes.push(pay.value>=minimum?'선호 연봉 '+minimum.toLocaleString('ko-KR')+'만 원 이상': '선호 연봉 미만 · 지원 대상에 포함');else notes.push(proxy?'연봉 미공개 · 회사 평균연봉 '+proxy.toLocaleString('ko-KR')+'만 원 참고(80% 반영)':'연봉 미공개·비교 불가');
    if(!trip)notes.push(km===null?'냉정역 기준 거리·대중교통 시간 미확인':'직선거리 기준 · 실제 통근 경로 확인 필요');
    return {score:Math.round(total/weightTotal),coverage:Math.round(known/weightTotal*100),notes,role,components:scores};
  }
  // A street (…로/길 12) or lot (…동/읍/면 45-53, optionally 번지) address in the search area,
  // precise enough to open on a map; district-only locations return null.
  function mapAddress(location){
    const v=String(location||'').trim();
    if(!v||/확인 필요|미공개|주소 없음|미확인|정확하지 않음/.test(v))return null;
    const address=v.replace(/\s*\([^)]*\)/g,'').trim();
    const end='(?:번지)?(?:[\\s,]|$)';
    const street=new RegExp('(?:로|길|대로|번길)\\s*\\d+(?:-\\d+)?'+end).test(address);
    const lot=new RegExp('(?:동|읍|면|리)\\s+(?:산\\s*)?\\d+(?:-\\d+)?'+end).test(address);
    return /(부산|김해|양산)/.test(address)&&(street||lot)?address:null;
  }
  // Map search works best with the address up to its number; building names and floors confuse it.
  function mapQuery(location){
    const address=mapAddress(location);
    if(!address)return null;
    // A number followed by 번길 is part of the road name (본산로269번길), not the building number.
    const m=address.match(/^.*?(?:(?:로|길|대로|번길)\s*\d+(?:-\d+)?(?![\d-]|번길)|(?:동|읍|면|리)\s+(?:산\s*)?\d+(?:-\d+)?)(?:번지)?/);
    return m?m[0]:address;
  }
  // Gyul-specific checks shown as one tangerine each on a card.
  function fit(job,profile={}){
    const items=[];
    if(experienceYears(job)===0)items.push({key:'newbie',label:'신입 가능'});
    const minimum=profile.salary_preference_manwon||3000,pay=salary(job);
    if(pay&&pay.value>=minimum)items.push({key:'pay',label:'연봉 '+minimum.toLocaleString('ko-KR')+'↑'});
    if(roleFit(job).score>=88)items.push({key:'portfolio',label:'직무 적합'});
    const km=distance(job,profile);
    if(km!==null&&km<=(profile.commute?.near_km||8))items.push({key:'near',label:'출근 거리'});
    if(/정규직/.test(String(job.employment||'')))items.push({key:'fulltime',label:'정규직'});
    return items;
  }
  // scoreOf lets callers pass precomputed sweetness so large lists do not rescore per comparison.
  function compare(a,b,sort,profile,today=day(),scoreOf=null){
    const sweet=scoreOf||(j=>recommend(j,profile,today).score);
    const unknownLast=(x,y,descending=false)=>x===null?(y===null?0:1):y===null?-1:descending?y-x:x-y;
    let delta=0;
    if(sort==='salary')delta=unknownLast(salary(a)?.value??null,salary(b)?.value??null,true);
    else if(sort==='size')delta=unknownLast(employees(a),employees(b),true);
    else if(sort==='distance')delta=unknownLast(distance(a,profile),distance(b,profile));
    else if(sort==='transit')delta=unknownLast(transit(a,today)?.minutes??null,transit(b,today)?.minutes??null);
    // Saramin's posting date first; first_seen only says when the radar found it.
    else if(sort==='newest')delta=String(b.posted_at||b.first_seen||'').localeCompare(String(a.posted_at||a.first_seen||''));
    else if(sort==='deadline')delta=String(a.deadline||'9999').localeCompare(String(b.deadline||'9999'));
    else if(sort==='company')delta=String(a.company).localeCompare(String(b.company),'ko');
    else if(sort==='region'){
      const order=profile.priority_regions||[];
      const rank=j=>{const n=order.findIndex(r=>String(j.location||'').includes(r));return n<0?999:n;};delta=rank(a)-rank(b);
    }
    return delta||sweet(b)-sweet(a)||String(postingId(a)||a.id).localeCompare(String(postingId(b)||b.id));
  }
  function preferences(raw){const value=raw&&typeof raw==='object'?raw:{};return Object.fromEntries(['favorites','applied','hidden'].map(k=>[k,[...new Set(Array.isArray(value[k])?value[k].filter(x=>typeof x==='string'):[])]]));}
  const api={normalize,day,validDate,minusDays,safeUrl,saraminUrl,postingId,sourceMatches,status,salary,metric,averageSalary,shareCompanyInfo,companyFit,employees,distance,transit,roleFit,experienceYears,recommend,fit,mapAddress,mapQuery,compare,preferences};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.GyulRadar=api;
})(typeof globalThis!=='undefined'?globalThis:this);

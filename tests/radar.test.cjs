const {test}=require('node:test');
const assert=require('node:assert/strict');
const R=require('../assets/radar.js');
const cases=require('./fixtures/status-cases.json');
for(const c of cases)test('status: '+c.name,()=>assert.equal(R.status(c.job,c.today),c.expected));
const profile={salary_preference_manwon:3000,commute:{origin_coordinates:{lat:35.15,lng:129.01}}};
const job=(id,patch={})=>({id,url:'https://m.saramin.co.kr/job-search/view?rec_idx='+id,company:'회사',title:'SNS 디자이너',salary:'미공개',...patch});
test('salary lower bound, comma, monthly conversion and unknown',()=>{
 assert.equal(R.salary({salary:'연봉 3,000~4,000만원 협의'}).value,3000);
 assert.deepEqual(R.salary({salary:'월급 250만원 (주 40시간)'}).value,3000);
 assert.equal(R.salary({salary:'시급 10,320원'}),null);
 assert.equal(R.salary({salary:'면접 후 결정',company_info:{avg_salary:{value:'5000만원'}}}),null);
});
test('salary sort keeps lower salaries and puts missing last',()=>{
 const jobs=[job('11111'),job('22222',{salary:'연 2,700만원'}),job('33333',{salary:'연봉 3,000만원'})];
 jobs.sort((a,b)=>R.compare(a,b,'salary',profile));assert.deepEqual(jobs.map(j=>j.id),['33333','22222','11111']);
 assert.match(R.recommend(jobs[1],profile).notes.join(' '),/지원 대상에 포함/);
});
test('scale sort requires source and period, not average salary',()=>{
 const known=job('11111',{company_info:{employees:{value:'1,200명',year:'2025',source_url:'https://example.com/company'}}});
 const unknown=job('22222',{company_info:{employees:{value:'9999명'}}});
 assert.equal(R.employees(known),1200);assert.equal(R.employees(unknown),null);assert.ok(R.compare(known,unknown,'size',profile)<0);
});
test('real transit evidence only, no legacy guessed minutes',()=>{
 assert.equal(R.transit({transit_minutes:20,transit_checked_at:'2026-10-21'},'2026-10-21'),null);
 const commute={origin:'냉정역',mode:'transit',minutes:25,checked_at:'2026-10-21',source_url:'https://map.kakao.com/'};
 assert.equal(R.transit({commute},'2026-10-21').minutes,25);
 assert.equal(R.transit({commute:{...commute,checked_at:'2026-10-22'}},'2026-10-21'),null);
 assert.equal(R.transit({commute},'2026-12-21'),null);
});
test('distance calculation and unknown ordering',()=>{
 const a=job('11111',{workplace_coordinates:{lat:35.15,lng:129.02,source_url:'https://example.com/map',checked_at:'2026-10-21'}}),b=job('22222');
 assert.ok(R.distance(a,profile)>0.8&&R.distance(a,profile)<1);
 assert.equal(R.distance(b,profile),null);assert.ok(R.compare(a,b,'distance',profile)<0);
});
test('portfolio role relevance does not use historic arbitrary score',()=>{
 assert.ok(R.recommend(job('11111',{title:'유니폼 SNS 디자인',score:0}),profile).score>R.recommend(job('22222',{title:'창고 관리',score:999}),profile).score);
 assert.match(R.roleFit(job('11111',{experience:'경력 3년 이상'})).warnings.join(' '),/3개월/);
});
test('corrupt local storage preferences recover and preserve valid records',()=>{
 assert.deepEqual(R.preferences({favorites:'oops',applied:['r:11111','r:11111',3]}),{favorites:[],applied:['r:11111'],hidden:[]});
});
test('URLs require actual allowed host and numeric individual posting',()=>{
 assert.equal(R.postingId({url:'https://evil.example/?rec_idx=12345678'}),null);
 assert.equal(R.postingId({url:'https://m.saramin.co.kr/company?rec_idx=12345678'}),null);
 assert.equal(R.postingId({url:'https://user:password@m.saramin.co.kr/job-search/view?rec_idx=12345678'}),null);
});

test('video editing is not confused with print editorial design',()=>{
 assert.ok(R.roleFit(job('11111',{title:'편집 디자이너 InDesign'})).score>R.roleFit(job('22222',{title:'영상편집 담당'})).score);
 assert.ok(R.roleFit(job('33333',{title:'UI/UX 디자이너'})).score<=55);
 assert.equal(R.salary({salary:'연봉 3,000만원 이하'}),null);
});
test('gyul fit items for newcomer, pay, portfolio, nearby and full-time',()=>{
 const near={lat:35.155,lng:129.015,source_url:'https://example.com/map',checked_at:'2026-10-21'};
 const all=R.fit(job('11111',{title:'SNS 디자이너',experience:'신입·경력',salary:'연봉 3,200만원',employment:'정규직',workplace_coordinates:near}),profile);
 assert.deepEqual(all.map(x=>x.key),['newbie','pay','portfolio','near','fulltime']);
 assert.deepEqual(all.map(x=>x.label),['신입 가능','연봉 3,000↑','직무 적합','출근 거리','정규직']);
 assert.deepEqual(R.fit(job('22222',{title:'창고 관리',experience:'경력 3년↑',salary:'월급 200만원'}),profile),[]);
});
test('sweetness rewards newcomer-friendly, full-time weekday design work',()=>{
 assert.equal(R.experienceYears({experience:'신입·경력 1년 ↑'}),0);
 assert.equal(R.experienceYears({experience:'경력 3~10년'}),3);
 assert.equal(R.experienceYears({experience:'원문 확인'}),null);
 const base={title:'브랜드 디자이너',salary:'면접 후 결정'};
 const easy=R.recommend(job('11111',{...base,experience:'경력무관',employment:'정규직',work_schedule:'주 5일(월~금) 09:00~18:00'}),profile);
 const hard=R.recommend(job('22222',{...base,experience:'경력 5년↑',employment:'계약직',work_schedule:'주 6일 교대'}),profile);
 assert.ok(easy.score>hard.score+15);
 assert.equal(easy.components.experience,100);assert.equal(hard.components.experience,5);
 assert.ok(easy.components.conditions>hard.components.conditions);
 assert.equal(R.recommend(job('33333',{title:'쥬얼리 캐드 디자인'}),profile).components.role<=55,true);
});
test('map address accepts street, lot and 번지 forms but not districts',()=>{
 assert.equal(R.mapAddress('부산 금정구 남산동 45-53번지 아티스컴퍼니 2층'),'부산 금정구 남산동 45-53번지 아티스컴퍼니 2층');
 assert.ok(R.mapAddress('부산 남구 전포대로 116, 1층'));
 assert.ok(R.mapAddress('경남 김해시 진영읍 본산로269번길 62-4'));
 assert.ok(R.mapAddress('부산 해운대구 우동 1408 (센텀)'));
 assert.equal(R.mapAddress('부산 사하구'),null);
 assert.equal(R.mapAddress('서울 강남구 테헤란로 1'),null);
 assert.equal(R.mapAddress('정확한 근무지 주소 미확인'),null);
 assert.equal(R.mapQuery('부산 금정구 남산동 45-53번지 아티스컴퍼니 2층 아티스디자인'),'부산 금정구 남산동 45-53번지');
 assert.equal(R.mapQuery('부산 남구 전포대로 116, 1층'),'부산 남구 전포대로 116');
 assert.equal(R.mapQuery('경남 김해시 진영읍 본산로269번길 62-4'),'경남 김해시 진영읍 본산로269번길 62-4');
});
test('role fit recognizes marketer and store-operation titles',()=>{
 for(const title of ['온라인 검색광고 마케터','인스타그램 및 유튜브 채널 숏폼 제작자','마켓터 경력 채용','브랜드 스마트스토어 운영 담당자'])assert.ok(R.roleFit(job('11111',{title})).score>=50,title);
 for(const title of ['삼진어묵 매장기획팀 팀장','테넌트 관리 경력직 채용'])assert.ok(R.roleFit(job('22222',{title})).score<50,title);
});

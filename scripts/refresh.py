#!/usr/bin/env python3
"""Find public Saramin posting links in a search-engine RSS feed.
No Saramin page scraping, credential, or private applicant data.
Search-index results are candidates, NEVER verified live vacancies.
"""
import datetime as dt
import json
import re
import sys
import urllib.parse as up
import urllib.request as req
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
JOBS=ROOT/'data/jobs.json'
META=ROOT/'data/meta.json'
TZ=dt.timezone(dt.timedelta(hours=9))
QUERIES=[
 'site:saramin.co.kr/zf_user/jobs/view 부산 신입 디자이너',
 'site:saramin.co.kr/zf_user/jobs/view 부산 콘텐츠 마케팅',
 'site:saramin.co.kr/zf_user/jobs/view 부산 패키지 브랜드 디자인',
 'site:saramin.co.kr/zf_user/jobs/view 부산 상품기획 SNS',
 'site:saramin.co.kr/zf_user/jobs/relay/view 부산 그래픽 디자이너',
]
WORDS=('디자인','디자이너','마케팅','콘텐츠','컨텐츠','기획','md','브랜드','SNS','GTQ','포토샵')
MAX_NEW=80

def posting_url(url):
    try:
        p=up.urlsplit(url)
        if p.hostname not in ('saramin.co.kr','www.saramin.co.kr','www2.saramin.co.kr'):
            return None
        ids=up.parse_qs(p.query).get('rec_idx',[])
        if not ids or not re.fullmatch(r'\d{5,16}',ids[0]):return None
        return 'https://www.saramin.co.kr/zf_user/jobs/view?rec_idx='+ids[0]
    except (ValueError,TypeError):return None

def category(t):
    x=t.lower()
    if any(w in x for w in ('디자인','디자이너','그래픽','포토샵','illustrator')):return '디자인'
    if any(w in x for w in ('상품기획','쇼핑몰',' md','머천다이징')):return 'MD·상품기획'
    return '마케팅·기획'

def items_for_query(q):
    endpoint='https://www.bing.com/search?'+up.urlencode({'q':q,'format':'rss'})
    request=req.Request(endpoint,headers={'User-Agent':'Mozilla/5.0 (compatible; GYUL-Radar/1.0)','Accept':'application/rss+xml, application/xml'})
    with req.urlopen(request,timeout=18) as response:
        raw=response.read(900000)
    root=ET.fromstring(raw)
    if root.tag!='rss':raise ValueError('RSS feed unavailable')
    return [(i.findtext('title') or '', i.findtext('link') or '', i.findtext('description') or '') for i in root.findall('./channel/item')]

def collect(now):
    new={}
    failures=0
    for query in QUERIES:
        try:found=items_for_query(query)
        except Exception as e:
            print('RSS query failed:',type(e).__name__,file=sys.stderr)
            failures+=1
            continue
        for title,link,desc in found:
            # No quoted source content is reproduced: only a brief search label.
            url=posting_url(link)
            if not url:continue
            identifier=up.parse_qs(up.urlsplit(url).query)['rec_idx'][0]
            combined=(title+' '+desc).lower()
            if not any(x.lower() in combined for x in WORDS):continue
            # Can't independently establish actual work site or current application status.
            # Store a candidate with explicitly unverified area and deadline.
            title=re.sub(r'\s*[-|]\s*(사람인|saramin).*$', '',title,flags=re.I)
            title=re.sub(r'\s+',' ',title).strip()[:110]
            if not title:continue
            new[identifier]=dict(id=identifier,company='공고 원문 확인',title=title,
                location='부산 검색 결과 · 실제 근무지 확인',
                salary='미공개 · 원문 확인',benefits='원문 확인',
                considerations='검색 색인에 표시된 공고입니다. 부산 근무지·채용 여부·자격요건을 원문에서 확인하세요.',
                experience='원문 확인',status='재확인 필요',
                deadline=None,deadline_text='확인 필요',url=url,source='사람인',
                category=category(title),score=45,origin='검색 색인',
                first_seen=now.date().isoformat(),last_seen=now.date().isoformat())
            if len(new)>=MAX_NEW:break
    return new,failures

def main():
    now=dt.datetime.now(TZ)
    jobs=json.loads(JOBS.read_text('utf8'))
    meta=json.loads(META.read_text('utf8'))
    detected,failures=collect(now)
    if detected:
        current={str(j['id']):j for j in jobs}
        for key,item in detected.items():
            if key in current:
                current[key]['last_seen']=now.date().isoformat()
                # Search indexing does not change status to "open".
            else:current[key]=item
        jobs=list(current.values())
        jobs.sort(key=lambda x:(x.get('status')=='마감' or bool(x.get('deadline') and x['deadline']<now.date().isoformat()),-int(x.get('score') or 0)))
        JOBS.write_text(json.dumps(jobs[:550],ensure_ascii=False,indent=2)+'\n','utf8')
        meta.update(mode='index',last_success=now.isoformat(timespec='seconds'),last_attempt=now.isoformat(timespec='seconds'),last_error=None,found_count=len(detected),search_errors=failures)
        print('RSS search candidates:',len(detected),'query errors:',failures)
    else:
        meta.update(mode='error',last_attempt=now.isoformat(timespec='seconds'),last_error='검색 RSS 결과 없음 또는 수집 불가',search_errors=failures)
        print('No candidates retrieved: existing data unchanged',file=sys.stderr)
    META.write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n','utf8')
    return 0

if __name__=='__main__':
    raise SystemExit(main())

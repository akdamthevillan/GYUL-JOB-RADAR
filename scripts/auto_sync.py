#!/usr/bin/env python3
"""Scheduled Saramin sync for GYUL JOB RADAR.

Discovery reads public occupation-category listings for the configured regions.
Status reads each individual public posting page and judges its application
control with inspect_html. Low request rate, no login, never clicks or applies.
Network or parsing failures never close or delete a posting; they are retried
on the next run.
"""
import datetime as dt
import html as html_lib
import http.client
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from cleanup import CLOSED, JOBS, posting_id, write_if_changed
from inspect_html import inspect_html
from observations import merge_observations, parse_observations
from status_rules import KST, effective_status, saramin_url

CONFIG = JOBS.parent / 'search-config.json'
LEDGER = JOBS.parent / 'observations.json'
USER_AGENT = 'GYUL-JOB-RADAR personal posting review (github.com/akdamthevillan/GYUL-JOB-RADAR)'
LIST_URL = 'https://www.saramin.co.kr/zf_user/jobs/list/job-category'
POSTING_URL = 'https://www.saramin.co.kr/zf_user/jobs/view?rec_idx={}'
COMPANY_URL = 'https://www.saramin.co.kr/zf_user/company-info/view?csn={}'
REGION_WORDS = ('부산', '김해', '양산')
PLACEHOLDERS = ('미확인', '미공개', '확인 필요', '원문 확인', '공고 확인')
OBSERVATION_BATCH = 80
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}
DEFAULTS = {'page_size': 100, 'max_list_pages': 40, 'max_detail_checks': 50,
            'request_delay_seconds': 1.5, 'recheck_after_hours': 20, 'detail_refresh_days': 7,
            'max_consecutive_failures': 8, 'time_budget_seconds': 1500,
            'max_company_checks': 30, 'company_recheck_days': 30}


class ListingParser(HTMLParser):
    """Rows of one occupation-category listing page (div.list_item#rec-<id>)."""

    def __init__(self):
        super().__init__()
        self.stack, self.rows = [], []
        self.row, self.depth, self.field = None, 0, None

    def handle_starttag(self, tag, attributes):
        # Valueless attributes (e.g. <div style>) arrive as None.
        attrs = {key: value or '' for key, value in attributes}
        classes = set(attrs.get('class', '').split())
        if tag not in VOID:
            self.stack.append((tag, classes))
        match = re.fullmatch(r'rec-(\d{5,16})', attrs.get('id', ''))
        if tag == 'div' and 'list_item' in classes and match:
            self.row = {'id': match[1], 'company': '', 'company_url': '', 'title': '', 'sectors': [],
                        'work_place': '', 'career': '', 'education': '', 'apply': '', 'apply_id': '',
                        'date': '', 'registered': ''}
            self.depth = len(self.stack)
            return
        if not self.row:
            return
        inside = {c for _, group in self.stack for c in group}
        href = attrs.get('href', '')
        # Companies without a public page show their name in a <span> instead of a link.
        if 'company_nm' in inside and 'str_tit' in classes and not self.row['company']:
            if tag == 'a' and href.startswith('/zf_user/company-info/'):
                self.row['company_url'] = 'https://www.saramin.co.kr' + href
            self.field = 'company'
        elif tag == 'button' and 'company_nm' in inside and attrs.get('csn') and not self.row['company_url']:
            self.row['company_url'] = COMPANY_URL.format(urllib.parse.quote(attrs['csn'], safe='=+/'))
        elif tag == 'a' and 'job_tit' in inside and attrs.get('title'):
            self.row['title'] = attrs['title'].strip()
        elif tag == 'span' and 'job_sector' in inside:
            self.row['sectors'].append('')
            self.field = 'sector'
        elif tag == 'p' and classes & {'work_place', 'career', 'education'}:
            self.field = next(iter(classes & {'work_place', 'career', 'education'}))
        elif tag == 'span' and classes & {'date', 'deadlines'}:
            self.field = 'date' if 'date' in classes else 'registered'
        elif tag in {'button', 'a'} and 'support_info' in inside:
            # Quick-apply buttons name the posting in onclick; homepage-apply links in href.
            match = re.search(r"quickApply\w*\(\s*['\"](\d+)['\"]", attrs.get('onclick', '')) or re.search(r'rec_idx=(\d+)', href)
            self.row['apply_id'] = match[1] if match else ''
            self.field = 'apply'

    def handle_data(self, value):
        if not self.row or not self.field:
            return
        if self.field == 'sector':
            self.row['sectors'][-1] += value
        else:
            self.row[self.field] += value

    def handle_endtag(self, tag):
        if self.field and tag in {'a', 'span', 'p', 'button'}:
            self.field = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                if self.row and i + 1 <= self.depth:
                    self.finish_row()
                del self.stack[i:]
                break

    def finish_row(self):
        # Saramin double-escapes some titles ("R&amp;amp;D"); unescape once more after parsing.
        row = {k: (html_lib.unescape(re.sub(r'\s+', ' ', v).strip()) if isinstance(v, str) else v) for k, v in self.row.items()}
        row['sectors'] = [s for s in (re.sub(r'\s+', ' ', x).strip() for x in row['sectors']) if s and s != '외']
        if row['title'] and row['company']:
            self.rows.append(row)
        self.row = None


def parse_listing(html):
    """Return (total result count or None, rows) for one listing page."""
    total = re.search(r'total_count"\s*>\s*<em>\s*([\d,]+)', html)
    parser = ListingParser()
    parser.feed(html)
    return (int(total[1].replace(',', '')) if total else None), parser.rows


TITLE_CATEGORIES = (
    ('디자인', r'디자인|디자이너|그래픽|일러스트|편집\s*디자'),
    ('콘텐츠·SNS', r'SNS|콘텐츠|컨텐츠|유튜브|인스타|블로그|에디터'),
    ('브랜드·상품기획', r'(?<![A-Za-z])MD(?![A-Za-z])|상품\s*기획|머천다이|브랜드'),
    ('온라인·디지털 운영', r'온라인|쇼핑몰|이커머스|오픈마켓|스마트스토어|자사몰'),
    ('마케팅·기획', r'마케팅|마케터|마켓팅|마켓터|홍보|광고|(행사|이벤트|전시|축제|공연|문화|콘텐츠|컨텐츠|브랜드|상품|광고|홍보|마케팅)\s*기획|MICE'),
    ('창작·영상', r'웹툰|만화|애니메이|작가|카피\s*라이터|영상|촬영|사진|포토|모션|3D|모델러'),
)
# Tags alone count only when they name creative work; generic 마케팅/기획 tags are too broad.
RELATED_SECTORS = r'디자인|디자이너|그래픽|일러스트|SNS|콘텐츠|컨텐츠|영상|브랜딩|편집'
DESIGN_SECTORS = r'디자인|디자이너|그래픽|일러스트|편집'
SUPPORT_TITLE = r'콜센터|고객센터|텔레마케|채팅\s*상담|상담원|상담사|인바운드|아웃바운드|(?<![A-Za-z])(TM|CS|AE)(?![A-Za-z])|영업|세일즈|환자\s*유치'
# Work Gyul cannot take on even when the title also says 마케팅 or 쇼핑몰.
HANDS_ON_TITLES = (
    ('판매·매장', r'판매|매장|백화점|(?<!스마트)스토어|샵\s*마스터|점장|(?<![A-Za-z])SV(?![A-Za-z])|슈퍼바이저|R&D|파트너십|제휴|가맹|지역\s*매니저'),
    ('기타', r'알바|아르바이트|파트\s*타임|메이크업|헤어|네일|에스테틱'),
    ('물류·운송·서비스', r'포장|물류|외근'),
    ('의료·교육', r'강사'),
    ('IT·개발', r'개발자|\(개발\)|빌더|퍼블리셔'),
    ('설계·생산·기술', r'소싱|생산'),
)
OFFICE_TITLE = r'사무\s*(직|보조|행정)|경리|회계|총무|사업\s*기획|경영|전략\s*기획|재무|(IT|기술|서비스)\s*기획|수주|무역|가이드|통역'
CREATIVE_TITLE = r'디자인|디자이너|콘텐츠|컨텐츠|SNS|일러스트|영상|그래픽'
SPACE_TITLE = r'인테리어|실내\s*(건축|디자인|디자이너)|건축|공간\s*디자|가구|조경|시공|감리|현장\s*(관리|소장|팀|기사)|목수|목공|설치\s*기사|도배|(?<!텍스)타일|도장공'
VIDEO_TITLE = r'영상|동영상|편집자|(?<![A-Za-z])(PD|CG|VJ)(?![A-Za-z])|애니메이|3D|모델러|모션|촬영'
VIDEO_PHRASE = r'(영상|모션|3D|모델링|렌더링|유튜브)[^,/&]*(디자인|디자이너|그래픽|마케터|마케팅)'
VIDEO_ONLY_TITLE = r'영상\s*편집\s*PD|3D.*(캐드|CAD)|(캐드|CAD).*3D'
VIDEO_KEEP_TITLE = r'디자인|디자이너|그래픽|일러스트|마케터|마케팅|쇼핑몰|상세\s*페이지|시각'
MARKETING_TITLE = r'마케팅|마케터|콘텐츠|컨텐츠|SNS|그래픽|시각|브랜드|편집\s*디자|웹'
# Postings outside Gyul's field still get a concrete group so they can be filtered out.
OTHER_CATEGORIES = (
    ('영업·고객상담', r'영업|세일즈|거래처|(?<![A-Za-z])(CS|TM)(?![A-Za-z])|상담|콜센터|고객센터|인바운드|아웃바운드'),
    ('판매·매장', r'판매|매장|스토어|샵마스터|슈퍼바이저|(?<![A-Za-z])SV(?![A-Za-z])|백화점|캐셔|점장|스태프'),
    ('사무·경영지원', r'사무|총무|경리|회계|세무|재무|경영\s*지원|경영\s*관리|인사|노무|비서|행정|서무|무역|구매|자재|사업\s*관리|컨설|원가|입찰|(?<![A-Za-z])PM(?![A-Za-z])'),
    ('IT·개발', r'개발|프론트|백엔드|서버|네트워크|데이터|정보\s*보안|(?<![A-Za-z])(ERP|SAP|AI|IT|SE)(?![A-Za-z])|엔지니어'),
    ('설계·생산·기술', r'설계|CAD|캐드|R&D|연구|생산|품질|기계|전기|전자|인테리어|현장|공정|시공|정비|기술'),
    ('물류·운송·서비스', r'물류|배송|택배|운송|기사|지게차|창고|바리스타|홀|식당|조리|서빙|호텔'),
    ('의료·교육', r'간호|병원|의료|약사|치과|피부과|교육|강사|교사|튜터'),
)


def category_for(title, sectors, listing_category):
    """Map a posting onto the dashboard's category names.

    Saramin listings also carry postings that only tag a related keyword, so the
    title decides first and unrelated postings fall into '기타' instead of a
    misleading category.
    """
    # Call-center and TM postings often say "마케팅" or "쇼핑몰" but are phone/chat support work.
    if re.search(SUPPORT_TITLE, title, re.I) and not re.search(CREATIVE_TITLE, title, re.I):
        return '영업·고객상담'
    # Saramin's design category also lists interior, architecture and site/installation work.
    if re.search(SPACE_TITLE, title, re.I) and not re.search(MARKETING_TITLE, title, re.I):
        return '인테리어·건축·시공'
    # Video, animation and 3D are outside Gyul's skills unless the role is design or marketing work.
    # "영상 디자이너", "영상마케터" or "3D 모델링·렌더링 디자이너" is still video/3D work, so those phrases do not count.
    if re.search(VIDEO_ONLY_TITLE, title, re.I) or (
            re.search(VIDEO_TITLE, title, re.I) and not re.search(VIDEO_KEEP_TITLE, re.sub(VIDEO_PHRASE, ' ', title, flags=re.I), re.I)):
        return '창작·영상'
    if not re.search(CREATIVE_TITLE, title, re.I):
        for name, pattern in (('사무·경영지원', OFFICE_TITLE),) + HANDS_ON_TITLES:
            if re.search(pattern, title, re.I):
                return name
    for name, pattern in TITLE_CATEGORIES + OTHER_CATEGORIES:
        if re.search(pattern, title, re.I):
            return name
    tags = ' '.join(sectors)
    if re.search(RELATED_SECTORS, tags, re.I):
        return '디자인' if re.search(DESIGN_SECTORS, tags, re.I) else '콘텐츠·SNS'
    for name, pattern in OTHER_CATEGORIES:
        if re.search(pattern, tags, re.I):
            return name
    return '기타'


def prune_unrelated(jobs, focus):
    """Drop auto-discovered postings outside Gyul's field; curated records are kept.

    They are not closed postings, so nothing is written to the closure ledger and the
    listing simply skips them on later runs.
    """
    kept = [job for job in jobs if job.get('discovered_by') != 'auto_sync' or job.get('category') in focus]
    removed = len(jobs) - len(kept)
    jobs[:] = kept
    return removed


def recategorize(jobs, settings):
    """Re-apply category_for to auto-discovered postings so rule changes reach stored data."""
    names = {str(c['code']): c['name'] for c in settings['categories']}
    changed = 0
    for job in jobs:
        if job.get('discovered_by') != 'auto_sync':
            continue
        code = urllib.parse.parse_qs(urllib.parse.urlsplit(str(job.get('listing_source_url') or '')).query).get('cat_mcls', [''])[0]
        sectors = [s.strip() for s in str(job.get('job_sectors') or '').split(',') if s.strip()]
        title = html_lib.unescape(str(job.get('title') or ''))
        if title != job.get('title'):
            job['title'] = title
        category = category_for(title, sectors, names.get(code, ''))
        if job.get('category') != category:
            job['category'] = category
            changed += 1
    return changed


def short(value, limit):
    value = re.sub(r'\s+', ' ', str(value or '')).strip()
    return value if len(value) <= limit else value[:limit - 1] + '…'


def placeholder(value):
    return not str(value or '').strip() or any(word in str(value) for word in PLACEHOLDERS)


def parse_time(value):
    try:
        stamp = dt.datetime.fromisoformat(str(value))
        return stamp if stamp.tzinfo else None
    except ValueError:
        return None


ACTIVE_LISTING_BUTTONS = {'입사지원': 'saramin', '홈페이지 지원': 'homepage'}


def listing_deadline(text, today):
    """ISO deadline from a listing date such as '~11.20(금)' or 'D-5'; None for 상시/채용시."""
    match = re.search(r'D-(\d{1,3})', text)
    if match:
        return (today + dt.timedelta(days=int(match[1]))).isoformat()
    if re.search(r'오늘\s*마감', text):
        return today.isoformat()
    if re.search(r'내일\s*마감', text):
        return (today + dt.timedelta(days=1)).isoformat()
    match = re.search(r'~\s*(\d{1,2})\.(\d{1,2})', text)
    if not match:
        return None
    try:
        date = dt.date(today.year, int(match[1]), int(match[2]))
    except ValueError:
        return None
    # Listings show no year; a month/day already passed belongs to next year.
    if date < today - dt.timedelta(days=1):
        try:
            date = date.replace(year=today.year + 1)
        except ValueError:
            return None
    return date.isoformat()


def listing_posted(text, today):
    match = re.search(r'(\d{1,3})일\s*전\s*등록', text)
    if match:
        return (today - dt.timedelta(days=int(match[1]))).isoformat()
    return today.isoformat() if re.search(r'(분|시간)\s*전\s*등록', text) else None


def listing_evidence(row):
    return short(f"자동 점검: {row.get('region', '')} {row.get('listing_category', '')} 직종 목록에서 "
                 f"공고번호 일치 '{row['apply']}' 버튼 활성", 300)


def apply_listing(jobs, closed_ids, listed, now, focus=None):
    """Confirm postings whose listing row shows an active apply control; add new ones.

    The listing row's control is bound to the same posting number (apply_id), so it is
    the posting's live application button as rendered on Saramin's own listing page.
    New postings are added only when their category is in ``focus`` (None allows all).
    Returns (verified, added).
    """
    today = now.date().isoformat()
    stamp = now.isoformat(timespec='seconds')
    index = {posting_id(job): i for i, job in enumerate(jobs) if posting_id(job)}
    verified = added = 0
    for pid, row in listed.items():
        route = ACTIVE_LISTING_BUTTONS.get(row.get('apply'))
        if pid in closed_ids or not route or row.get('apply_id') != pid:
            continue
        url = POSTING_URL.format(pid)
        state = {'status': 'verified_open', 'verified_at': today, 'verified_source_url': url,
                 'verification_evidence': listing_evidence(row), 'application_button_state': 'apply_enabled',
                 'application_evidence_kind': 'page_dom', 'application_evidence_page': row.get('source_url', ''),
                 'application_checked_at': today, 'listing_seen_at': today, 'listing_checked_at': today,
                 'last_checked_at': stamp, 'last_check_result': 'apply_enabled', 'apply_route': route}
        if pid in index:
            jobs[index[pid]] = dict(jobs[index[pid]], **state)
            verified += 1
            continue
        if focus is not None and row.get('category') not in focus:
            continue
        # Listing facts only; the posting page fills address, pay, hours and duties later.
        job = {'id': pid, 'url': url, 'source': '사람인', 'company': row['company'], 'title': row['title'],
               'category': row.get('category') or '기타', 'location': row['work_place'] or '정확한 근무지 주소 미확인',
               'experience': row['career'] or '원문 확인', 'first_seen': today, 'discovered_by': 'auto_sync',
               'listing_source_url': row.get('source_url', ''), 'job_sectors': short(', '.join(row['sectors']), 200)}
        if row.get('company_url'):
            job['company_url'] = row['company_url']
        if row.get('date'):
            job['deadline_text'] = short(row['date'], 60)
            deadline = listing_deadline(row['date'], now.date())
            if deadline:
                job['deadline'] = deadline
        posted = listing_posted(row.get('registered', ''), now.date())
        if posted:
            job['posted_at'] = posted
        job.update(state)
        index[pid] = len(jobs)
        jobs.append(job)
        added += 1
    return verified, added


def plan_checks(jobs, closed_ids, listed, listings_complete, now, settings):
    """Order posting pages to open this run.

    1. Jobs once seen in a listing but missing now (probably closed).
    2. Listed jobs whose details were never read, newest listing first.
    3. Jobs outside the category listings that are not currently verified or are due.
    4. Listed jobs whose details are older than detail_refresh_days.
    """
    refresh_before = (now.date() - dt.timedelta(days=settings['detail_refresh_days'])).isoformat()
    due_before = now - dt.timedelta(hours=settings['recheck_after_hours'])
    never = dt.datetime(2000, 1, 1, tzinfo=KST)
    order = {pid: i for i, pid in enumerate(listed)}
    suspects, fresh, unlisted, stale = [], [], [], []
    for job in jobs:
        pid = posting_id(job)
        if not pid or pid in closed_ids:
            continue
        details = job.get('details_checked_at') or ''
        checked = parse_time(job.get('last_checked_at')) or never
        if pid in listed:
            if not details:
                fresh.append((order[pid], pid))
            elif details < refresh_before:
                stale.append((details, pid))
        elif listings_complete and job.get('listing_seen_at'):
            suspects.append((checked, pid))
        elif effective_status(job, now.date()) != 'verified_open' or checked < due_before:
            # Postings outside the category listings only get a status from their own page.
            unlisted.append((checked, pid))
    plan = [pid for _, pid in sorted(suspects) + sorted(fresh) + sorted(unlisted) + sorted(stale)]
    return list(dict.fromkeys(plan))[:settings['max_detail_checks']]


def evidence_text(outcome):
    controls = [c for c in outcome.get('controls', []) if not c.get('hidden')]
    names = ', '.join(sorted({c['text'] for c in controls if c.get('text')})) or '지원 컨트롤 없음'
    if outcome['result'] == 'apply_enabled':
        return short(f"자동 점검: 공고번호 일치 지원 버튼 활성 ({names})", 300)
    if outcome['result'] == 'closed':
        return short(f"자동 점검: 마감 안내 또는 접수마감 컨트롤 확인 ({names})", 300)
    return short(f"자동 점검: 지원 상태 판독 불가 ({names})", 300)


def fill_details(record, details, url, today, overwrite):
    """Copy fields read from the posting page; keep confirmed manual values unless asked."""
    limits = {'location': 200, 'salary': 200, 'experience': 200, 'employment': 200, 'work_schedule': 200,
              'application_method': 200, 'company_business': 200, 'benefits': 300, 'duties': 700}
    for key, limit in limits.items():
        value = details.get(key)
        if value and (overwrite or placeholder(record.get(key))):
            record[key] = short(value, limit)
    if details.get('deadline'):
        record['deadline'] = details['deadline']
    if details.get('posted_at') and (overwrite or not record.get('posted_at')):
        record['posted_at'] = details['posted_at']
    point = details.get('workplace_coordinates')
    if point and (overwrite or not record.get('workplace_coordinates')):
        record['workplace_coordinates'] = dict(point, source_url=url, checked_at=today)


def apply_outcome(jobs, closed, pid, outcome, now, observations):
    """Apply one inspected posting page. Returns 'verified', 'closed' or 'unknown'."""
    today = now.date().isoformat()
    stamp = now.isoformat(timespec='seconds')
    url = POSTING_URL.format(pid)
    index = next((i for i, job in enumerate(jobs) if posting_id(job) == pid), None)
    if index is None:
        return 'unknown'
    result = outcome['result']
    if result == 'closed':
        job = jobs.pop(index)
        closed['postings'].append({
            'id': pid, 'closed_confirmed': today,
            'reason': '접수마감 확인: 자동 점검에서 마감 안내 또는 접수마감 컨트롤 확인',
            'evidence_url': url, 'application_button_state': 'closed', 'application_evidence_kind': 'page_dom',
            'application_checked_at': today, 'closure_kind': 'closed_by_ui',
            'snapshot': {k: job.get(k) for k in ('company', 'title', 'location', 'category', 'salary',
                                                  'deadline', 'deadline_text', 'first_seen', 'url')
                         if job.get(k) is not None}})
        observations.append({'id': pid, 'source_url': url, 'observed_at': stamp, 'result': 'closed',
                             'method': 'page_dom', 'evidence': evidence_text(outcome)})
        return 'closed'
    job = dict(jobs[index])
    details = outcome.get('details', {})
    if details:
        # Auto-discovered records start from rough listing values that the page supersedes.
        fill_details(job, details, url, today, overwrite=job.get('discovered_by') == 'auto_sync')
        job['details_checked_at'] = today
    if result == 'apply_enabled':
        job.update({'status': 'verified_open', 'verified_at': today, 'verified_source_url': url,
                    'verification_evidence': evidence_text(outcome), 'application_button_state': 'apply_enabled',
                    'application_evidence_kind': 'page_dom', 'application_evidence_page': url,
                    'application_checked_at': today, 'source_checked_at': today, 'last_checked_at': stamp,
                    'last_check_result': 'apply_enabled', 'apply_route': outcome.get('apply_route') or 'saramin'})
        jobs[index] = job
        return 'verified'
    job.update(last_checked_at=stamp, last_check_result='unknown')
    jobs[index] = job
    return 'unknown'


class CompanyParser(HTMLParser):
    """Summary tiles and definition rows of a public company-info page."""

    def __init__(self):
        super().__init__()
        self.tiles, self.rows = [], []
        self.field, self.dl_key = None, ''

    def handle_starttag(self, tag, attributes):
        classes = set(dict((k, v or '') for k, v in attributes).get('class', '').split())
        if tag == 'li' and 'company_summary_item' in classes:
            self.tiles.append({'tit': '', 'desc': ''})
        elif self.tiles and 'company_summary_tit' in classes:
            self.field = 'tit'
        elif self.tiles and 'company_summary_desc' in classes:
            self.field = 'desc'
        elif tag in {'dt', 'dd'}:
            self.field = tag
            if tag == 'dt':
                self.dl_key = ''
            else:
                self.rows.append([self.dl_key, ''])

    def handle_data(self, value):
        if self.field in {'tit', 'desc'}:
            self.tiles[-1][self.field] += value
        elif self.field == 'dt':
            self.dl_key += value
        elif self.field == 'dd':
            self.rows[-1][1] += value

    def handle_endtag(self, tag):
        if tag in {'strong', 'p', 'dt', 'dd'}:
            self.field = None


def parse_company(html):
    """Return the company facts Saramin shows, keyed for the dashboard (empty if unreadable)."""
    parser = CompanyParser()
    parser.feed(html)
    clean = lambda v: re.sub(r'\s+', ' ', v).strip()
    profile = {}
    for tile in parser.tiles:
        value, label = clean(tile['tit']), clean(tile['desc'])
        if label.endswith('설립'):
            profile['established'] = label
            profile['company_age'] = value
        elif label in {'기업형태', '사원수', '매출액'} and value and value != '-':
            profile[{'기업형태': 'company_type', '사원수': 'employees', '매출액': 'revenue'}[label]] = value
    for key, value in parser.rows:
        field = {'업종': 'industry', '사업내용': 'business', '홈페이지': 'homepage'}.get(clean(key))
        value = clean(value)
        if field and value and field not in profile:
            profile[field] = short(value, 200)
    if profile.get('homepage') and not re.match(r'https?://', profile['homepage']):
        profile['homepage'] = 'http://' + profile['homepage']
    return profile


def company_key(job):
    try:
        value = urllib.parse.parse_qs(urllib.parse.urlsplit(str(job.get('company_url') or '')).query).get('csn', [''])[0]
    except ValueError:
        return None
    return value if re.fullmatch(r'[A-Za-z0-9+/=_-]{8,120}', value) else None


def plan_companies(jobs, now, settings):
    """Companies whose profile is missing or older than company_recheck_days; open postings first."""
    oldest = (now.date() - dt.timedelta(days=settings['company_recheck_days'])).isoformat()
    due = {}
    for job in jobs:
        key = company_key(job)
        checked = (job.get('company_profile') or {}).get('checked_at', '')
        if key and checked < oldest:
            first = effective_status(job, now.date()) == 'verified_open'
            due[key] = due.get(key, False) or first
    return sorted(due, key=lambda key: not due[key])[:settings['max_company_checks']]


def apply_company(jobs, key, profile, today):
    url = COMPANY_URL.format(key)
    record = dict(profile, source_url=url, checked_at=today)
    for job in jobs:
        if company_key(job) != key:
            continue
        job['company_profile'] = record
        info = dict(job.get('company_info') or {})
        for field, metric in (('employees', 'employees'), ('revenue', 'revenue')):
            if profile.get(field):
                info[metric] = {'value': profile[field], 'as_of': today, 'source_url': url}
        if info:
            job['company_info'] = info
        if profile.get('industry') and placeholder(job.get('company_business')):
            job['company_business'] = profile['industry']


class Fetcher:
    def __init__(self, settings, clock=time.monotonic, sleep=time.sleep):
        self.settings, self.clock, self.sleep = settings, clock, sleep
        self.last = None

    def get(self, url, limit=6 * 1024 * 1024):
        if self.last is not None:
            wait = self.settings['request_delay_seconds'] - (self.clock() - self.last)
            if wait > 0:
                self.sleep(wait)
        try:
            request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
            with urllib.request.urlopen(request, timeout=25) as response:
                return response.geturl(), response.read(limit).decode('utf-8', errors='replace')
        finally:
            self.last = self.clock()


def collect_listings(fetch, settings, log):
    """Return ({id: row}, complete) where complete means every listing page was read."""
    listed, complete = {}, True
    for region in settings['regions']:
        for category in settings['categories']:
            pages = 1
            page = 1
            while page <= min(pages, settings['max_list_pages']):
                query = {'cat_mcls': category['code'], region['param']: region['code'],
                         'page': page, 'page_count': settings['page_size'], 'sort': 'RD'}
                url = LIST_URL + '?' + urllib.parse.urlencode(query)
                try:
                    _, html = fetch(url)
                    total, rows = parse_listing(html)
                except (OSError, http.client.HTTPException, ValueError) as exc:
                    log(f"listing failed: {region['name']} {category['name']} p{page}: {exc}")
                    complete = False
                    break
                if total is None and not rows:
                    log(f"listing unreadable: {region['name']} {category['name']} p{page}")
                    complete = False
                    break
                if total is not None:
                    pages = math.ceil(total / settings['page_size'])
                    if pages > settings['max_list_pages']:
                        complete = False
                for row in rows:
                    if not any(word in row['work_place'] for word in REGION_WORDS):
                        continue
                    row.update(region=region['name'], listing_category=category['name'], source_url=url,
                               category=category_for(row['title'], row['sectors'], category['name']))
                    listed.setdefault(row['id'], row)
                if not rows:
                    break
                page += 1
    return listed, complete


def run(fetch, now, settings, log=print, clock=time.monotonic):
    jobs = json.loads(JOBS.read_text(encoding='utf-8'))
    closed = json.loads(CLOSED.read_text(encoding='utf-8'))
    ledger = json.loads(LEDGER.read_text(encoding='utf-8')) if LEDGER.exists() else {'observations': []}
    started = clock()
    listed, complete = collect_listings(fetch, settings, log)
    closed_ids = {str(row.get('id')) for row in closed['postings'] if isinstance(row, dict)}
    today = now.date().isoformat()
    recategorized = recategorize(jobs, settings)
    focus = set(settings['focus_categories'])
    pruned = prune_unrelated(jobs, focus)
    listing_verified, added = apply_listing(jobs, closed_ids, listed, now, focus)
    queue = plan_checks(jobs, closed_ids, listed, complete, now, settings)
    stats = {'listed': len(listed), 'listings_complete': complete, 'recategorized': recategorized, 'pruned': pruned,
             'listing_verified': listing_verified,
             'added': added, 'planned': len(queue), 'verified': 0, 'closed': 0, 'unknown': 0, 'failed': 0}
    observations, failures, blocked = [], 0, False
    for pid in queue:
        if clock() - started > settings['time_budget_seconds']:
            log('time budget reached; remaining postings wait for the next run')
            break
        url = POSTING_URL.format(pid)
        try:
            final_url, html = fetch(url)
            if not saramin_url(final_url, pid):
                raise ValueError('redirected away from the posting')
            outcome = inspect_html(html, pid)
            failures = 0
        except (OSError, http.client.HTTPException, ValueError) as exc:
            stats['failed'] += 1
            failures += 1
            log(f'posting {pid} not checked: {exc}')
            if failures >= settings['max_consecutive_failures']:
                log('too many consecutive failures; stopping this run without changing statuses')
                blocked = True
                break
            continue
        stats[apply_outcome(jobs, closed, pid, outcome, now, observations)] += 1
    stats['companies'] = 0
    for key in ([] if blocked else plan_companies(jobs, now, settings)):
        if clock() - started > settings['time_budget_seconds']:
            break
        try:
            _, html = fetch(COMPANY_URL.format(key))
            profile = parse_company(html)
        except urllib.error.HTTPError as exc:
            log(f'company {key} not checked: {exc}')
            if exc.code == 404:
                # No public company page; wait company_recheck_days instead of retrying every run.
                apply_company(jobs, key, {'unavailable': True}, today)
            continue
        except (OSError, http.client.HTTPException, ValueError) as exc:
            log(f'company {key} not checked: {exc}')
            continue
        if profile:
            apply_company(jobs, key, profile, today)
            stats['companies'] += 1
    # parse_observations caps one Issue payload at 80 rows; a sync run can record more.
    for start in range(0, len(observations), OBSERVATION_BATCH):
        batch = observations[start:start + OBSERVATION_BATCH]
        merge_observations(ledger, parse_observations({'observations': batch}))
    changed = write_if_changed(JOBS, jobs) | write_if_changed(CLOSED, closed)
    if LEDGER.exists():
        changed |= write_if_changed(LEDGER, ledger)
    stats['changed'] = changed
    return stats


def load_settings():
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    settings = dict(DEFAULTS, **config.get('auto_sync', {}))
    if not settings.get('categories') or not settings.get('regions'):
        raise ValueError('search-config.json auto_sync requires categories and regions')
    # Only Gyul's job groups are kept; the dashboard reads the same list from advisor_profile.
    settings['focus_categories'] = config.get('advisor_profile', {}).get('focus_categories') or []
    if not settings['focus_categories']:
        raise ValueError('search-config.json advisor_profile.focus_categories is required')
    return settings


def main():
    settings = load_settings()
    if not settings.get('enabled', True):
        print('auto_sync disabled in search-config.json')
        return
    fetcher = Fetcher(settings)
    stats = run(fetcher.get, dt.datetime.now(KST), settings, log=lambda m: print(m, file=sys.stderr))
    print('GYUL auto sync: ' + json.dumps(stats, ensure_ascii=False))
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as report:
            report.write('## 사람인 자동 점검\n' + ' · '.join(f'{k} {v}' for k, v in stats.items()) + '\n')


if __name__ == '__main__':
    main()

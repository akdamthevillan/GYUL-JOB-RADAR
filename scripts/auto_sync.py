#!/usr/bin/env python3
"""Scheduled Saramin sync for GYUL JOB RADAR.

Discovery reads public occupation-category listings for the configured regions.
Status reads each individual public posting page and judges its application
control with inspect_html. Low request rate, no login, never clicks or applies.
Network or parsing failures never close or delete a posting; they are retried
on the next run.
"""
import datetime as dt
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
REGION_WORDS = ('부산', '김해', '양산')
PLACEHOLDERS = ('미확인', '미공개', '확인 필요', '원문 확인', '공고 확인')
OBSERVATION_BATCH = 80
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}
DEFAULTS = {'page_size': 100, 'max_list_pages': 40, 'max_detail_checks': 250,
            'request_delay_seconds': 1.0, 'recheck_after_hours': 20,
            'max_consecutive_failures': 8, 'time_budget_seconds': 1500}


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
                        'work_place': '', 'career': '', 'education': '', 'apply': '', 'date': '', 'registered': ''}
            self.depth = len(self.stack)
            return
        if not self.row:
            return
        inside = {c for _, group in self.stack for c in group}
        href = attrs.get('href', '')
        if tag == 'a' and 'company_nm' in inside and href.startswith('/zf_user/company-info/'):
            self.row['company_url'] = 'https://www.saramin.co.kr' + href
            self.field = 'company'
        elif tag == 'a' and 'job_tit' in inside and attrs.get('title'):
            self.row['title'] = attrs['title'].strip()
        elif tag == 'span' and 'job_sector' in inside:
            self.row['sectors'].append('')
            self.field = 'sector'
        elif tag == 'p' and classes & {'work_place', 'career', 'education'}:
            self.field = next(iter(classes & {'work_place', 'career', 'education'}))
        elif tag == 'span' and classes & {'date', 'deadlines'}:
            self.field = 'date' if 'date' in classes else 'registered'
        elif tag == 'button' and 'support_info' in inside:
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
        row = {k: (re.sub(r'\s+', ' ', v).strip() if isinstance(v, str) else v) for k, v in self.row.items()}
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
    ('마케팅·기획', r'마케팅|마케터|마켓팅|홍보|광고|기획'),
)
LISTING_CATEGORIES = {'디자인': '디자인', '마케팅·홍보·조사': '마케팅·기획',
                      '상품기획·MD': '브랜드·상품기획', '기획·전략': '마케팅·기획'}
RELATED_SECTORS = r'디자인|디자이너|그래픽|일러스트|마케팅|홍보|광고|SNS|콘텐츠|컨텐츠|MD|상품기획|브랜드|기획'


def category_for(title, sectors, listing_category):
    """Map a posting onto the dashboard's category names.

    Saramin listings also carry postings that only tag a related keyword, so the
    title decides first and unrelated postings fall into '기타' instead of a
    misleading category.
    """
    for name, pattern in TITLE_CATEGORIES:
        if re.search(pattern, title, re.I):
            return name
    if re.search(RELATED_SECTORS, ' '.join(sectors), re.I):
        return LISTING_CATEGORIES.get(listing_category, '기타')
    return '기타'


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


def plan_checks(jobs, closed_ids, listed, listings_complete, now, settings):
    """Order posting ids to inspect this run.

    1. Jobs once seen in a listing but missing now (probably closed).
    2. Jobs whose current status is not verified open, so unknowns keep being retried.
    3. Newly listed postings, newest first.
    4. Verified jobs due for a recheck before their evidence expires.
    """
    due_before = now - dt.timedelta(hours=settings['recheck_after_hours'])
    never = dt.datetime(2000, 1, 1, tzinfo=KST)
    suspects, unknown, stale = [], [], []
    for job in jobs:
        pid = posting_id(job)
        if not pid or pid in closed_ids:
            continue
        checked = parse_time(job.get('last_checked_at'))
        if listings_complete and job.get('listing_seen_at') and pid not in listed:
            suspects.append((checked or never, pid))
        elif effective_status(job, now.date()) != 'verified_open':
            unknown.append((checked or never, pid))
        elif not checked or checked < due_before:
            stale.append((checked or never, pid))
    known = {posting_id(job) for job in jobs}
    fresh = [pid for pid in listed if pid not in known and pid not in closed_ids]
    order = ([pid for _, pid in sorted(suspects)] + [pid for _, pid in sorted(unknown)]
             + fresh + [pid for _, pid in sorted(stale)])
    return list(dict.fromkeys(order))[:settings['max_detail_checks']]


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
    point = details.get('workplace_coordinates')
    if point and (overwrite or not record.get('workplace_coordinates')):
        record['workplace_coordinates'] = dict(point, source_url=url, checked_at=today)


def apply_outcome(jobs, closed, pid, outcome, row, now, observations):
    """Apply one inspected posting. Returns 'added', 'verified', 'closed' or 'unknown'."""
    today = now.date().isoformat()
    stamp = now.isoformat(timespec='seconds')
    url = POSTING_URL.format(pid)
    index = next((i for i, job in enumerate(jobs) if posting_id(job) == pid), None)
    result = outcome['result']
    if result == 'closed':
        record = {'id': pid, 'closed_confirmed': today,
                  'reason': '접수마감 확인: 자동 점검에서 마감 안내 또는 접수마감 컨트롤 확인',
                  'evidence_url': url, 'application_button_state': 'closed',
                  'application_evidence_kind': 'page_dom', 'application_checked_at': today,
                  'closure_kind': 'closed_by_ui'}
        if index is not None:
            job = jobs.pop(index)
            record['snapshot'] = {k: job.get(k) for k in ('company', 'title', 'location', 'category', 'salary',
                                                          'deadline', 'deadline_text', 'first_seen', 'url')
                                  if job.get(k) is not None}
        elif row:
            record['snapshot'] = {'company': row['company'], 'title': row['title'], 'url': url}
        closed['postings'].append(record)
        observations.append({'id': pid, 'source_url': url, 'observed_at': stamp, 'result': 'closed',
                             'method': 'page_dom', 'evidence': evidence_text(outcome)})
        return 'closed'
    if result != 'apply_enabled':
        if index is not None:
            jobs[index] = dict(jobs[index], last_checked_at=stamp, last_check_result='unknown')
        return 'unknown'
    route = outcome.get('apply_route') or 'saramin'
    verified = {'status': 'verified_open', 'verified_at': today, 'verified_source_url': url,
                'verification_evidence': evidence_text(outcome), 'application_button_state': 'apply_enabled',
                'application_evidence_kind': 'page_dom', 'application_checked_at': today,
                'source_checked_at': today, 'last_checked_at': stamp, 'last_check_result': 'apply_enabled',
                'apply_route': route}
    if index is not None:
        job = dict(jobs[index], **verified)
        fill_details(job, outcome.get('details', {}), url, today, overwrite=False)
        if row:
            job['listing_seen_at'] = today
        jobs[index] = job
        return 'verified'
    if not row:
        return 'unknown'
    job = {'id': pid, 'url': url, 'source': '사람인', 'company': row['company'], 'title': row['title'],
           'category': row.get('category') or '마케팅·기획',
           'location': row['work_place'] or '정확한 근무지 주소 미확인', 'salary': '미공개',
           'benefits': '미공개', 'experience': row['career'] or '원문 확인', 'employment': '원문 확인',
           'first_seen': today, 'discovered_by': 'auto_sync', 'listing_seen_at': today,
           'listing_checked_at': today, 'listing_source_url': row.get('source_url', ''),
           'listing_evidence': f"{row.get('region', '')} {row.get('listing_category', '')} 직종 목록에서 발견".strip(),
           'job_sectors': short(', '.join(row['sectors']), 200)}
    if row.get('company_url'):
        job['company_url'] = row['company_url']
    if row.get('date'):
        job['deadline_text'] = short(row['date'], 60)
    job.update(verified)
    fill_details(job, outcome.get('details', {}), url, today, overwrite=True)
    jobs.append(job)
    observations.append({'id': pid, 'source_url': url, 'observed_at': stamp, 'result': 'apply_enabled',
                         'method': 'page_dom', 'evidence': evidence_text(outcome)})
    return 'added'


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
    for job in jobs:
        if posting_id(job) in listed and job.get('listing_seen_at') != today:
            job['listing_seen_at'] = today
    queue = plan_checks(jobs, closed_ids, listed, complete, now, settings)
    stats = {'listed': len(listed), 'listings_complete': complete, 'planned': len(queue),
             'added': 0, 'verified': 0, 'closed': 0, 'unknown': 0, 'failed': 0}
    observations, failures = [], 0
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
                break
            continue
        stats[apply_outcome(jobs, closed, pid, outcome, listed.get(pid), now, observations)] += 1
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

import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import auto_sync
from auto_sync import (apply_company, apply_outcome, category_for, company_key, parse_company, parse_listing,
                       plan_checks, plan_companies)
from inspect_html import inspect_html
from status_rules import KST

# Observation timestamps must not be in the future, so tests run at the real clock.
NOW = dt.datetime.now(KST).replace(microsecond=0) - dt.timedelta(minutes=1)
SETTINGS = dict(auto_sync.DEFAULTS, regions=[{'name': '부산광역시 전체', 'param': 'loc_mcd', 'code': '106000'}],
                categories=[{'code': '15', 'name': '디자인'}], request_delay_seconds=0)


def listing_row(pid, title, place='부산 사하구', apply='입사지원'):
    # Mirrors the public category listing markup observed on 2026-10-21.
    return f'''<div id="rec-{pid}" class="list_item"><div class="box_item">
    <div class="col company_nm"><a href="/zf_user/company-info/view-inner-recruit?csn=abc" class="str_tit">회사{pid}</a></div>
    <div class="col notification_info"><div class="job_tit"><a class="str_tit" title="{title}" href="/zf_user/jobs/relay/view?rec_idx={pid}"><span>{title}</span></a></div>
    <div class="job_meta"><span class="job_sector"><span>브랜드디자인</span><span>SNS</span> 외</span></div></div>
    <div class="col recruit_info"><ul><li><p class="work_place">{place}</p></li><li><p class="career">경력무관 · 정규직</p></li></ul></div>
    <div class="col support_info"><button class="sri_btn_md" onclick="quickApplyForm('{pid}')"><span class="sri_btn_immediately">{apply}</span></button>
    <p class="support_detail"><span class="date">~11.20(금)</span><span class="deadlines">1시간 전 등록</span></p></div>
    </div></div>'''


def listing_page(*rows, total=None):
    return f'<div style><span class="total_count"><em>{total if total is not None else len(rows)}</em></span>{"".join(rows)}</div>'


def detail(pid, state='open'):
    if state == 'open':
        button = f'<button class="sri_btn_lg for_btn_event" onclick="quickApplyForm(\'{pid}\')"><span class="sri_btn_immediately">입사지원</span></button>'
    elif state == 'homepage':
        button = (f'<button class="sri_btn_lg for_btn_event" title="홈페이지 지원" onclick=\'try{{Saramin.btnJob("homepage", this, "", "");}} catch(e) {{}}\' '
                  f'data-rec_idx="{pid}"><span class="sri_btn_homepage_apply">홈페이지 지원</span></button>')
    else:
        button = f'<button class="sri_btn_expired_apply" onclick="quickApplyForm(\'{pid}\')">접수마감</button>'
    return (f'<div class="jv_location" data-address="(46000) 부산 사하구 낙동대로 1" data-latitude="35.1" data-longitude="129.0"></div>'
            f'<dl><dt>시작일</dt><dd>2026.10.20 08:00</dd><dt>마감일</dt><dd>2026.11.20 23:59</dd><dt>급여</dt><dd>연봉 3,200만원</dd></dl>{button}')


def job(pid, **extra):
    return dict({'id': pid, 'company': '회사', 'title': '디자이너', 'status': '재확인 필요',
                 'url': f'https://www.saramin.co.kr/zf_user/jobs/view?rec_idx={pid}'}, **extra)


class AutoSyncTests(unittest.TestCase):
    def test_listing_rows_parse_with_valueless_attributes(self):
        total, rows = parse_listing(listing_page(listing_row('55300001', '브랜드 디자이너'), total=230))
        self.assertEqual(total, 230)
        self.assertEqual(rows[0]['id'], '55300001')
        self.assertEqual(rows[0]['title'], '브랜드 디자이너')
        self.assertEqual(rows[0]['company'], '회사55300001')
        self.assertEqual(rows[0]['work_place'], '부산 사하구')
        self.assertEqual(rows[0]['sectors'], ['브랜드디자인', 'SNS'])
        self.assertEqual(rows[0]['date'], '~11.20(금)')
        self.assertTrue(rows[0]['company_url'].startswith('https://www.saramin.co.kr/zf_user/company-info/'))

    def test_category_uses_title_before_noisy_sectors(self):
        self.assertEqual(category_for('SNS 콘텐츠 디자이너', [], '마케팅·홍보·조사'), '디자인')
        self.assertEqual(category_for('온라인 MD', [], '디자인'), '브랜드·상품기획')
        self.assertEqual(category_for('AMD 서버 엔지니어', [], '기획·전략'), '기타')
        self.assertEqual(category_for('콜센터 상담원', ['캐셔', '판매직'], '디자인'), '기타')
        self.assertEqual(category_for('신규 직원 채용', ['브랜드디자인'], '디자인'), '디자인')

    def test_homepage_apply_control_counts_as_open(self):
        result = inspect_html(detail('55300002', 'homepage'), '55300002')
        self.assertEqual((result['result'], result['apply_route']), ('apply_enabled', 'homepage'))
        other = inspect_html(detail('55300002', 'homepage'), '55300003')
        self.assertEqual(other['result'], 'unknown')

    def test_plan_prioritizes_missing_then_unknown_then_new_then_due(self):
        fresh = NOW.date().isoformat()
        verified = dict(status='verified_open', verified_at=fresh, application_checked_at=fresh,
                        application_button_state='apply_enabled', application_evidence_kind='page_dom',
                        verification_evidence='x')
        jobs = [job('55300010', **verified, verified_source_url=job('55300010')['url'],
                    last_checked_at=(NOW - dt.timedelta(hours=30)).isoformat()),
                job('55300011'),
                job('55300012', listing_seen_at='2026-10-20'),
                job('55300013', **verified, verified_source_url=job('55300013')['url'],
                    last_checked_at=(NOW - dt.timedelta(hours=1)).isoformat())]
        listed = {'55300010': {}, '55300011': {}, '55300013': {}, '55300020': {}, '55300099': {}}
        order = plan_checks(jobs, {'55300099'}, listed, True, NOW, SETTINGS)
        self.assertEqual(order, ['55300012', '55300011', '55300020', '55300010'])
        # An incomplete listing must not treat absence as a closure hint.
        self.assertEqual(plan_checks(jobs, set(), {}, False, NOW, SETTINGS)[0], '55300011')

    def test_outcomes_add_verify_close_and_keep_unknown(self):
        jobs, closed, notes = [job('55300030', location='부산 사상구 주례로 10')], {'postings': []}, []
        row = parse_listing(listing_page(listing_row('55300031', '편집 디자이너')))[1][0]
        row.update(category='디자인', region='부산광역시 전체', listing_category='디자인')
        self.assertEqual(apply_outcome(jobs, closed, '55300031', inspect_html(detail('55300031'), '55300031'), row, NOW, notes), 'added')
        added = jobs[-1]
        self.assertEqual((added['status'], added['deadline'], added['posted_at'], added['salary']),
                         ('verified_open', '2026-11-20', '2026-10-20', '연봉 3,200만원'))
        self.assertEqual(added['workplace_coordinates']['checked_at'], NOW.date().isoformat())
        unknown = {'result': 'unknown', 'controls': [], 'details': {}}
        self.assertEqual(apply_outcome(jobs, closed, '55300030', unknown, None, NOW, notes), 'unknown')
        self.assertEqual(jobs[0]['status'], '재확인 필요')
        self.assertEqual(apply_outcome(jobs, closed, '55300030', inspect_html(detail('55300030'), '55300030'), None, NOW, notes), 'verified')
        self.assertEqual(jobs[0]['location'], '부산 사상구 주례로 10')
        self.assertEqual(apply_outcome(jobs, closed, '55300030', inspect_html(detail('55300030', 'closed'), '55300030'), None, NOW, notes), 'closed')
        self.assertEqual([j['id'] for j in jobs], ['55300031'])
        self.assertEqual(closed['postings'][0]['snapshot']['location'], '부산 사상구 주례로 10')
        self.assertEqual(len(notes), 2)

    def test_run_end_to_end_and_failures_never_close(self):
        pages = {'list': listing_page(listing_row('55300040', '브랜드 디자이너'), listing_row('55300041', 'SNS 마케터'),
                                      listing_row('55300042', '외부 공고', place='서울 강남구')),
                 '55300040': detail('55300040'), '55300041': None, '55300050': detail('55300050', 'closed')}

        def fetch(url):
            if 'job-category' in url:
                return url, pages['list']
            pid = url.rsplit('=', 1)[1]
            if pages.get(pid) is None:
                raise OSError('HTTP 503')
            return url, pages[pid]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'jobs.json').write_text(json.dumps([job('55300050', listing_seen_at='2026-10-20'), job('55300051')]))
            (root / 'closed-postings.json').write_text('{"postings": []}')
            (root / 'observations.json').write_text('{"observations": []}')
            with patch.object(auto_sync, 'JOBS', root / 'jobs.json'), patch.object(auto_sync, 'CLOSED', root / 'closed-postings.json'), \
                    patch.object(auto_sync, 'LEDGER', root / 'observations.json'):
                stats = auto_sync.run(fetch, NOW, SETTINGS, log=lambda _: None)
            jobs = {j['id']: j for j in json.loads((root / 'jobs.json').read_text())}
            closed = json.loads((root / 'closed-postings.json').read_text())['postings']
        self.assertEqual(stats['listed'], 2)
        self.assertEqual((stats['added'], stats['closed'], stats['failed']), (1, 1, 2))
        self.assertEqual(set(jobs), {'55300040', '55300051'})
        self.assertEqual(jobs['55300051']['status'], '재확인 필요')
        self.assertEqual([row['id'] for row in closed], ['55300050'])

    def test_run_records_more_than_one_issue_batch_of_observations(self):
        ids = [str(55301000 + i) for i in range(85)]

        def fetch(url):
            if 'job-category' in url:
                return url, listing_page(*(listing_row(pid, '브랜드 디자이너') for pid in ids))
            pid = url.rsplit('=', 1)[1]
            return url, detail(pid)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'jobs.json').write_text('[]')
            (root / 'closed-postings.json').write_text('{"postings": []}')
            (root / 'observations.json').write_text('{"observations": []}')
            with patch.object(auto_sync, 'JOBS', root / 'jobs.json'), patch.object(auto_sync, 'CLOSED', root / 'closed-postings.json'), \
                    patch.object(auto_sync, 'LEDGER', root / 'observations.json'):
                stats = auto_sync.run(fetch, NOW, SETTINGS, log=lambda _: None)
            self.assertEqual(stats['added'], 85)
            self.assertEqual(len(json.loads((root / 'observations.json').read_text())['observations']), 85)

    def test_company_page_profile_feeds_size_metrics(self):
        # Mirrors the public company-info page markup observed on 2026-10-21.
        html = ('<ul><li class="company_summary_item"><strong class="company_summary_tit">업력 7년차 </strong>'
                '<p class="company_summary_desc">2020년 7월 24일 설립</p></li>'
                '<li class="company_summary_item"><button><strong class="company_summary_tit">중소기업</strong></button>'
                '<p class="company_summary_desc">기업형태</p></li>'
                '<li class="company_summary_item"><strong class="company_summary_tit">34 명</strong><p class="company_summary_desc">사원수</p></li>'
                '<li class="company_summary_item"><strong class="company_summary_tit">-</strong><p class="company_summary_desc">매출액</p></li></ul>'
                '<dl><dt>업종</dt><dd>디자인 서비스업</dd><dt>대표자명</dt><dd>홍길동</dd><dt>홈페이지</dt><dd>example.com</dd></dl>')
        profile = parse_company(html)
        self.assertEqual(profile, {'established': '2020년 7월 24일 설립', 'company_age': '업력 7년차', 'company_type': '중소기업',
                                   'employees': '34 명', 'industry': '디자인 서비스업', 'homepage': 'http://example.com'})
        jobs = [job('55300060', company_url='https://www.saramin.co.kr/zf_user/company-info/view-inner-recruit?csn=QWJjZDEyMzQ='),
                job('55300061', company_url='https://www.saramin.co.kr/zf_user/company-info/view?csn=QWJjZDEyMzQ=',
                    company_profile={'checked_at': NOW.date().isoformat()}),
                job('55300062')]
        self.assertEqual(company_key(jobs[0]), 'QWJjZDEyMzQ=')
        self.assertEqual(plan_companies(jobs, NOW, SETTINGS), ['QWJjZDEyMzQ='])
        apply_company(jobs, 'QWJjZDEyMzQ=', profile, NOW.date().isoformat())
        self.assertEqual(jobs[0]['company_info']['employees']['value'], '34 명')
        self.assertNotIn('revenue', jobs[0]['company_info'])
        self.assertEqual(jobs[1]['company_profile']['company_type'], '중소기업')
        self.assertEqual(plan_companies(jobs, NOW, SETTINGS), [])
        self.assertNotIn('company_profile', jobs[2])

    def test_consecutive_failures_stop_run(self):
        calls = []

        def fetch(url):
            calls.append(url)
            if 'job-category' in url:
                return url, listing_page(*(listing_row(str(55300100 + i), '디자이너') for i in range(20)))
            raise OSError('blocked')

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'jobs.json').write_text('[]')
            (root / 'closed-postings.json').write_text('{"postings": []}')
            with patch.object(auto_sync, 'JOBS', root / 'jobs.json'), patch.object(auto_sync, 'CLOSED', root / 'closed-postings.json'), \
                    patch.object(auto_sync, 'LEDGER', root / 'missing.json'):
                stats = auto_sync.run(fetch, NOW, dict(SETTINGS, max_consecutive_failures=3), log=lambda _: None)
        self.assertEqual(stats['failed'], 3)
        self.assertEqual(len(calls), 4)


if __name__ == '__main__':
    unittest.main()

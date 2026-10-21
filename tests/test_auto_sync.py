import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import auto_sync
from auto_sync import (apply_company, apply_listing, apply_outcome, category_for, company_key, listing_deadline,
                       listing_posted, parse_company, parse_listing, plan_checks, plan_companies, prune_unrelated,
                       recategorize)
from status_rules import effective_status
from inspect_html import inspect_html
from status_rules import KST

# Observation timestamps must not be in the future, so tests run at the real clock.
NOW = dt.datetime.now(KST).replace(microsecond=0) - dt.timedelta(minutes=1)
SETTINGS = dict(auto_sync.DEFAULTS, regions=[{'name': '부산광역시 전체', 'param': 'loc_mcd', 'code': '106000'}],
                categories=[{'code': '15', 'name': '디자인'}], request_delay_seconds=0,
                focus_categories=['디자인', '콘텐츠·SNS', '브랜드·상품기획', '온라인·디지털 운영', '마케팅·기획'])


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
        # 'MD' inside 'AMD' is not a merchandiser posting.
        self.assertEqual(category_for('AMD 서버 엔지니어', [], '기획·전략'), 'IT·개발')
        self.assertEqual(category_for('신규 직원 채용', ['브랜드디자인'], '디자인'), '디자인')
        self.assertEqual(category_for('콜센터 상담원', ['캐셔', '판매직'], '디자인'), '영업·고객상담')
        self.assertEqual(category_for('백화점 판매사원', [], '마케팅·홍보·조사'), '판매·매장')
        self.assertEqual(category_for('웹툰 펜터치 작가', [], '디자인'), '창작·영상')
        self.assertEqual(category_for('SNS 마케터 (사진·영상편집)', [], '디자인'), '콘텐츠·SNS')
        self.assertEqual(category_for('신규 채용', ['경리', '총무'], '기획·전략'), '사무·경영지원')
        self.assertEqual(category_for('병원 마케팅 TM 마케터 정규직 모집', [], '마케팅·홍보·조사'), '영업·고객상담')
        self.assertEqual(category_for('온라인 쇼핑몰 채팅상담/오픈마켓/CS관리 정규직', [], '디자인'), '영업·고객상담')
        self.assertEqual(category_for('웹디자이너, 고객상담(CS) 채용', [], '디자인'), '디자인')
        self.assertEqual(category_for('실내인테리어 설계 디자이너 경력직 채용', [], '디자인'), '인테리어·건축·시공')
        self.assertEqual(category_for('사업기획팀 신입/경력사원 모집', [], '기획·전략'), '사무·경영지원')
        self.assertEqual(category_for('영업마케팅AE 직원 채용', [], '마케팅·홍보·조사'), '영업·고객상담')
        self.assertNotIn(category_for('의류 쇼핑몰 단순 포장 알바생 모집', [], '상품기획·MD'), SETTINGS['focus_categories'])
        self.assertEqual(category_for('웹퍼블리셔 모집 (디자인 가능 우대)', [], '디자인'), '디자인')
        for title in ('김해 의류 쇼핑몰 파트타임 알바생을 모집합니다', '현대백화점 화장품 브랜드 판매업무',
                      '이치방쿠지 부산 지역 매니저 채용', '체험홍보관 부산점 메이크업 아티스트',
                      '골프매장 판매 및 제품 블로그 홍보·마케팅 채용', 'AI 무인매장 내 브랜드 파트너십 매니저 채용',
                      '브랜드 불고기공방 R&D / SV 모집', '삼진어묵 매장기획팀 팀장'):
            self.assertNotIn(category_for(title, [], '디자인'), SETTINGS['focus_categories'], title)
        self.assertEqual(category_for('스마트스토어 상세페이지 운영 담당', [], '디자인'), '온라인·디지털 운영')
        for title in ('유튜브 영상편집자 모집', '2D 애니메이터 채용', '애니메이션 3D 배경 모델러', '영상 제작 PD 채용', '동영상 편집 직원'):
            self.assertNotIn(category_for(title, [], '디자인'), SETTINGS['focus_categories'], title)
        for title in ('[부산] 영상 디자이너 채용', '모션그래픽, 영상 편집팀 채용', '3D 모델링·렌더링 디자이너 모집', '[법무법인] 영상마케터 직원 채용', '비버웍스디자인에서 3D 및 캐드설계직원 모집'):
            self.assertNotIn(category_for(title, [], '디자인'), SETTINGS['focus_categories'], title)
        for title in ('26하반기 온라인마케터, 시각 영상 디자이너 채용', '책디자이너&영상편집자를 모집해요'):
            self.assertIn(category_for(title, [], '디자인'), SETTINGS['focus_categories'], title)
        self.assertEqual(category_for('매장 POP·SNS 디자이너', [], '디자인'), '디자인')
        self.assertEqual(category_for('행사·전시 기획자 모집', [], '기획·전략'), '마케팅·기획')
        self.assertEqual(category_for('경력직 수시채용', ['마케팅기획', '사업기획'], '기획·전략'), '기타')
        self.assertEqual(category_for('인테리어 목수 및 설치기사 모집', [], '디자인'), '인테리어·건축·시공')
        # Marketing work at an interior company stays in Gyul's field.
        self.assertEqual(category_for('인테리어 컨텐츠 마케팅 담당자를 찾습니다', [], '디자인'), '콘텐츠·SNS')

    def test_recategorize_updates_auto_records_only(self):
        settings = dict(SETTINGS, categories=[{'code': '15', 'name': '디자인'}])
        jobs = [job('55300080', title='백화점 판매사원', category='디자인', discovered_by='auto_sync',
                    listing_source_url='https://www.saramin.co.kr/zf_user/jobs/list/job-category?cat_mcls=15'),
                job('55300081', title='신규 채용', category='기타', discovered_by='auto_sync', job_sectors='브랜드디자인, SNS',
                    listing_source_url='https://www.saramin.co.kr/zf_user/jobs/list/job-category?cat_mcls=15'),
                job('55300082', title='백화점 판매사원', category='디자인')]
        self.assertEqual(recategorize(jobs, settings), 2)
        self.assertEqual([j['category'] for j in jobs], ['판매·매장', '디자인', '디자인'])

    def test_homepage_apply_control_counts_as_open(self):
        result = inspect_html(detail('55300002', 'homepage'), '55300002')
        self.assertEqual((result['result'], result['apply_route']), ('apply_enabled', 'homepage'))
        other = inspect_html(detail('55300002', 'homepage'), '55300003')
        self.assertEqual(other['result'], 'unknown')

    def test_listing_dates(self):
        today = dt.date(2026, 10, 21)
        self.assertEqual(listing_deadline('~11.20(금)', today), '2026-11-20')
        self.assertEqual(listing_deadline('~01.05(월)', today), '2027-01-05')
        self.assertEqual(listing_deadline('D-5', today), '2026-10-26')
        self.assertIsNone(listing_deadline('상시채용', today))
        self.assertEqual(listing_posted('3일 전 등록', today), '2026-10-18')
        self.assertEqual(listing_posted('4시간 전 등록', today), '2026-10-21')
        self.assertIsNone(listing_posted('3시간 전 수정', today))

    def test_listing_button_verifies_existing_and_adds_new(self):
        rows = parse_listing(listing_page(listing_row('55300070', '브랜드 디자이너'), listing_row('55300071', 'SNS 마케터'),
                                          listing_row('55300072', '편집 디자이너', apply='접수예정'),
                                          listing_row('55300073', '디자이너'), listing_row('55300074', '디자이너')))[1]
        rows[4]['apply_id'] = '55300099'
        listed = {row['id']: dict(row, category='디자인', source_url='https://www.saramin.co.kr/list') for row in rows}
        jobs = [job('55300070', location='부산 사상구 주례로 10')]
        verified, added = apply_listing(jobs, {'55300073'}, listed, NOW)
        self.assertEqual((verified, added), (1, 1))
        self.assertEqual(jobs[0]['location'], '부산 사상구 주례로 10')
        self.assertEqual(jobs[0]['application_evidence_page'], 'https://www.saramin.co.kr/list')
        new = jobs[1]
        self.assertEqual((new['id'], new['deadline_text'], new['location'], new['discovered_by']),
                         ('55300071', '~11.20(금)', '부산 사하구', 'auto_sync'))
        self.assertNotIn('salary', new)
        self.assertNotIn('details_checked_at', new)
        self.assertEqual(effective_status(new, NOW.date()), 'verified_open')

    def test_unrelated_postings_are_not_added_and_auto_records_are_pruned(self):
        rows = parse_listing(listing_page(listing_row('55300090', '브랜드 디자이너'), listing_row('55300091', '콜센터 상담원')))[1]
        listed = {row['id']: dict(row, category=category_for(row['title'], [], '디자인')) for row in rows}
        jobs = [job('55300092', category='판매·매장', discovered_by='auto_sync'),
                job('55300093', category='판매·매장'), job('55300094', category='디자인', discovered_by='auto_sync')]
        self.assertEqual(prune_unrelated(jobs, set(SETTINGS['focus_categories'])), 1)
        self.assertEqual([j['id'] for j in jobs], ['55300093', '55300094'])
        self.assertEqual(apply_listing(jobs, set(), listed, NOW, set(SETTINGS['focus_categories'])), (0, 1))
        self.assertEqual([j['id'] for j in jobs], ['55300093', '55300094', '55300090'])

    def test_plan_prioritizes_missing_new_unlisted_then_stale(self):
        fresh_day = NOW.date().isoformat()
        old_day = (NOW.date() - dt.timedelta(days=10)).isoformat()
        jobs = [job('55300010', details_checked_at=old_day),
                job('55300011'),
                job('55300012', listing_seen_at='2026-10-20', details_checked_at=fresh_day),
                job('55300013', details_checked_at=fresh_day),
                job('55300014')]
        listed = {'55300014': {}, '55300011': {}, '55300010': {}, '55300013': {}}
        self.assertEqual(plan_checks(jobs, set(), listed, True, NOW, SETTINGS),
                         ['55300012', '55300014', '55300011', '55300010'])
        # An incomplete listing must not treat absence as a closure hint.
        self.assertEqual(plan_checks(jobs, set(), {}, False, NOW, SETTINGS), ['55300010', '55300011', '55300012', '55300013', '55300014'])

    def test_posting_page_fills_details_closes_or_keeps_unknown(self):
        jobs, closed, notes = [job('55300030', location='부산 사상구 주례로 10'),
                               job('55300031', discovered_by='auto_sync', location='부산 사하구')], {'postings': []}, []
        self.assertEqual(apply_outcome(jobs, closed, '55300031', inspect_html(detail('55300031'), '55300031'), NOW, notes), 'verified')
        added = jobs[1]
        self.assertEqual((added['location'], added['deadline'], added['posted_at'], added['salary']),
                         ('부산 사하구 낙동대로 1', '2026-11-20', '2026-10-20', '연봉 3,200만원'))
        self.assertEqual(added['details_checked_at'], NOW.date().isoformat())
        self.assertEqual(added['workplace_coordinates']['checked_at'], NOW.date().isoformat())
        unknown = {'result': 'unknown', 'controls': [], 'details': {}}
        self.assertEqual(apply_outcome(jobs, closed, '55300030', unknown, NOW, notes), 'unknown')
        self.assertEqual(jobs[0]['status'], '재확인 필요')
        self.assertEqual(apply_outcome(jobs, closed, '55300030', inspect_html(detail('55300030'), '55300030'), NOW, notes), 'verified')
        self.assertEqual(jobs[0]['location'], '부산 사상구 주례로 10')
        self.assertEqual(apply_outcome(jobs, closed, '55300030', inspect_html(detail('55300030', 'closed'), '55300030'), NOW, notes), 'closed')
        self.assertEqual([j['id'] for j in jobs], ['55300031'])
        self.assertEqual(closed['postings'][0]['snapshot']['location'], '부산 사상구 주례로 10')
        self.assertEqual(apply_outcome(jobs, closed, '55300099', unknown, NOW, notes), 'unknown')
        self.assertEqual(len(notes), 1)

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
        self.assertEqual((stats['listed'], stats['added'], stats['closed'], stats['failed']), (2, 2, 1, 2))
        self.assertEqual(set(jobs), {'55300040', '55300041', '55300051'})
        self.assertEqual(jobs['55300040']['details_checked_at'], NOW.date().isoformat())
        # The page failed, but the listing button still confirms the posting; details stay pending.
        self.assertEqual(effective_status(jobs['55300041'], NOW.date()), 'verified_open')
        self.assertNotIn('details_checked_at', jobs['55300041'])
        self.assertEqual(jobs['55300051']['status'], '재확인 필요')
        self.assertEqual([row['id'] for row in closed], ['55300050'])

    def test_run_records_more_than_one_issue_batch_of_observations(self):
        ids = [str(55301000 + i) for i in range(85)]

        def fetch(url):
            if 'job-category' in url:
                return url, listing_page()
            return url, detail(url.rsplit('=', 1)[1], 'closed')

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'jobs.json').write_text(json.dumps([job(pid, listing_seen_at='2026-10-20') for pid in ids]))
            (root / 'closed-postings.json').write_text('{"postings": []}')
            (root / 'observations.json').write_text('{"observations": []}')
            with patch.object(auto_sync, 'JOBS', root / 'jobs.json'), patch.object(auto_sync, 'CLOSED', root / 'closed-postings.json'), \
                    patch.object(auto_sync, 'LEDGER', root / 'observations.json'):
                stats = auto_sync.run(fetch, NOW, dict(SETTINGS, max_detail_checks=100), log=lambda _: None)
            self.assertEqual(stats['closed'], 85)
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
        apply_company(jobs, 'QWJjZDEyMzQ=', {'unavailable': True}, NOW.date().isoformat())
        self.assertTrue(jobs[0]['company_profile']['unavailable'])
        self.assertEqual(plan_companies(jobs, NOW, SETTINGS), [])

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

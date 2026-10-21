import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from status_rules import effective_status
from observations import parse_observations, merge_observations, validate_details
from import_issues import apply_imports, parse_issue, prepare
from cleanup import maintain


class AdvisorTests(unittest.TestCase):
    def test_shared_browser_python_status_contract(self):
        path = Path(__file__).parent / 'fixtures/status-cases.json'
        for case in json.loads(path.read_text()):
            with self.subTest(case['name']):
                self.assertEqual(effective_status(case['job'], dt.date.fromisoformat(case['today'])), case['expected'])

    def test_observation_ledger_idempotent_and_timezone_required(self):
        row = {'id': '55251835', 'source_url': 'https://m.saramin.co.kr/job-search/view?rec_idx=55251835',
               'observed_at': '2026-10-21T11:17:00+09:00', 'result': 'apply_enabled',
               'method': 'user_screenshot', 'evidence': '사용자 화면 하단 입사지원'}
        rows = parse_observations({'observations': [row]})
        ledger = {'observations': []}
        merge_observations(ledger, rows)
        merge_observations(ledger, rows)
        self.assertEqual(len(ledger['observations']), 1)
        with self.assertRaises(ValueError):
            parse_observations({'observations': [dict(row, observed_at='2026-10-21T11:17:00')]})
        with self.assertRaises(ValueError):
            parse_observations({'observations': [dict(row, id='12345678')]})

    def test_new_unknown_observation_can_downgrade_without_erasing_address(self):
        jobs = [{'id': '55251835', 'url': 'https://m.saramin.co.kr/job-search/view?rec_idx=55251835',
                 'status': 'verified_open', 'location': '부산 사상구 주례로 10', 'verification_evidence': '과거 관찰'}]
        apply_imports(jobs, {'postings': []}, [{'id': '55251835', 'status': '재확인 필요', 'location': '정확한 근무지 주소 미확인'}], [])
        self.assertEqual(jobs[0]['status'], '재확인 필요')
        self.assertEqual(jobs[0]['location'], '부산 사상구 주례로 10')
        self.assertEqual(jobs[0]['verification_evidence'], '과거 관찰')

    def test_expiry_keeps_snapshot_and_distinct_reason(self):
        job = {'id': '55251835', 'url': 'https://m.saramin.co.kr/job-search/view?rec_idx=55251835', 'deadline': '2026-10-20'}
        jobs, ledger, stats = maintain([job], {'postings': []}, dt.date(2026, 10, 21))
        self.assertEqual(jobs, [])
        self.assertEqual(ledger['postings'][0]['closure_kind'], 'expired_by_date')
        self.assertEqual(ledger['postings'][0]['snapshot'], job)

    def test_company_and_commute_require_sources(self):
        with self.assertRaises(ValueError):
            validate_details({'company_info': {'employees': {'value': '100명'}}})
        with self.assertRaises(ValueError):
            validate_details({'commute': {'origin': '냉정역', 'minutes': 15}})

    def test_ui_payload_accepted_and_observation_only_saved(self):
        row = {'id': '55251835', 'source_url': 'https://m.saramin.co.kr/job-search/view?rec_idx=55251835',
               'observed_at': '2026-10-21T11:17:00+09:00', 'result': 'unknown',
               'method': 'browser_visual', 'evidence': '페이지 로딩 실패'}
        payload = {'jobs': [], 'closed_postings': [], 'observations': [row]}
        self.assertEqual(parse_issue({'body': json.dumps(payload)}), ([], []))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'jobs.json').write_text('[]')
            (root/'closed-postings.json').write_text('{"postings": []}')
            issue = {'body': json.dumps(payload), 'number': 1, 'updated_at': '2026-10-21T02:17:00Z'}
            with patch('import_issues.JOBS', root/'jobs.json'), patch('import_issues.CLOSED', root/'closed-postings.json'), patch('import_issues.pending_issues', return_value=[issue]):
                prepare('owner/repo', 'owner', str(root/'manifest.json'))
            self.assertEqual(len(json.loads((root/'observations.json').read_text())['observations']), 1)

    def test_agent_issue_with_summary_text_uses_fenced_json(self):
        payload = {'jobs': [], 'closed_postings': [], 'observations': []}
        body = '귤레이더 점검 결과입니다.\n\n```json\n' + json.dumps(payload) + '\n```\n\n- 신규 0건'
        self.assertEqual(parse_issue({'body': body}), ([], []))
        with self.assertRaises(ValueError):
            parse_issue({'body': '설명만 있고 JSON 없음'})

    @staticmethod
    def research_report(**overrides):
        report = {'last_run_at': '2026-10-21T09:00:00+09:00', 'state': 'partial',
                  'existing_postings_checked': 2, 'new_candidates_checked': 1,
                  'observations': {'apply_enabled': 1, 'closed': 1, 'unknown': 1},
                  'searches': [{'region': '부산광역시 전체', 'keyword': '디자인', 'page': 1, 'state': 'partial',
                                'source_url': 'https://www.saramin.co.kr/zf_user/search?searchword=x'}],
                  'note': '디자인 첫 페이지만 조사'}
        report.update(overrides)
        return report

    def test_research_report_validation(self):
        from import_issues import parse_research_report
        self.assertEqual(parse_research_report({'research_report': self.research_report()})['state'], 'partial')
        for bad in ({'last_run_at': '2999-01-01T00:00:00+09:00'}, {'last_run_at': '2026-10-21T09:00:00'},
                    {'state': 'done'}, {'observations': {'apply_enabled': 1}}, {'note': ''},
                    {'searches': [{'region': '부산', 'keyword': '디자인', 'state': 'partial', 'html': 'x'}]}):
            with self.subTest(bad), self.assertRaises(ValueError):
                parse_research_report({'research_report': self.research_report(**bad)})

    def test_prepare_writes_research_report_with_applied_counts(self):
        payload = {'jobs': [], 'closed_postings': [], 'research_report': self.research_report(new_jobs_added=99)}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'jobs.json').write_text('[]')
            (root/'closed-postings.json').write_text('{"postings": []}')
            (root/'research-report.json').write_text(json.dumps({'last_run_at': '2026-10-20T10:00:00+09:00'}))
            issue = {'body': json.dumps(payload), 'number': 7, 'updated_at': '2026-10-21T06:00:00Z'}
            with patch('import_issues.JOBS', root/'jobs.json'), patch('import_issues.CLOSED', root/'closed-postings.json'), patch('import_issues.pending_issues', return_value=[issue]):
                prepare('owner/repo', 'owner', str(root/'manifest.json'))
            report = json.loads((root/'research-report.json').read_text())
            self.assertEqual(report['note'], '디자인 첫 페이지만 조사')
            self.assertEqual(report['new_jobs_added'], 0)
            self.assertEqual(report['source_issue'], 7)
            self.assertEqual(len(json.loads((root/'manifest.json').read_text())), 1)

    def test_rejected_issue_gets_one_feedback_comment(self):
        from import_issues import report_rejection
        calls = []
        def fake_api(method, path, payload=None):
            calls.append((method, path, payload))
            return [{'body': c[2]['body']} for c in calls if c[0] == 'POST']
        issue = {'number': 3, 'body': '{"jobs": "bad"}'}
        with patch('import_issues.github_api', side_effect=fake_api):
            report_rejection('owner/repo', issue, 'expected arrays')
            report_rejection('owner/repo', issue, 'expected arrays')
        posts = [c for c in calls if c[0] == 'POST']
        self.assertEqual(len(posts), 1)
        self.assertIn('expected arrays', posts[0][2]['body'])

    def test_live_dom_overrides_past_recorded_deadline_in_import_and_cleanup(self):
        from import_issues import validated_job
        day = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
        job = {'id': '55251835', 'url': 'https://m.saramin.co.kr/job-search/view?rec_idx=55251835',
               'company': '회사', 'title': '디자이너', 'deadline': (day-dt.timedelta(days=1)).isoformat(),
               'status': 'verified_open', 'verified_at': day.isoformat(),
               'verified_source_url': 'https://m.saramin.co.kr/job-search/view?rec_idx=55251835',
               'verification_evidence': '현재 실제 DOM의 활성 입사지원 버튼',
               'application_button_state': 'apply_enabled', 'application_evidence_kind': 'page_dom',
               'application_checked_at': day.isoformat()}
        self.assertEqual(validated_job(job)['status'], 'verified_open')
        result, ledger, _ = maintain([job], {'postings': []}, day)
        self.assertEqual(len(result), 1)
        self.assertEqual(ledger['postings'], [])

    def test_search_session_never_counts_pending_or_blocked_as_completed(self):
        from research_session import create_session, summarize
        session = create_session({'search_strategy': {'regions': ['부산', '김해'], 'primary_keywords': ['디자인'], 'additional_keywords': ['디자인', 'SNS']}})
        self.assertEqual(summarize(session)['total_searches'], 4)
        session['tasks'][0]['state'] = 'blocked'
        self.assertEqual(summarize(session)['completion_percent'], 0)
        session['tasks'][1]['state'] = 'completed'
        self.assertEqual(summarize(session)['completion_percent'], 25)

    def test_exact_user_html_controls_without_images(self):
        from inspect_html import inspect_html
        root = Path(__file__).parent/'fixtures'
        self.assertEqual(inspect_html((root/'apply-enabled.html').read_text(), '55251835')['result'], 'apply_enabled')
        self.assertEqual(inspect_html((root/'apply-closed.html').read_text(), '55166027')['result'], 'closed')
        enabled = (root/'apply-enabled.html').read_text()
        self.assertEqual(inspect_html(enabled, '99999999')['result'], 'unknown')
        self.assertEqual(inspect_html(enabled.replace('<button ', '<button disabled '), '55251835')['result'], 'unknown')
        self.assertEqual(inspect_html('<div hidden>'+enabled+'</div>', '55251835')['result'], 'unknown')

    def test_search_result_candidates_and_confirmed_sort(self):
        from discover_candidates import CandidateParser, parse_candidates
        html = '<li class="selected"><button target="sort" value="reg_dt" position="recruit">등록일순</button></li><div class="item_recruit" value="55287035"><div class="area_job"><h2 class="job_tit"><a title="시각디자이너">시각디자이너</a></h2><div class="job_condition"><span>부산 사상구</span><span>경력무관</span></div><div class="job_date">~ 11/10 입사지원</div></div><strong class="corp_name"><a href="/zf_user/company-info/view?csn=example">예시회사</a></strong></div>'
        rows = parse_candidates(html+html)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['company'], '예시회사')
        self.assertEqual(rows[0]['deadline_text'], '~ 11/10')
        self.assertIn('부산 사상구', rows[0]['conditions'])
        parser = CandidateParser()
        parser.feed(html)
        self.assertEqual(parser.selected_sort, 'reg_dt')

    def test_source_workplace_coordinates_and_job_conditions(self):
        from inspect_html import inspect_html
        html = '<dl><dt>급여</dt><dd>연봉 3,000만원</dd><dt>근무일시</dt><dd>주 5일</dd></dl><div class="jv_location" data-address="(46981) 부산 사상구 대동로 303" data-latitude="35.15" data-longitude="128.98" data-hide_fl="n"></div>'
        fields = inspect_html(html, '55251835')['details']
        self.assertEqual(fields['salary'], '연봉 3,000만원')
        self.assertEqual(fields['work_schedule'], '주 5일')
        self.assertEqual(fields['location'], '부산 사상구 대동로 303')
        self.assertEqual(fields['workplace_coordinates']['lng'], 128.98)

    def test_closure_stats_count_one_posting_once_and_preserve_snapshot(self):
        jobs = [{'id':'55251835','url':'https://www.saramin.co.kr/zf_user/jobs/view?rec_idx=55251835','title':'디자이너'}]
        closed = {'postings': []}
        stats = apply_imports(jobs, closed, [], [{'id':'55251835','reason':'접수마감 확인','closure_kind':'closed_by_ui'}])
        self.assertEqual(stats['closed'], 1)
        self.assertEqual(jobs, [])
        self.assertEqual(closed['postings'][0]['snapshot']['title'], '디자이너')

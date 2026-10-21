import datetime as dt
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cleanup import maintain, posting_id
from import_issues import apply_imports, parse_issue, validated_job


class GyulTests(unittest.TestCase):
    TODAY = dt.date(2026, 10, 16)

    @staticmethod
    def job(pid, title, deadline=None, status='재확인 필요'):
        return {'id': pid, 'company': '동일기업', 'title': title,
                'location': '부산 사상구', 'url':
                f'https://www.saramin.co.kr/zf_user/jobs/view?rec_idx={pid}',
                'deadline': deadline, 'status': status}

    def test_same_company_distinct_ids_both_remain(self):
        jobs = [self.job('55260001', '디자인'), self.job('55260002', '디자인')]
        result, closed, stats = maintain(jobs, {'postings': []}, self.TODAY)
        self.assertEqual(len(result), 2)
        self.assertEqual(stats['duplicates'], 0)
        self.assertEqual(closed['postings'], [])

    def test_expired_only_and_closure_ledger(self):
        jobs = [self.job('55260001', '만료', '2026-10-15'),
                self.job('55260002', '당일', '2026-10-16'),
                self.job('55260003', '미확인', None)]
        result, closed, stats = maintain(jobs, {'postings': []}, self.TODAY)
        self.assertEqual(len(result), 2)
        self.assertEqual(stats['removed'], 1)
        self.assertEqual(closed['postings'][0]['id'], '55260001')

    def test_unknown_identifier_not_erased(self):
        unknown = {'id': 'company-abc', 'company': '회사', 'title': '디자인',
                   'url': 'https://www.saramin.co.kr/zf_user/company-info/view-inner-recruit/abc',
                   'status': '마감', 'deadline': '2026-10-01'}
        result, closed, _ = maintain([unknown], {'postings': []}, self.TODAY)
        self.assertEqual(result, [unknown])
        self.assertEqual(closed['postings'], [])

    def test_existing_closure_prevents_resurrection(self):
        existing = {'postings': [{'id': '55260001', 'reason': '접수마감 확인'}]}
        result, closed, _ = maintain([self.job('55260001', '마감')], existing, self.TODAY)
        self.assertEqual(result, [])
        self.assertEqual(len(closed['postings']), 1)

    def test_import_new_and_idempotent(self):
        entry = validated_job(self.job('55260002', 'MD', (dt.date.today() + dt.timedelta(days=365)).isoformat()))
        jobs, closed = [], {'postings': []}
        first = apply_imports(jobs, closed, [entry], [])
        second = apply_imports(jobs, closed, [entry], [])
        self.assertEqual(first['added'], 1)
        self.assertEqual(second['added'], 0)
        self.assertEqual(second['updated'], 0)
        self.assertEqual(len(jobs), 1)

    def test_verified_requires_explicit_evidence(self):
        entry = self.job('55260001', '디자인', (dt.date.today() + dt.timedelta(days=365)).isoformat(), 'verified_open')
        self.assertEqual(validated_job(entry)['status'], '재확인 필요')

    def test_reject_mismatched_posting_url(self):
        entry = self.job('55260001', '디자인')
        entry['url'] = 'https://www.saramin.co.kr/zf_user/jobs/view?rec_idx=55260009'
        with self.assertRaises(ValueError):
            validated_job(entry)

    def test_issue_body_parse(self):
        body = json.dumps({'jobs': [self.job('55260001', '디자인')], 'closed_postings': []})
        jobs, closed = parse_issue({'body': body})
        self.assertEqual(jobs[0]['id'], '55260001')
        self.assertEqual(closed, [])

    def test_evidence_required_for_manual_closure(self):
        body = json.dumps({'closed_postings': [{'id': '55260001', 'reason': '접수마감 확인'}]})
        with self.assertRaises(ValueError):
            parse_issue({'body': body})

    def test_partial_issue_update_keeps_verified_workplace(self):
        original = self.job('55260004', '웹디자이너')
        original['location'] = '부산 사상구 사상로 25'
        patch = dict(original)
        patch.pop('location')
        partial = validated_job(patch)
        self.assertNotIn('location', partial)
        jobs = [original]
        apply_imports(jobs, {'postings': []}, [partial], [])
        self.assertEqual(jobs[0]['location'], '부산 사상구 사상로 25')

    def test_new_job_without_location_is_marked_unknown(self):
        item = self.job('55260005', '웹디자이너')
        item.pop('location')
        incoming = validated_job(item)
        jobs = []
        apply_imports(jobs, {'postings': []}, [incoming], [])
        self.assertEqual(jobs[0]['location'], '정확한 근무지 주소 미확인')

    def test_stale_recent_listing_becomes_unverified_not_closed(self):
        job = self.job('55260011', '마케팅', '2026-11-20', 'recently_listed')
        job['listing_checked_at'] = '2026-10-17'
        job['listing_evidence'] = 'Search result from Oct 17'
        result, closed, stats = maintain([job], {'postings': []}, dt.date(2026, 10, 21))
        self.assertEqual(result[0]['status'], '재확인 필요')
        self.assertEqual(result[0]['listing_checked_at'], '2026-10-17')
        self.assertEqual(closed['postings'], [])
        self.assertEqual(stats['stale_evidence'], 1)

    def test_recent_evidence_stays_recent(self):
        job = self.job('55260012', '디자인', '2026-11-20', 'recently_listed')
        job['listing_checked_at'] = '2026-10-20'
        job['listing_evidence'] = 'Oct 20 listing from Saramin'
        result, _, stats = maintain([job], {'postings': []}, dt.date(2026, 10, 21))
        self.assertEqual(result[0]['status'], 'recently_listed')
        self.assertEqual(stats['stale_evidence'], 0)

    def test_yesterday_verified_must_not_still_claim_current(self):
        job = self.job('55260013', '디자인', '2026-11-20', 'verified_open')
        job['verified_at'] = '2026-10-20'
        job['verification_evidence'] = 'Button was seen yesterday'
        job['verified_source_url'] = job['url']
        result, closed, _ = maintain([job], {'postings': []}, dt.date(2026, 10, 21))
        self.assertEqual(result[0]['status'], '재확인 필요')
        self.assertEqual(closed['postings'], [])

    def test_verified_on_today_with_proper_evidence_remains(self):
        job = self.job('55260014', '디자인', '2026-11-20', 'verified_open')
        job['verified_at'] = '2026-10-21'
        job['verification_evidence'] = 'Currently visible application control'
        job['verified_source_url'] = job['url']
        result, _, stats = maintain([job], {'postings': []}, dt.date(2026, 10, 21))
        self.assertEqual(result[0]['status'], 'verified_open')
        self.assertEqual(stats['stale_evidence'], 0)

    def test_search_snippet_cannot_claim_verified_open(self):
        job = self.job('55260020', '디자인', (dt.date.today() + dt.timedelta(days=3)).isoformat(), 'verified_open')
        job['verified_at'] = dt.date.today().isoformat()
        job['verification_evidence'] = 'Google snippet says 입사지원'
        job['verified_source_url'] = job['url']
        entry = validated_job(job)
        self.assertEqual(entry['status'], '재확인 필요')

    def test_actual_ui_button_evidence_can_verify_open(self):
        job = self.job('55260021', '디자인', (dt.date.today() + dt.timedelta(days=3)).isoformat(), 'verified_open')
        job['verified_at'] = dt.date.today().isoformat()
        job['verification_evidence'] = 'User screenshot, red enabled 입사지원 bottom button'
        job['verified_source_url'] = job['url']
        job['application_button_state'] = 'apply_enabled'
        job['application_evidence_kind'] = 'user_screenshot'
        job['application_checked_at'] = dt.date.today().isoformat()
        entry = validated_job(job)
        self.assertEqual(entry['status'], 'verified_open')
        self.assertEqual(entry['application_button_state'], 'apply_enabled')

    def test_outdated_visual_button_evidence_not_current(self):
        job = self.job('55260022', '디자인', (dt.date.today() + dt.timedelta(days=3)).isoformat(), 'verified_open')
        job['verified_at'] = dt.date.today().isoformat()
        job['verification_evidence'] = 'Prior screenshot'
        job['verified_source_url'] = job['url']
        job['application_button_state'] = 'apply_enabled'
        job['application_evidence_kind'] = 'user_screenshot'
        job['application_checked_at'] = (dt.date.today()-dt.timedelta(days=1)).isoformat()
        self.assertEqual(validated_job(job)['status'], '재확인 필요')

    def test_explicitly_closed_job_never_imported_as_open_candidate(self):
        job = self.job('55260023', '디자인')
        job['application_button_state'] = 'closed'
        with self.assertRaises(ValueError):
            validated_job(job)

    def test_closed_posting_requires_visual_button_state(self):
        today = dt.date.today().isoformat()
        base = {'id':'55260024', 'reason':'접수마감 확인',
                'closed_confirmed': today, 'evidence_url':
                'https://m.saramin.co.kr/job-search/view?rec_idx=55260024'}
        import json
        with self.assertRaises(ValueError):
            parse_issue({'body': json.dumps({'jobs': [], 'closed_postings': [base]})})
        base['application_button_state'] = 'closed'
        base['application_evidence_kind'] = 'user_screenshot'
        base['application_checked_at'] = today
        incoming, closed = parse_issue({'body':json.dumps({'jobs': [],'closed_postings':[base]})})
        self.assertEqual(incoming, [])
        self.assertEqual(closed[0]['id'], '55260024')
        self.assertEqual(closed[0]['application_button_state'], 'closed')

    def test_exact_posting_url_extraction(self):
        self.assertEqual(posting_id(self.job('55260001', '디자인')), '55260001')


if __name__ == '__main__':
    unittest.main()

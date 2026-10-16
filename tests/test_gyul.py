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

    def test_exact_posting_url_extraction(self):
        self.assertEqual(posting_id(self.job('55260001', '디자인')), '55260001')


if __name__ == '__main__':
    unittest.main()

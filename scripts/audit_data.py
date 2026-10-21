#!/usr/bin/env python3
"""Read-only report of real data quality; never infer current application state."""
import json
from collections import Counter
from pathlib import Path
from cleanup import posting_id, today
from status_rules import effective_status

ROOT = Path(__file__).resolve().parents[1]


def main():
    jobs = json.loads((ROOT/'data/jobs.json').read_text())
    closed = json.loads((ROOT/'data/closed-postings.json').read_text())
    ledger = json.loads((ROOT/'data/observations.json').read_text())
    ids = [posting_id(j) for j in jobs if posting_id(j)]
    blocked = {str(row['id']) for row in closed['postings']}
    visible = [j for j in jobs if posting_id(j) and posting_id(j) not in blocked
               and effective_status(j, today()) not in {'closed_by_ui', 'expired_by_date'}]
    states = Counter(effective_status(j, today()) for j in visible)
    report = {'source_jobs': len(jobs), 'publishable_jobs': len(visible),
              'pending_identity': len(jobs)-len(ids), 'duplicate_ids': len(ids)-len(set(ids)),
              'closed_ids_in_jobs': sorted(set(ids) & blocked), 'effective_status': dict(states),
              'observations': len(ledger['observations']),
              'workplace_coordinates': sum(bool(j.get('workplace_coordinates')) for j in visible),
              'sourced_transit_routes': sum(bool(j.get('commute')) for j in visible),
              'sourced_company_employee_metrics': sum(bool(j.get('company_info', {}).get('employees')) for j in visible)}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report['duplicate_ids'] or report['closed_ids_in_jobs']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

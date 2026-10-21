#!/usr/bin/env python3
"""Validate a browser export locally; optional apply never contacts GitHub/Saramin."""
import argparse
import copy
import json
from pathlib import Path

from cleanup import JOBS, CLOSED, write_if_changed, posting_id
from import_issues import parse_issue, apply_imports, parse_research_report
from observations import parse_observations, merge_observations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--apply', action='store_true', help='Write reviewed batch into local checkout, never commit/push')
    args = parser.parse_args()
    text = args.input.read_text(encoding='utf-8')
    payload = json.loads(text)
    incoming, closures = parse_issue({'body': text})
    observations = parse_observations(payload)
    research = parse_research_report(payload)
    jobs = json.loads(JOBS.read_text(encoding='utf-8'))
    closed = json.loads(CLOSED.read_text(encoding='utf-8'))
    path = JOBS.parent / 'observations.json'
    ledger = json.loads(path.read_text(encoding='utf-8'))
    before = copy.deepcopy((jobs, closed, ledger))
    stats = apply_imports(jobs, closed, incoming, closures)
    merge_observations(ledger, observations)
    print(json.dumps({'mode': 'apply' if args.apply else 'dry_run', 'changes': stats,
                      'observations_added': len(ledger['observations']) - len(before[2]['observations']),
                      'removed_jobs': len({posting_id(j) for j in before[0]} - {posting_id(j) for j in jobs}), 'jobs_after': len(jobs)}, ensure_ascii=False))
    if args.apply:
        write_if_changed(JOBS, jobs)
        write_if_changed(CLOSED, closed)
        write_if_changed(path, ledger)
        if research:
            report_path = JOBS.parent / 'research-report.json'
            report_path.write_text(json.dumps(dict(research, new_jobs_added=stats['added'], closed_jobs_removed=stats['closed']),
                                              ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print('Local files updated. Review diff and update meta before committing the batch together. No deployment performed.')


if __name__ == '__main__':
    main()

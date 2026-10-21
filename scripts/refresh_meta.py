#!/usr/bin/env python3
"""Update metadata only when workflow found actual job/closure data changes.

The workflow commits metadata together with the underlying data atomically.
"""
import datetime as dt
import json
from pathlib import Path
from status_rules import effective_status
from cleanup import posting_id

ROOT = Path(__file__).resolve().parents[1]
KST = dt.timezone(dt.timedelta(hours=9))


def main():
    jobs = json.loads((ROOT / 'data/jobs.json').read_text(encoding='utf-8'))
    closed = json.loads((ROOT / 'data/closed-postings.json').read_text(encoding='utf-8'))
    meta_file = ROOT / 'data/meta.json'
    meta = json.loads(meta_file.read_text(encoding='utf-8'))
    now = dt.datetime.now(KST)
    meta['last_updated_at'] = now.isoformat(timespec='seconds')
    meta['last_review_date'] = now.date().isoformat()
    meta['source_total'] = len(jobs)
    blocked = {str(row.get('id')) for row in closed['postings']}
    visible = [j for j in jobs if posting_id(j) and posting_id(j) not in blocked
               and effective_status(j, now.date()) not in {'closed_by_ui', 'expired_by_date'}]
    meta['pending_identity'] = sum(not posting_id(j) for j in jobs)
    meta['total'] = len(visible)
    meta['visible_categories'] = {
        'confirmed_open': sum(effective_status(j, now.date()) == 'verified_open' for j in visible),
        'recent_public_listing': sum(effective_status(j, now.date()) == 'recently_listed' for j in visible),
        'unverified': sum(effective_status(j, now.date()) == 'unknown' for j in visible),
    }
    meta['removed_closed_posting_ids'] = [str(p['id']) for p in closed['postings']]
    meta.pop('note', None)
    meta['update_policy'] = ('ChatGPT research via owner-submitted GitHub Issues; '
                             'GitHub Actions local-only validation/maintenance every 2 hours; '
                             'no automated Saramin crawler')
    # A SHA stored inside the commit cannot identify that same commit.
    meta.pop('last_data_commit', None)
    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('GYUL metadata staged for atomic data commit')


if __name__ == '__main__':
    main()

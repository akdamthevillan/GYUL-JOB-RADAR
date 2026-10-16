#!/usr/bin/env python3
"""Update metadata only when workflow found actual job/closure data changes.

The workflow commits metadata together with the underlying data atomically.
"""
import datetime as dt
import json
from pathlib import Path

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
    meta['total'] = len(jobs)
    meta['visible_categories'] = {
        'confirmed_open': sum(j.get('status') == 'verified_open' for j in jobs),
        'recent_public_listing': sum(j.get('status') == 'recently_listed' for j in jobs),
        'unverified': sum(j.get('status') not in ('verified_open', 'recently_listed') for j in jobs),
    }
    meta['removed_closed_posting_ids'] = [str(p['id']) for p in closed['postings']]
    meta['update_policy'] = ('ChatGPT research via owner-submitted GitHub Issues; '
                             'GitHub Actions local-only validation/maintenance every 2 hours; '
                             'no automated Saramin crawler')
    # A SHA stored inside the commit cannot identify that same commit.
    meta.pop('last_data_commit', None)
    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('GYUL metadata staged for atomic data commit')


if __name__ == '__main__':
    main()

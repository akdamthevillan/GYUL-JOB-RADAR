#!/usr/bin/env python3
"""Track requested search coverage without pretending to execute remote searches."""
import argparse
import datetime as dt
import json
from pathlib import Path
from status_rules import KST

ROOT = Path(__file__).resolve().parents[1]


def create_session(config):
    strategy = config['search_strategy']
    keywords = list(dict.fromkeys(strategy['primary_keywords'] + strategy['additional_keywords']))
    return {'started_at': dt.datetime.now(KST).isoformat(timespec='seconds'),
            'tasks': [{'region': region, 'keyword': keyword, 'state': 'pending', 'pages': [],
                       'posting_ids': [], 'note': ''}
                      for region in strategy['regions'] for keyword in keywords]}


def summarize(session):
    tasks = session['tasks']
    completed = sum(t['state'] == 'completed' for t in tasks)
    return {'total_searches': len(tasks), 'completed_searches': completed,
            'blocked_searches': sum(t['state'] == 'blocked' for t in tasks),
            'pending_searches': sum(t['state'] == 'pending' for t in tasks),
            'partial_searches': sum(t['state'] == 'partial' for t in tasks),
            'completion_percent': round(completed / len(tasks) * 100, 1) if tasks else 0,
            'unique_postings_encountered': len({pid for t in tasks for pid in t['posting_ids']})}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['init', 'record', 'report'])
    parser.add_argument('--file', type=Path, required=True)
    parser.add_argument('--region')
    parser.add_argument('--keyword')
    parser.add_argument('--state', choices=['pending', 'partial', 'blocked', 'completed'])
    parser.add_argument('--page', action='append', default=[])
    parser.add_argument('--posting-id', action='append', default=[])
    parser.add_argument('--note', default='')
    args = parser.parse_args()
    if args.command == 'init':
        if args.file.exists():
            parser.error('session already exists; record/report it instead of overwriting')
        config = json.loads((ROOT/'data/search-config.json').read_text())
        session = create_session(config)
    else:
        session = json.loads(args.file.read_text())
    if args.command == 'record':
        matches = [t for t in session['tasks'] if t['region'] == args.region and t['keyword'] == args.keyword]
        if len(matches) != 1 or not args.state:
            parser.error('record requires an existing region/keyword and --state')
        import re
        if any(not re.fullmatch(r'\d{5,16}', pid) for pid in args.posting_id):
            parser.error('posting IDs must be numeric Saramin rec_idx')
        task = matches[0]
        task.update(state=args.state, note=args.note, updated_at=dt.datetime.now(KST).isoformat(timespec='seconds'))
        task['pages'] = list(dict.fromkeys(task['pages'] + args.page))
        task['posting_ids'] = list(dict.fromkeys(task['posting_ids'] + args.posting_id))
        if args.state == 'completed' and not task['pages']:
            parser.error('completed search requires actual inspected page references, including zero-result searches')
    if args.command != 'report':
        args.file.parent.mkdir(parents=True, exist_ok=True)
        args.file.write_text(json.dumps(session, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(summarize(session), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

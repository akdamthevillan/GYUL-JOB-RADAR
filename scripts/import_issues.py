#!/usr/bin/env python3
"""Owner-only GitHub Issue intake for curated Saramin job candidates.

An Issue is a transport, NOT evidence of a live application button.
This module never visits Saramin, submits an application, or uses a Kakao API.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from cleanup import CLOSED, JOBS, posting_id, today, write_if_changed

MARKER = '[GYUL-IMPORT]'
API = 'https://api.github.com'
ALLOWED_HOSTS = {'www.saramin.co.kr', 'saramin.co.kr', 'www2.saramin.co.kr', 'm.saramin.co.kr'}
STATUS = {'verified_open', 'recently_listed', '재확인 필요'}
FIELDS = {'company', 'title', 'location', 'category', 'salary', 'benefits', 'experience',
          'employment', 'deadline', 'deadline_text', 'considerations', 'score',
          'verified_at', 'status', 'source_checked_at', 'posted_at',
          'posted_date_source', 'listing_checked_at', 'listing_evidence',
          'listing_source_url', 'verification_evidence', 'verified_source_url',
          'application_start'}


def github_api(method, path, payload=None):
    token = os.environ['GH_TOKEN']
    body = json.dumps(payload).encode('utf-8') if payload is not None else None
    request = urllib.request.Request(API + path, data=body, method=method,
        headers={'Authorization': 'Bearer ' + token,
                 'Accept': 'application/vnd.github+json',
                 'X-GitHub-Api-Version': '2022-11-28',
                 'User-Agent': 'GYUL-JOB-RADAR-actions',
                 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=20) as response:
        content = response.read()
        return json.loads(content) if content else None


def pending_issues(repo, owner):
    result = []
    for page in range(1, 7):
        items = github_api('GET', f'/repos/{repo}/issues?state=open&per_page=100&page={page}')
        if not isinstance(items, list):
            raise ValueError('GitHub Issues API returned invalid data')
        for issue in items:
            if ('pull_request' not in issue and
                    (issue.get('user') or {}).get('login', '').casefold() == owner.casefold() and
                    str(issue.get('title', '')).startswith(MARKER)):
                result.append(issue)
        if len(items) < 100:
            return result
    raise RuntimeError('Over 600 open issues; refusing partial queue processing')


def saramin_url(url, expected_id):
    if not isinstance(url, str) or len(url) > 2000:
        return False
    try:
        parts = urlsplit(url)
        if parts.scheme != 'https' or parts.hostname not in ALLOWED_HOSTS:
            return False
        if parts.username or parts.password or parts.port:
            return False
        if parts.path not in ('/zf_user/jobs/view', '/job-search/view'):
            return False
        return parse_qs(parts.query).get('rec_idx', [''])[0] == expected_id
    except (TypeError, ValueError):
        return False


def date_ok(value):
    if value is None:
        return True
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return False
    try:
        dt.date.fromisoformat(value)
        return True
    except ValueError:
        return False


def validated_job(raw):
    if not isinstance(raw, dict):
        raise ValueError('job must be an object')
    pid = str(raw.get('id') or '')
    if not re.fullmatch(r'\d{5,16}', pid) or not saramin_url(raw.get('url'), pid):
        raise ValueError('job requires matching numeric Saramin id and posting URL')
    for k in ('company', 'title'):
        if not isinstance(raw.get(k), str) or not raw[k].strip():
            raise ValueError(f'job {pid}: missing {k}')
    for k in ('deadline', 'verified_at', 'listing_checked_at', 'source_checked_at'):
        if k in raw and not date_ok(raw[k]):
            raise ValueError(f'job {pid}: invalid {k}')
    if raw.get('deadline') and raw['deadline'] < today().isoformat():
        raise ValueError(f'job {pid}: past deadline; do not import')
    for k in FIELDS:
        value = raw.get(k)
        if value is not None and not isinstance(value, (str, int, float)):
            raise ValueError(f'job {pid}: {k} must be scalar')
        if isinstance(value, str) and len(value) > 4000:
            raise ValueError(f'job {pid}: {k} too long')
    status = raw.get('status', '재확인 필요')
    if status not in STATUS:
        raise ValueError(f'job {pid}: invalid status')
    entry = {k: raw[k] for k in FIELDS if k in raw and raw[k] is not None}
    if status == 'verified_open' and not (
        entry.get('verified_at') == today().isoformat() and
        entry.get('verification_evidence') and
        saramin_url(entry.get('verified_source_url'), pid)
    ):
        status = '재확인 필요'
        entry.pop('verified_at', None)
        entry.pop('verification_evidence', None)
        entry.pop('verified_source_url', None)
    if status == 'recently_listed' and not (
        entry.get('listing_checked_at') and entry.get('listing_evidence') and
        entry.get('deadline') and
        entry['listing_checked_at'] <= today().isoformat() and
        entry['listing_checked_at'] >= (today() - dt.timedelta(days=3)).isoformat() and
        entry['deadline'] >= today().isoformat()
    ):
        status = '재확인 필요'
    entry['status'] = status
    entry['id'] = pid
    entry['url'] = raw['url']
    entry['source'] = '사람인'
    entry['location'] = str(raw.get('location') or '정확한 근무지 주소 미확인')
    return entry


def parse_issue(issue):
    body = str(issue.get('body') or '').strip()
    if len(body) > 100_000:
        raise ValueError('issue body too large')
    match = re.fullmatch(r'\x60\x60\x60(?:json)?\s*\n(.*?)\n\x60\x60\x60', body, re.DOTALL)
    if match:
        body = match.group(1)
    payload = json.loads(body)
    if not isinstance(payload, dict) or not isinstance(payload.get('jobs', []), list) or not isinstance(payload.get('closed_postings', []), list):
        raise ValueError('expected JSON object with jobs and/or closed_postings arrays')
    if set(payload) - {'jobs', 'closed_postings'}:
        raise ValueError('unexpected payload fields')
    if len(payload.get('jobs', [])) > 40 or len(payload.get('closed_postings', [])) > 40:
        raise ValueError('too many changes in one issue')
    jobs = [validated_job(item) for item in payload.get('jobs', [])]
    closed = []
    for item in payload.get('closed_postings', []):
        if not isinstance(item, dict):
            raise ValueError('closed_postings entries must be objects')
        pid = str(item.get('id') or '')
        reason = str(item.get('reason') or '')
        if (not re.fullmatch(r'\d{5,16}', pid) or
            not any(x in reason for x in ('접수마감', '채용마감', '지원마감')) or
            not saramin_url(item.get('evidence_url'), pid) or
            not date_ok(item.get('closed_confirmed')) or not item.get('closed_confirmed') or
            item['closed_confirmed'] > today().isoformat()):
            raise ValueError(f'invalid closure evidence for {pid}')
        closed.append({'id': pid, 'closed_confirmed': item['closed_confirmed'],
                       'reason': reason[:300], 'evidence_url': item['evidence_url']})
    return jobs, closed


def apply_imports(jobs, closed_data, incoming, closures):
    """Idempotent; never excludes an unrelated posting from the same company."""
    ids = {posting_id(job): i for i, job in enumerate(jobs) if posting_id(job)}
    blocked = {str(row.get('id')) for row in closed_data['postings'] if isinstance(row, dict)}
    stats = {'added': 0, 'updated': 0, 'closed': 0}
    for entry in incoming:
        pid = entry['id']
        if pid in blocked:
            continue
        if pid in ids:
            previous = jobs[ids[pid]]
            merged = dict(previous)
            for k, v in entry.items():
                if k == 'status' and previous.get('status') == 'verified_open' and v != 'verified_open':
                    # Preserve past evidence; the UI itself handles expiry of verification dates.
                    continue
                if v not in (None, ''):
                    merged[k] = v
            if merged != previous:
                jobs[ids[pid]] = merged
                stats['updated'] += 1
        else:
            record = {'company': entry['company'], 'title': entry['title'],
                      'salary': '미공개', 'benefits': '미공개',
                      'experience': '원문 확인', 'employment': '원문 확인',
                      'category': '기타', 'first_seen': today().isoformat()}
            record.update(entry)
            ids[pid] = len(jobs)
            jobs.append(record)
            stats['added'] += 1
    for entry in closures:
        pid = entry['id']
        if pid not in blocked:
            closed_data['postings'].append(entry)
            blocked.add(pid)
            stats['closed'] += 1
    if blocked:
        before = len(jobs)
        jobs[:] = [job for job in jobs if posting_id(job) not in blocked]
        stats['closed'] += before - len(jobs)
    return stats


def prepare(repo, owner, manifest):
    jobs = json.loads(JOBS.read_text(encoding='utf-8'))
    closed = json.loads(CLOSED.read_text(encoding='utf-8'))
    if not isinstance(jobs, list) or not isinstance(closed, dict) or not isinstance(closed.get('postings'), list):
        raise ValueError('Invalid existing job JSON structure')
    processed = []
    totals = {'added': 0, 'updated': 0, 'closed': 0}
    for issue in pending_issues(repo, owner):
        try:
            incoming, closures = parse_issue(issue)
            stats = apply_imports(jobs, closed, incoming, closures)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            print(f'Issue #{issue.get("number")}: rejected ({exc})', file=sys.stderr)
            continue
        for key in totals:
            totals[key] += stats[key]
        processed.append({'number': issue['number'], 'updated_at': issue['updated_at']})
    write_if_changed(JOBS, jobs)
    write_if_changed(CLOSED, closed)
    Path(manifest).write_text(json.dumps(processed), encoding='utf-8')
    print(f'Issue intake: accepted={len(processed)} added={totals["added"]} '
          f'updated={totals["updated"]} closures={totals["closed"]}')


def acknowledge(repo, manifest):
    if not Path(manifest).exists():
        raise FileNotFoundError('Missing accepted-issue manifest')
    for accepted in json.loads(Path(manifest).read_text(encoding='utf-8')):
        number = accepted['number']
        issue = github_api('GET', f'/repos/{repo}/issues/{number}')
        # Do not close a candidate whose body changed while the commit was being written.
        if issue.get('updated_at') != accepted['updated_at'] or issue.get('state') != 'open':
            print(f'Issue #{number} changed; leaving for next run')
            continue
        github_api('PATCH', f'/repos/{repo}/issues/{number}', {'state': 'closed'})
        print(f'Issue #{number} marked processed')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('prepare', 'acknowledge'))
    parser.add_argument('--repo', default=os.environ.get('GITHUB_REPOSITORY', ''))
    parser.add_argument('--owner', default=os.environ.get('GITHUB_REPOSITORY_OWNER', ''))
    parser.add_argument('--manifest', required=True)
    args = parser.parse_args()
    if not args.repo or not args.owner or args.repo.split('/')[0].casefold() != args.owner.casefold():
        parser.error('invalid repo owner')
    if args.command == 'prepare':
        prepare(args.repo, args.owner, args.manifest)
    else:
        acknowledge(args.repo, args.manifest)


if __name__ == '__main__':
    main()

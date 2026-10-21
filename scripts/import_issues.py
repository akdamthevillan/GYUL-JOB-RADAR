#!/usr/bin/env python3
"""Owner-only GitHub Issue intake for curated Saramin job candidates.

An Issue is a transport, NOT evidence of a live application button.
This module never visits Saramin, submits an application, or uses a Kakao API.
"""
import argparse
import copy
import datetime as dt
import json
import math
import os
import re
import sys
import urllib.request
from pathlib import Path

from cleanup import CLOSED, JOBS, posting_id, today, write_if_changed
from status_rules import effective_status, saramin_url
from observations import parse_observations, merge_observations, validate_details

MARKER = '[GYUL-IMPORT]'
API = 'https://api.github.com'
STATUS = {'verified_open', 'recently_listed', '재확인 필요'}
FIELDS = {'company', 'title', 'location', 'category', 'salary', 'benefits', 'experience',
          'employment', 'deadline', 'deadline_text', 'considerations', 'score',
          'verified_at', 'status', 'source_checked_at', 'posted_at',
          'posted_date_source', 'listing_checked_at', 'listing_evidence',
          'listing_source_url', 'verification_evidence', 'verified_source_url',
          'application_start', 'application_button_state', 'application_evidence_kind',
          'application_checked_at', 'application_method', 'work_schedule', 'duties', 'company_business', 'company_url'}


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
    for k in ('deadline', 'verified_at', 'listing_checked_at', 'source_checked_at', 'application_checked_at'):
        if k in raw and not date_ok(raw[k]):
            raise ValueError(f'job {pid}: invalid {k}')
    if raw.get('deadline') and raw['deadline'] < today().isoformat() and effective_status(raw, today()) != 'verified_open':
        raise ValueError(f'job {pid}: past deadline; do not import')
    for k in FIELDS:
        value = raw.get(k)
        if value is not None and not isinstance(value, (str, int, float)):
            raise ValueError(f'job {pid}: {k} must be scalar')
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f'job {pid}: {k} must be finite')
        if isinstance(value, str) and len(value) > 4000:
            raise ValueError(f'job {pid}: {k} too long')
    status = raw.get('status', '재확인 필요')
    if status not in STATUS:
        raise ValueError(f'job {pid}: invalid status')
    # Search snippets never prove a live application button.
    button = raw.get('application_button_state')
    method = raw.get('application_evidence_kind')
    if button not in (None, 'apply_enabled', 'closed', 'unknown'):
        raise ValueError(f'job {pid}: invalid application button state')
    if method not in (None, 'user_screenshot', 'browser_visual', 'page_dom'):
        raise ValueError(f'job {pid}: invalid application evidence kind')
    if button == 'closed':
        raise ValueError(f'job {pid}: explicitly closed buttons must go to closed_postings')
    entry = {k: raw[k] for k in FIELDS if k in raw and raw[k] is not None}
    if status in {'verified_open', 'recently_listed'}:
        candidate = dict(entry, id=pid, url=raw['url'], status=status)
        if effective_status(candidate, today()) != status:
            status = '재확인 필요'
    entry.update(validate_details(raw))
    entry['status'] = status
    entry['id'] = pid
    entry['url'] = raw['url']
    entry['source'] = '사람인'
    # A partial Issue update must never erase a previously confirmed workplace address.
    # New records receive the default location in apply_imports() instead.
    if 'location' in raw:
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
    if set(payload) - {'jobs', 'closed_postings', 'observations'}:
        raise ValueError('unexpected payload fields')
    if len(payload.get('jobs', [])) > 40 or len(payload.get('closed_postings', [])) > 40:
        raise ValueError('too many changes in one issue')
    parse_observations(payload)
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
            item['closed_confirmed'] > today().isoformat() or
            item.get('application_button_state') != 'closed' or
            item.get('application_evidence_kind') not in ('user_screenshot', 'browser_visual', 'page_dom') or
            item.get('application_checked_at') != item.get('closed_confirmed')):
            raise ValueError(f'invalid closure evidence for {pid}')
        closed.append({'id': pid, 'closed_confirmed': item['closed_confirmed'],
                       'reason': reason[:300], 'evidence_url': item['evidence_url'],
                       'application_button_state': 'closed',
                       'application_evidence_kind': item['application_evidence_kind'],
                       'application_checked_at': item['application_checked_at'],
                       'closure_kind': 'closed_by_ui'})
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
                if k == 'location' and (not str(v).strip() or any(word in str(v) for word in ('미확인', '미공개', '확인 필요'))):
                    continue
                if k == 'company_info' and isinstance(v, dict):
                    merged[k] = {**previous.get(k, {}), **v}
                elif v not in (None, ''):
                    merged[k] = v
            if merged != previous:
                jobs[ids[pid]] = merged
                stats['updated'] += 1
        else:
            record = {'company': entry['company'], 'title': entry['title'],
                      'location': '정확한 근무지 주소 미확인',
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
            record = dict(entry)
            original = next((dict(job) for job in jobs if posting_id(job) == pid), None)
            if original:
                record['snapshot'] = original
            closed_data['postings'].append(record)
            blocked.add(pid)
            stats['closed'] += 1
    if blocked:
        jobs[:] = [job for job in jobs if posting_id(job) not in blocked]
    return stats


def prepare(repo, owner, manifest):
    jobs = json.loads(JOBS.read_text(encoding='utf-8'))
    closed = json.loads(CLOSED.read_text(encoding='utf-8'))
    if not isinstance(jobs, list) or not isinstance(closed, dict) or not isinstance(closed.get('postings'), list):
        raise ValueError('Invalid existing job JSON structure')
    observation_path = JOBS.parent / 'observations.json'
    ledger = json.loads(observation_path.read_text(encoding='utf-8')) if observation_path.exists() else {'observations': []}
    processed = []
    rejected = []
    totals = {'added': 0, 'updated': 0, 'closed': 0}
    for issue in pending_issues(repo, owner):
        try:
            incoming, closures = parse_issue(issue)
            body = str(issue.get('body') or '').strip()
            match = re.fullmatch(r'`{3}(?:json)?\s*\n(.*?)\n`{3}', body, re.DOTALL)
            observations = parse_observations(json.loads(match.group(1) if match else body))
            staged_jobs, staged_closed = copy.deepcopy(jobs), copy.deepcopy(closed)
            stats = apply_imports(staged_jobs, staged_closed, incoming, closures)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            rejected.append({'number': issue.get('number'), 'reason': str(exc)})
            print(f'Issue #{issue.get("number")}: rejected ({exc})', file=sys.stderr)
            continue
        jobs, closed = staged_jobs, staged_closed
        merge_observations(ledger, observations)
        for key in totals:
            totals[key] += stats[key]
        processed.append({'number': issue['number'], 'updated_at': issue['updated_at']})
    write_if_changed(JOBS, jobs)
    write_if_changed(CLOSED, closed)
    if observation_path.exists():
        write_if_changed(observation_path, ledger)
    else:
        observation_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as report:
            report.write(f'## 공고 입력 결과\n정상 {len(processed)}건 · 반려 {len(rejected)}건\n')
            for row in rejected:
                report.write(f"- Issue #{row['number']}: 형식·근거 검증 실패 (실행 로그 확인)\n")
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

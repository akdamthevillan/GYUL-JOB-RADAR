#!/usr/bin/env python3
"""Safe, local-only maintenance of curated GYUL JOB RADAR jobs.

Never accesses Saramin. Never drops entries solely because of incomplete data.
Only expired deadlines and explicitly closed statuses are removed.
"""
import datetime as dt
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from status_rules import effective_status, saramin_url

ROOT = Path(__file__).resolve().parents[1]
JOBS = ROOT / 'data' / 'jobs.json'
CLOSED = ROOT / 'data' / 'closed-postings.json'
CLOSED_STATES = {'closed', 'expired', '마감', '접수마감', '채용마감', '지원마감'}
KST = dt.timezone(dt.timedelta(hours=9))


def today():
    return dt.datetime.now(KST).date()


def posting_id(job):
    """Only an actual Saramin rec_idx identifies a Saramin posting."""
    try:
        url = urlsplit(str(job.get('url') or ''))
        if url.hostname not in {'saramin.co.kr', 'www.saramin.co.kr',
                                'www2.saramin.co.kr', 'm.saramin.co.kr'}:
            return None
        value = parse_qs(url.query).get('rec_idx', [''])[0]
        return value if re.fullmatch(r'\d{5,16}', value) and saramin_url(job.get('url'), value) else None
    except (TypeError, ValueError):
        return None


def has_expired(job, on_date):
    deadline = job.get('deadline')
    if not isinstance(deadline, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', deadline):
        return False
    try:
        return dt.date.fromisoformat(deadline) < on_date
    except ValueError:
        return False


def confirmed_closed(job):
    return str(job.get('status') or '').strip().lower() in CLOSED_STATES


def status_after_evidence_check(job, on_date):
    """Expire evidence labels, never infer that the job itself has closed."""
    state = effective_status(job, on_date)
    return state if state in {'verified_open', 'recently_listed'} else '재확인 필요'


def quality(job):
    return sum(bool(job.get(k)) for k in
               ('location', 'salary', 'benefits', 'experience', 'employment',
                'verified_at', 'verification_evidence', 'listing_evidence', 'posted_at'))


def maintain(jobs, closed, on_date=None):
    on_date = on_date or today()
    if not isinstance(jobs, list) or not isinstance(closed, dict) or not isinstance(closed.get('postings'), list):
        raise ValueError('Invalid jobs.json or closed-postings.json structure')
    known = {str(x.get('id')) for x in closed['postings'] if isinstance(x, dict) and x.get('id')}
    result, positions, removed, duplicates, stale = [], {}, 0, 0, 0
    for job in jobs:
        if not isinstance(job, dict):
            # Unknown data should fail safe, not vanish silently.
            raise ValueError('Non-object job entry must be corrected manually')
        pid = posting_id(job)
        if pid and (pid in known or effective_status(job, on_date) in {'closed_by_ui', 'expired_by_date'}):
            removed += 1
            if pid not in known:
                expired = effective_status(job, on_date) == 'expired_by_date'
                reason = '마감일 경과' if expired else '공고 상태 마감 확인'
                closed['postings'].append({'id': pid, 'closed_confirmed': on_date.isoformat(),
                                           'reason': reason, 'company': job.get('company', ''),
                                           'title': job.get('title', ''),
                                           'closure_kind': 'expired_by_date' if expired else 'closed_by_ui',
                                           'snapshot': dict(job)})
                known.add(pid)
            continue
        if not pid and (confirmed_closed(job) or has_expired(job, on_date)):
            # No Saramin posting ID: cannot record closure of that exact posting.
            # Retain for human review rather than risk an incorrect deletion.
            result.append(job)
            continue
        updated_state = status_after_evidence_check(job, on_date)
        if updated_state != job.get('status'):
            job = dict(job)
            job['status'] = updated_state
            stale += 1
        if pid and pid in positions:
            duplicates += 1
            prior = positions[pid]
            if quality(job) > quality(result[prior]):
                result[prior] = job
            continue
        if pid:
            positions[pid] = len(result)
        result.append(job)
    return result, closed, {'removed': removed, 'duplicates': duplicates, 'stale_evidence': stale}


def write_if_changed(path, value):
    original = json.loads(path.read_text(encoding='utf-8'))
    if original == value:
        return False
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return True


def main():
    jobs = json.loads(JOBS.read_text(encoding='utf-8'))
    closed = json.loads(CLOSED.read_text(encoding='utf-8'))
    new_jobs, new_closed, stats = maintain(jobs, closed)
    changed = write_if_changed(JOBS, new_jobs) | write_if_changed(CLOSED, new_closed)
    print(f'GYUL maintenance: changed={changed} removed={stats["removed"]} '
          f'duplicates={stats["duplicates"]} stale_evidence={stats["stale_evidence"]} jobs={len(new_jobs)}')


if __name__ == '__main__':
    main()

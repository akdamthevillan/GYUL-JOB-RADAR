"""Application observations and deadline expiry are separate facts.

Keep behavior in sync with assets/radar.js using shared fixture tests.
"""
import datetime as dt
import re
from urllib.parse import urlsplit, parse_qs

KST = dt.timezone(dt.timedelta(hours=9))
EVIDENCE_METHODS = {'user_screenshot', 'browser_visual', 'page_dom'}


def valid_date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return False
    try:
        dt.date.fromisoformat(value)
        return True
    except ValueError:
        return False


def saramin_url(url, expected_id):
    if not isinstance(url, str) or len(url) > 2000:
        return False
    try:
        parts = urlsplit(url)
        return (parts.scheme == 'https' and parts.hostname in
                {'saramin.co.kr', 'www.saramin.co.kr', 'www2.saramin.co.kr', 'm.saramin.co.kr'}
                and not parts.username and not parts.password and not parts.port
                and parts.path in ('/zf_user/jobs/view', '/job-search/view')
                and parse_qs(parts.query).get('rec_idx', [''])[0] == expected_id)
    except (TypeError, ValueError):
        return False


def effective_status(job, on_date):
    day = on_date.isoformat()
    pid = str(job.get('id') or '')
    if (job.get('status') == 'verified_open' and re.fullmatch(r'\d{5,16}', pid)
            and saramin_url(job.get('url'), pid)
            and job.get('verified_at') == day
            and job.get('application_checked_at') == day
            and job.get('application_button_state') == 'apply_enabled'
            and job.get('application_evidence_kind') in EVIDENCE_METHODS
            and str(job.get('verification_evidence') or '').strip()
            and saramin_url(job.get('verified_source_url'), pid)):
        return 'verified_open'
    if str(job.get('status', '')).lower() in {'closed', '마감', '접수마감', '채용마감', '지원마감'} or job.get('application_button_state') == 'closed':
        return 'closed_by_ui'
    if job.get('status') == 'expired' or (valid_date(job.get('deadline')) and job['deadline'] < day):
        return 'expired_by_date'
    if (job.get('status') == 'recently_listed'
            and valid_date(job.get('listing_checked_at'))
            and (on_date - dt.timedelta(days=3)).isoformat() <= job['listing_checked_at'] <= day
            and str(job.get('listing_evidence') or '').strip()
            and valid_date(job.get('deadline')) and job['deadline'] >= day):
        return 'recently_listed'
    return 'unknown'

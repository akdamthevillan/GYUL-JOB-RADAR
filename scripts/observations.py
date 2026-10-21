"""Append-only public observation metadata; never store private screenshots here."""
import datetime as dt
import hashlib
import json
import math
import re
from urllib.parse import urlsplit

from status_rules import KST, saramin_url, valid_date


def safe_url(value):
    try:
        u = urlsplit(value)
        return isinstance(value, str) and u.scheme == 'https' and bool(u.hostname) and not u.username and not u.password
    except (ValueError, TypeError, AttributeError):
        return False


def dated_source(value):
    return (isinstance(value, dict) and safe_url(value.get('source_url'))
            and valid_date(value.get('checked_at'))
            and value['checked_at'] <= dt.datetime.now(KST).date().isoformat())


def validate_details(raw):
    result = {}
    if 'company_info' in raw:
        info = raw['company_info']
        if not isinstance(info, dict):
            raise ValueError('company_info must be an object')
        for key, metric in info.items():
            if key not in {'employees', 'revenue', 'operating_profit', 'avg_salary', 'recent_hires', 'recent_leavers'}:
                raise ValueError('unknown company metric')
            if (not isinstance(metric, dict) or not safe_url(metric.get('source_url'))
                    or not any(metric.get(k) for k in ('year', 'period', 'as_of'))
                    or not isinstance(metric.get('value'), (str, int, float))):
                raise ValueError('company metrics require value, period and HTTPS source')
        result['company_info'] = info
    if 'workplace_coordinates' in raw:
        point = raw['workplace_coordinates']
        if (not dated_source(point) or any(type(point.get(k)) not in (int, float) or not math.isfinite(point[k]) for k in ('lat', 'lng'))
                or abs(point['lat']) > 90 or abs(point['lng']) > 180):
            raise ValueError('workplace coordinates require valid coordinates, source and date')
        result['workplace_coordinates'] = point
    if 'commute' in raw:
        trip = raw['commute']
        if (not dated_source(trip) or trip.get('origin') != '냉정역' or trip.get('mode') != 'transit'
                or type(trip.get('minutes')) not in (int, float) or not math.isfinite(trip['minutes']) or trip['minutes'] <= 0
                or ('transfers' in trip and (type(trip['transfers']) is not int or trip['transfers'] < 0))):
            raise ValueError('commute requires observed transit route from 냉정역, minutes, source and date')
        result['commute'] = trip
    return result


def parse_observations(payload):
    rows = payload.get('observations', [])
    if not isinstance(rows, list) or len(rows) > 80:
        raise ValueError('observations must be an array with at most 80 entries')
    result = []
    now = dt.datetime.now(KST)
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('observation must be an object')
        pid = str(row.get('id') or '')
        if not re.fullmatch(r'\d{5,16}', pid) or not saramin_url(row.get('source_url'), pid):
            raise ValueError('observation requires matching posting id and source URL')
        try:
            timestamp = dt.datetime.fromisoformat(row.get('observed_at', ''))
        except (TypeError, ValueError):
            raise ValueError('invalid observation timestamp') from None
        if timestamp.tzinfo is None or timestamp > now:
            raise ValueError('observation timestamp requires timezone and must not be in future')
        if row.get('result') not in {'apply_enabled', 'closed', 'unknown', 'external_apply'}:
            raise ValueError('invalid observation result')
        if row.get('method') not in {'user_screenshot', 'browser_visual', 'page_dom'}:
            raise ValueError('invalid observation method')
        evidence = row.get('evidence')
        if not isinstance(evidence, str) or not evidence.strip() or len(evidence) > 4000:
            raise ValueError('observation requires concise evidence')
        value = {key: row[key] for key in ('source_url', 'result', 'method', 'evidence')}
        value.update(id=pid, observed_at=timestamp.astimezone(KST).isoformat(timespec='seconds'))
        # Ref is an opaque local/private reference, not proof of truth or a public image URL.
        if row.get('evidence_ref'):
            if not isinstance(row['evidence_ref'], str) or len(row['evidence_ref']) > 300:
                raise ValueError('invalid evidence reference')
            value['evidence_ref'] = row['evidence_ref']
        key = json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
        value['observation_id'] = hashlib.sha256(key).hexdigest()
        result.append(value)
    return result


def merge_observations(ledger, incoming):
    if not isinstance(ledger, dict) or not isinstance(ledger.get('observations'), list):
        raise ValueError('invalid observation ledger')
    known = {row['observation_id'] for row in ledger['observations']}
    for row in incoming:
        if row['observation_id'] not in known:
            ledger['observations'].append(row)
            known.add(row['observation_id'])

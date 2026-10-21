#!/usr/bin/env python3
"""Read one public posting's actual HTML controls without clicking/applying.

No search crawler. Static HTML cannot prove CSS/JS behavior; ambiguous controls
remain unknown and can be checked in a rendered browser instead.
"""
import argparse
import datetime as dt
import json
import math
import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from status_rules import KST, saramin_url


class ApplicationControls(HTMLParser):
    def __init__(self, posting_id):
        super().__init__()
        self.posting_id = posting_id
        self.stack = []
        self.control = None
        self.controls = []
        self.text = []
        self.details = {}
        self.dl_mode = None
        self.dl_value = ''
        self.dl_key = ''
        self.sections = []

    def handle_starttag(self, tag, attributes):
        # Valueless attributes (e.g. <div style>) arrive as None.
        attrs = {key: value or '' for key, value in attributes}
        if tag in {'dt', 'dd'}:
            self.dl_mode, self.dl_value = tag, ''
        if 'jv_location' in attrs.get('class', '').split() and attrs.get('data-hide_fl') != 'y':
            address = attrs.get('data-address', '')
            if address:
                self.details['location'] = re.sub(r'^\(\d{5}\)\s*', '', address).strip()
            try:
                lat, lng = float(attrs['data-latitude']), float(attrs['data-longitude'])
                if math.isfinite(lat) and math.isfinite(lng) and abs(lat) <= 90 and abs(lng) <= 180 and (lat or lng):
                    self.details['workplace_coordinates'] = {'lat': lat, 'lng': lng, 'precision': 'posting_map'}
            except (ValueError, KeyError):
                pass
        hidden = (tag in {'script', 'style', 'template'} or 'hidden' in attrs or attrs.get('aria-hidden') == 'true'
                  or bool(re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', attrs.get('style', '')))
                  or bool(set(attrs.get('class', '').split()) & {'hidden', 'hide'}))
        inherited = any(item[1] for item in self.stack)
        if tag not in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}:
            self.stack.append((tag, hidden or inherited))
        field = {'template_welfare': 'benefits', 'template_recruitment_field': 'duties'}.get(attrs.get('id'))
        if field and not hidden and not inherited:
            self.sections.append({'field': field, 'depth': len(self.stack), 'text': ''})
        if tag in {'button', 'a'}:
            onclick = attrs.get('onclick', '')
            match = re.search(r"quickApply(?:Mobile|Form)\(['\"](\d+)['\"]", onclick)
            # Employer-site applications use a homepage control bound to the same posting number.
            homepage = attrs.get('data-rec_idx') == self.posting_id and re.search(r"btnJob\(\s*['\"]homepage", onclick)
            if (match and match[1] == self.posting_id) or homepage:
                self.control = {'tag': tag, 'class': attrs.get('class', ''), 'hidden': hidden or inherited,
                                'disabled': 'disabled' in attrs or attrs.get('aria-disabled') == 'true', 'text': '',
                                'route': 'homepage' if homepage else 'saramin'}

    def handle_endtag(self, tag):
        if self.dl_mode == tag:
            value = re.sub(r'\s+', ' ', self.dl_value).strip()
            if tag == 'dt':
                self.dl_key = value
            elif value:
                # 시작일 is the posting's opening date and serves as its registration date.
                date_field = {'마감일': 'deadline', '시작일': 'posted_at'}.get(self.dl_key)
                if date_field:
                    date = re.search(r'(20\d{2})[./-](\d{1,2})[./-](\d{1,2})', value)
                    if date:
                        try:
                            self.details[date_field] = dt.date(*(int(v) for v in date.groups())).isoformat()
                        except ValueError:
                            pass
                field = {'경력': 'experience', '근무형태': 'employment', '급여': 'salary', '근무일시': 'work_schedule', '지원방법': 'application_method', '업종': 'company_business'}.get(self.dl_key)
                if field and field not in self.details:
                    self.details[field] = value[:1000]
            self.dl_mode = None
        if self.control and tag == self.control['tag']:
            self.controls.append(self.control)
            self.control = None
        for index in range(len(self.stack)-1, -1, -1):
            if self.stack[index][0] == tag:
                for section in self.sections[:]:
                    if section['depth'] >= index+1:
                        value = re.sub(r'\s+', ' ', section['text']).strip()
                        if value:
                            self.details[section['field']] = value[:2000]
                        self.sections.remove(section)
                del self.stack[index:]
                break

    def handle_data(self, value):
        if self.dl_mode:
            self.dl_value += ' '+value
        hidden = any(item[1] for item in self.stack)
        if self.control:
            self.control['text'] += value
        if not hidden:
            self.text.append(value)
            for section in self.sections:
                section['text'] += ' '+value

    def outcome(self):
        controls = [dict(row, text=re.sub(r'\s+', ' ', row['text']).strip()) for row in self.controls if not row['hidden']]
        text = ' '.join(self.text)
        closed = any('expired' in row['class'] or row['text'] == '접수마감' for row in controls)
        closed = closed or bool(re.search(r'본\s*채용정보는\s*마감되었습니다', text))
        active = [row for row in controls if not row['disabled'] and (
            (row['route'] == 'saramin' and row['text'] in {'입사지원', '사람인 입사지원'}
             and bool(set(row['class'].split()) & {'sri_btn_immediately', 'for_btn_event'}))
            or (row['route'] == 'homepage' and row['text'] == '홈페이지 지원'))]
        state = 'closed' if closed else 'apply_enabled' if active else 'unknown'
        route = None
        if state == 'apply_enabled':
            route = 'saramin' if any(row['route'] == 'saramin' for row in active) else 'homepage'
        return {'result': state, 'apply_route': route, 'controls': controls, 'details': self.details,
                'evidence': ('현재 개별 공고 HTML의 공고번호 일치 지원 컨트롤: ' + json.dumps(controls, ensure_ascii=False))[:4000]}


def inspect_html(html, posting_id):
    parser = ApplicationControls(posting_id)
    parser.feed(html)
    return parser.outcome()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('--html-file', type=Path, help='Inspect an already fetched actual page or explicit fixture; makes no remote request')
    args = parser.parse_args()
    pid = parse_qs(urlsplit(args.url).query).get('rec_idx', [''])[0]
    if not re.fullmatch(r'\d{5,16}', pid) or not saramin_url(args.url, pid):
        parser.error('requires an individual Saramin HTTPS posting URL')
    observed = dt.datetime.now(KST).isoformat(timespec='seconds')
    try:
        if args.html_file:
            html = args.html_file.read_text(encoding='utf-8')
        else:
            request = urllib.request.Request(args.url, headers={'User-Agent': 'GYUL-JOB-RADAR personal posting review (github.com/akdamthevillan/GYUL-JOB-RADAR)'})
            with urllib.request.urlopen(request, timeout=25) as response:
                if not saramin_url(response.url, pid):
                    raise ValueError('redirected away from the selected posting')
                html = response.read(4 * 1024 * 1024).decode('utf-8', errors='replace')
        print(json.dumps(dict(id=pid, source_url=args.url, observed_at=observed, method='page_dom', **inspect_html(html, pid)), ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({'id': pid, 'source_url': args.url, 'observed_at': observed,
                          'method': 'page_dom', 'result': 'unknown', 'evidence': f'공고 접근 실패: {type(exc).__name__}: {exc}'}, ensure_ascii=False, indent=2))
        raise SystemExit(2) from None


if __name__ == '__main__':
    main()

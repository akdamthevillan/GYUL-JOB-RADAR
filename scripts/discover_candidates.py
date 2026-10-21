#!/usr/bin/env python3
"""One user-requested region/keyword/result page at a time; candidates are not verified jobs."""
import argparse
import datetime as dt
import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from status_rules import KST

# Codes observed in Saramin's public region selector, not guessed coordinates.
REGIONS = {'부산광역시 전체': ('loc_mcd', '106000', '부산'),
           '경남 김해시': ('loc_cd', '110040', '김해'),
           '경남 양산시': ('loc_cd', '110100', '양산')}
VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}


class CandidateParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.rows = [], []
        self.current = None
        self.depth = 0
        self.selected_sort = None

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        classes = set(attrs.get('class', '').split())
        if tag not in VOID:
            self.stack.append((tag, classes))
        if tag == 'button' and attrs.get('target') == 'sort' and attrs.get('position') == 'recruit' and any('selected' in group for _, group in self.stack):
            self.selected_sort = attrs.get('value')
        if tag == 'div' and 'item_recruit' in classes and re.fullmatch(r'\d{5,16}', attrs.get('value', '')):
            self.current = {'id': attrs['value'], 'company': '', 'company_url': '', 'title': '', 'conditions': '', 'sector': '', 'deadline_text': ''}
            self.depth = len(self.stack)
        if self.current and tag == 'a' and any('corp_name' in c for _, c in self.stack) and attrs.get('href', '').startswith('/zf_user/company-info/'):
            self.current['company_url'] = 'https://www.saramin.co.kr'+attrs['href']
        if self.current and tag == 'a' and any('job_tit' in c for _, c in self.stack) and attrs.get('title'):
            self.current['title'] = attrs['title']

    def handle_data(self, value):
        if not self.current:
            return
        classes = {c for _, group in self.stack for c in group}
        for css, field in [('corp_name', 'company'), ('job_condition', 'conditions'), ('job_sector', 'sector'), ('job_date', 'deadline_text')]:
            if css in classes:
                self.current[field] += ' '+value

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i][0] == tag:
                if self.current and i+1 <= self.depth:
                    row = {k: re.sub(r'\s+', ' ', v).strip() for k, v in self.current.items()}
                    row['deadline_text'] = re.sub(r'사람인\s*입사지원|입사지원|홈페이지\s*지원', '', row['deadline_text']).strip()
                    row['url'] = 'https://www.saramin.co.kr/zf_user/jobs/view?rec_idx='+row['id']
                    if row['title'] and row['company']:
                        self.rows.append(row)
                    self.current = None
                del self.stack[i:]
                break


def parse_candidates(html):
    parser = CandidateParser()
    parser.feed(html)
    seen, rows = set(), []
    for row in parser.rows:
        if row['id'] not in seen:
            seen.add(row['id'])
            rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--region', choices=REGIONS, required=True)
    parser.add_argument('--keyword', required=True)
    parser.add_argument('--page', type=int, default=1)
    parser.add_argument('--sort', choices=['reg_dt', 'relation'], default='reg_dt')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--html-file', type=Path)
    args = parser.parse_args()
    if not args.keyword.strip() or args.page < 1:
        parser.error('keyword and positive page required')
    field, code, label = REGIONS[args.region]
    url = 'https://www.saramin.co.kr/zf_user/search?'+urllib.parse.urlencode({'searchword':args.keyword, field:code, 'recruitPage':args.page, 'recruitSort':args.sort})
    if args.html_file:
        html = args.html_file.read_text(encoding='utf-8')
    else:
        request = urllib.request.Request(url, headers={'User-Agent':'GYUL-JOB-RADAR personal posting review (github.com/akdamthevillan/GYUL-JOB-RADAR)'})
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                html = response.read(6*1024*1024).decode('utf-8',errors='replace')
        except Exception as exc:
            result = {'region':args.region, 'keyword':args.keyword, 'page':args.page,
                      'source_url':url, 'state':'blocked', 'candidates':[],
                      'observed_at':dt.datetime.now(KST).isoformat(timespec='seconds'),
                      'error':f'{type(exc).__name__}: {exc}'}
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
            print(json.dumps(result, ensure_ascii=False))
            raise SystemExit(2) from None
    parsed = CandidateParser()
    parsed.feed(html)
    rows = parse_candidates(html)
    selected = [row for row in rows if label in row['conditions']]
    result = {'region':args.region, 'keyword':args.keyword, 'page':args.page, 'source_url':url,
              'observed_at':dt.datetime.now(KST).isoformat(timespec='seconds'), 'state':'partial',
              'sort':parsed.selected_sort or 'unconfirmed', 'requested_sort':args.sort, 'result_rows_on_page':len(rows),
              'candidates':selected, 'other_regions_ignored':len(rows)-len(selected),
              'note':'이 페이지에서 발견한 후보만 포함. 검색 전체 완료나 접수 상태 검증을 의미하지 않음.'}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'source_url':url,'result_rows_on_page':len(rows),'region_candidates':len(selected),'state':'partial'},ensure_ascii=False))


if __name__ == '__main__':
    main()

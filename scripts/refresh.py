#!/usr/bin/env python3
"""Conservative direct collection of public Saramin *search result* pages.

Checks robots.txt every run; no bypass of CAPTCHA/403/login, no personal data,
no detail-page scraping. A listing in a search result is not proof of open status.
"""
import datetime as dt
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
JOBS = ROOT / "data/jobs.json"
META = ROOT / "data/meta.json"
TZ = dt.timezone(dt.timedelta(hours=9))
BASE = "https://www.saramin.co.kr"
SEARCH = BASE + "/zf_user/search/recruit"
ROBOTS = BASE + "/robots.txt"
AGENT = "GYULJobRadar/1.0"
# Wide discovery, not a claim to cover all Saramin postings.
KEYWORDS = (
    "시각디자인", "그래픽디자인", "패키지디자인", "편집디자인",
    "웹디자인", "콘텐츠디자인", "브랜드디자인", "SNS마케팅",
    "콘텐츠마케팅", "마케팅기획", "상품기획", "온라인MD",
    "GTQ", "Illustrator", "Photoshop",
)
MAX_PAGES = int(os.getenv("SARAMIN_MAX_PAGES", "4"))
DELAY = float(os.getenv("SARAMIN_DELAY", "3.0"))
MAX_REQUESTS = int(os.getenv("SARAMIN_MAX_REQUESTS", "60"))
MAX_JOBS = 1500
BUSAN = re.compile(r"부산(?:광역시)?\s*(?:[가-힣]+(?:구|군)|전체)?")
REC_IDX = re.compile(r"(?:\?|&)rec_idx=(\d{5,16})(?:&|$)")
CATEGORIES = ("디자인", "마케팅·기획", "MD·상품기획")


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def text(node):
    return clean(node.get_text(" ", strip=True)) if node else ""


def safe_link(href):
    if not href:
        return None
    absolute = urllib.parse.urljoin(BASE, href)
    p = urllib.parse.urlsplit(absolute)
    if p.scheme != "https" or p.hostname not in (
        "www.saramin.co.kr", "saramin.co.kr", "www2.saramin.co.kr"
    ):
        return None
    q = urllib.parse.parse_qs(p.query)
    rec = q.get("rec_idx", [""])[0]
    if not re.fullmatch(r"\d{5,16}", rec):
        return None
    return rec, f"{BASE}/zf_user/jobs/relay/view?rec_idx={rec}"


def robots_permission():
    # Fail closed: if robots instructions cannot be fetched, do not crawl.
    request = urllib.request.Request(ROBOTS, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=18) as response:
        if response.status != 200:
            raise RuntimeError(f"robots.txt HTTP {response.status}")
        raw = response.read(250000).decode("utf-8", "replace")
    if not raw or "user-agent:" not in raw.lower():
        raise RuntimeError("robots.txt unavailable or invalid")
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(raw.splitlines())
    example = search_url("시각디자인", 1)
    allowed = parser.can_fetch(AGENT, example)
    print(f"robots.txt fetched, search allowed={allowed}")
    return allowed


def search_url(word, page):
    params = {
        "searchType": "search",
        "searchword": word,
        "loc_mcd": "106000",
        "recruitPage": str(page),
        "recruitPageCount": "40",
        "recruitSort": "reg_dt",
        "search_done": "y",
        "panel_count": "y",
        "search_optional_item": "y",
    }
    return SEARCH + "?" + urllib.parse.urlencode(params)


def download(url):
    request = urllib.request.Request(
        url, headers={"User-Agent": AGENT, "Accept": "text/html,application/xhtml+xml"}
    )
    with urllib.request.urlopen(request, timeout=23) as response:
        if response.status != 200:
            raise RuntimeError(f"Search HTTP {response.status}")
        content_type = response.headers.get("Content-Type", "").lower()
        if "html" not in content_type:
            raise RuntimeError("Search response not HTML")
        body = response.read(2_500_000)
    html = body.decode("utf-8", errors="replace")
    if any(s in html.lower() for s in ("captcha", "access denied", "비정상적인 접근")):
        raise RuntimeError("Search access blocked or challenged")
    return html


def classify(title, sector):
    s = (title + " " + sector).lower()
    if any(w in s for w in (
        "웹디자", "시각디자", "그래픽", "편집디자", "패키지디자",
        "디자이너", "콘텐츠디자", "디자인", "포토샵", "illustrator"
    )):
        return "디자인"
    if any(w in s for w in ("상품기획", "md", "머천다이저", "상품관리")):
        return "MD·상품기획"
    return "마케팅·기획"


def parse_cards(html, keyword, date):
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    candidates = soup.select(".item_recruit, .list_item, .recruit_item, .recruit_info")
    if not candidates:
        # Fallback targets card containers only; never entire page headings.
        for anchor in soup.select('a[href*="rec_idx="]'):
            parent = anchor.find_parent(
                lambda tag: tag.name in ("article", "li")
                or (tag.name == "div" and bool(re.search(r"item_recruit|list_item|recruit_item", " ".join(tag.get("class", [])))))
            )
            if parent:
                candidates.append(parent)
    for card in candidates:
        title_anchor = card.select_one(
            '.job_tit a[href*="rec_idx="], .job_title a[href*="rec_idx="],'
            ' a[href*="/jobs/relay/view"][href*="rec_idx="],'
            ' a[href*="/jobs/view"][href*="rec_idx="], a[href*="/recruit/"][href*="rec_idx="]'
        )
        if not title_anchor:
            title_anchor = card.select_one('a[href*="rec_idx="]')
        if not title_anchor:
            continue
        link = safe_link(title_anchor.get("href"))
        if not link:
            continue
        rid, url = link
        title = text(title_anchor)
        if len(title) < 4:
            title = text(card.select_one(".job_tit, .job_title"))
        if len(title) < 4:
            continue
        company = text(card.select_one(".corp_name a, .corp_name, .company_nm, .company_name"))
        if not company:
            company = "기업명 원문 확인"
        job_condition = text(card.select_one(".job_condition, .recruit_condition, .job_info"))
        sector = text(card.select_one(".job_sector, .recruit_sector"))
        blob = job_condition + " " + text(card.select_one(".job_date, .recruit_date"))
        area = BUSAN.search(job_condition)
        if not area:
            area = BUSAN.search(text(card.select_one(".job_condition .loc, .job_condition .area, .area")))
        if not area:
            # If no exact area is present, retain as unverified. Reject explicit non-Busan-only cards.
            places = re.findall(r"(?:서울|경기|인천|대구|울산|경남|경북|전남|전북|광주|대전|세종|제주)\s*[가-힣]*(?:구|군|시)?", job_condition)
            if places and not BUSAN.search(job_condition):
                continue
        location = ("부산 " + clean(area.group(0).replace("부산광역시", "").replace("부산", ""))) if area else "부산 검색 결과 · 근무지 확인"
        location = clean(location)
        deadline_raw = text(card.select_one(".job_date .date, .job_date, .recruit_date"))
        deadline = None
        match = re.search(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", deadline_raw)
        if match:
            try:
                deadline = dt.date(*map(int, match.groups())).isoformat()
            except ValueError:
                pass
        # Month/day without an explicit year is deliberately not turned into an ISO deadline.
        experience = "원문 확인"
        e = re.search(r"(신입\/경력|신입·경력|경력무관|신입|경력\s*\d+(?:년|개월)(?:\s*이상)?)", job_condition)
        if e:
            experience = clean(e.group(0))
        salary = "원문 확인"
        s = re.search(r"(?:연봉|월급|급여)\s*[\d,.~\-]+\s*(?:만원|원|만)", job_condition)
        if s:
            salary = s.group(0)
        out[rid] = {
            "id": rid,
            "company": company[:110],
            "title": title[:150],
            "location": location,
            "salary": salary,
            "benefits": "검색 목록에 정보 없음 · 원문 확인",
            "considerations": "검색 목록 정보입니다. 실제 근무지·연봉·복지·접수 여부를 원문에서 확인하세요.",
            "experience": experience,
            "status": "재확인 필요",
            "deadline": deadline,
            "deadline_text": deadline_raw[:50] or "확인 필요",
            "url": url,
            "source": "사람인",
            "category": classify(title, sector),
            "score": 70 if "신입" in experience or experience == "경력무관" else 55,
            "origin": "사람인 검색 페이지",
            "first_seen": date,
            "last_seen": date,
            "matched_keywords": [keyword],
        }
    return out


def update():
    now = dt.datetime.now(TZ)
    stamp = now.isoformat(timespec="seconds")
    today = now.date().isoformat()
    meta = json.loads(META.read_text("utf-8"))
    previous = json.loads(JOBS.read_text("utf-8"))
    state = {"mode": "direct_error", "last_attempt": stamp, "source": "사람인 검색 결과 직접 수집"}

    try:
        if not robots_permission():
            raise PermissionError("robots.txt disallows automated search-page collection")
        records = {}
        requests_made, failed, successful_pages = 0, 0, 0
        stop = False
        for word in KEYWORDS:
            for page in range(1, MAX_PAGES + 1):
                if requests_made >= MAX_REQUESTS or stop:
                    break
                url = search_url(word, page)
                # Use the same search URL shape as robots permission check.
                try:
                    time.sleep(DELAY)
                    html = download(url)
                    items = parse_cards(html, word, today)
                except urllib.error.HTTPError as e:
                    if e.code in (401, 403, 429):
                        stop = True
                        state["last_error"] = f"Search HTTP {e.code}; stopped"
                    failed += 1
                    print(f"{word} page {page}: HTTP {e.code}")
                    break
                except Exception as e:
                    failed += 1
                    print(f"{word} page {page}: {type(e).__name__}: {str(e)[:85]}")
                    if "blocked" in str(e).lower():
                        stop = True
                    break
                requests_made += 1
                print(f"{word} page {page}: {len(items)} cards")
                if not items:
                    break
                successful_pages += 1
                for key, record in items.items():
                    if key in records:
                        records[key]["matched_keywords"] = sorted(set(records[key]["matched_keywords"] + record["matched_keywords"]))
                    else:
                        records[key] = record
            if stop or requests_made >= MAX_REQUESTS:
                break

        if not records:
            raise RuntimeError(state.get("last_error") or "No search result cards parsed; existing data retained")
        existing = {str(x["id"]): x for x in previous}
        added = 0
        for key, record in records.items():
            if key in existing:
                old = existing[key]
                first_seen = old.get("first_seen") or today
                old.update(record)
                old["first_seen"] = first_seen
                # Preserve user-relevant curated notes if already present.
                if old.get("origin") == "초기 조사":
                    old["considerations"] = "초기 조사·검색목록 정보입니다. 접수 여부 및 상세 조건을 원문에서 확인하세요."
            else:
                existing[key] = record
                added += 1
        result = list(existing.values())
        result.sort(key=lambda j: (j.get("status") == "마감" or bool(j.get("deadline") and j["deadline"] < today),
                                   -int(j.get("score") or 0),
                                   j.get("last_seen", "")), reverse=False)
        # Keep the newest records; old items are never falsely marked closed by absence.
        if len(result) > MAX_JOBS:
            result = result[:MAX_JOBS]
        JOBS.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf-8")
        state.update(mode="direct", last_success=stamp, last_error=None,
                     found_count=len(records), new_count=added,
                     pages_checked=successful_pages, requests_made=requests_made,
                     search_errors=failed)
        print(f"Direct pages: {successful_pages}; unique cards: {len(records)}; new: {added}; errors: {failed}")
    except Exception as e:
        state.update(mode="direct_error", last_error=str(e)[:150])
        print(f"Direct search not available: {type(e).__name__}: {e}", file=sys.stderr)
    meta.update(state)
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", "utf-8")


if __name__ == "__main__":
    update()

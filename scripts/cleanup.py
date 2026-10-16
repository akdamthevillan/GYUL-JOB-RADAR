#!/usr/bin/env python3
"""Maintain curated public job records. Does not access Saramin or other sites."""
import datetime as dt
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "data" / "jobs.json"
META = ROOT / "data" / "meta.json"
TODAY = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date().isoformat()
CLOSED = {"closed", "expired", "마감", "접수마감", "채용마감", "지원마감"}


def normalized(value):
    return re.sub(r"[\s()\[\]_\-.]+", "", str(value or "").casefold())


def key(job):
    url = str(job.get("url") or "")
    rec = re.search(r"(?:[?&])rec_idx=(\d{5,16})(?:&|$)", url)
    if rec:
        return "saramin:" + rec.group(1)
    return "fallback:" + "|".join(normalized(job.get(k)) for k in ("company", "title", "location"))


def closed(job):
    state = str(job.get("status") or "").strip().casefold()
    if state in CLOSED:
        return True
    deadline = str(job.get("deadline") or "")
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", deadline) and deadline < TODAY)


def usable(job):
    if not isinstance(job, dict) or not job.get("company") or not job.get("title"):
        return False
    url = str(job.get("url") or "")
    return url.startswith(("https://www.saramin.co.kr/", "https://saramin.co.kr/", "https://www2.saramin.co.kr/"))


def quality(job):
    fields = ("company", "title", "location", "salary", "benefits", "considerations", "experience", "deadline", "verified_at")
    return sum(1 for f in fields if job.get(f) and not any(x in str(job[f]) for x in ("원문 확인", "확인 필요", "미공개")))


def run():
    rows = json.loads(FILE.read_text(encoding="utf8"))
    if not isinstance(rows, list):
        raise RuntimeError("jobs.json must contain a list")
    seen = {}
    removed = invalid = duplicate = 0
    for job in rows:
        if not usable(job):
            invalid += 1
            continue
        if closed(job):
            removed += 1
            continue
        k = key(job)
        previous = seen.get(k)
        if previous is None:
            seen[k] = job
        else:
            duplicate += 1
            if quality(job) > quality(previous):
                seen[k] = job
    result = list(seen.values())
    if result != rows:
        FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    meta = json.loads(META.read_text(encoding="utf8"))
    meta["last_maintenance_date"] = TODAY
    meta["total"] = len(result)
    meta["last_maintenance"] = {
        "expired_or_closed_removed": removed,
        "invalid_removed": invalid,
        "duplicates_removed": duplicate,
    }
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(f"cleaned {len(rows)} -> {len(result)}; closed={removed} invalid={invalid} duplicates={duplicate}")


if __name__ == "__main__":
    run()

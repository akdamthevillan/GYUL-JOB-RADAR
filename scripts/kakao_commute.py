#!/usr/bin/env python3
"""Optional Kakao Maps public-transit enrichment for GYUL JOB RADAR.
Reads KAKAO_REST_API_KEY from GitHub Actions Secrets, never from public files.
No Saramin automated requests. Records only verified Kakao API responses.
"""
import datetime as dt
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/"data/jobs.json"
API="https://dapi.kakao.com"
KEY=os.getenv("KAKAO_REST_API_KEY","").strip()
TZ=dt.timezone(dt.timedelta(hours=9))
MAX_JOBS=min(150,int(os.getenv("KAKAO_MAX_JOBS","80")))

def kakao_get(path,params):
    url=API+path+"?"+urllib.parse.urlencode(params)
    request=urllib.request.Request(url,headers={
        "Authorization":"KakaoAK "+KEY,"Accept":"application/json",
        "User-Agent":"GYUL-JOB-RADAR/1.0"})
    with urllib.request.urlopen(request,timeout=20) as response:
        return json.loads(response.read(700000).decode("utf-8"))

def geocode_address(address):
    # Preserve the street number. Omit building floor/room when present.
    import re
    query=re.split(r"\s+(?:\d+층|\d+호|[ABC]동|[가-힣]+빌딩|[가-힣]+타워)",address)[0]
    data=kakao_get("/v2/local/search/address.json",{"query":query})
    docs=data.get("documents") or []
    for p in docs:
        addr=p.get("road_address") or p.get("address") or p
        if addr and p.get("x") and p.get("y"):
            return {"lat":float(p["y"]),"lng":float(p["x"])}
    return None

def geocode_origin():
    data=kakao_get("/v2/local/search/keyword.json",{"query":"부산 냉정역 2호선","size":15})
    for p in data.get("documents",[]):
        if "냉정역" in p.get("place_name","") and "부산" in p.get("address_name",""):
            return {"lat":float(p["y"]),"lng":float(p["x"])}
    return None

def safe_landing(url):
    try:
        p=urllib.parse.urlsplit(url)
        if p.scheme=="https" and p.hostname in ("map.kakao.com","m.map.kakao.com"):
            return url
    except (TypeError,ValueError):
        pass
    return None

def run():
    if not KEY:
        print("KAKAO_REST_API_KEY not configured; no commute durations written.")
        return
    jobs=json.loads(PATH.read_text(encoding="utf-8"))
    if not jobs:
        print("No jobs")
        return
    origin=geocode_origin()
    if not origin:
        print("Could not confirm Naengjeong Station coordinates. No changes.")
        return
    changed=0
    now=dt.datetime.now(TZ).strftime("%Y-%m-%d %H:%M KST")
    for j in jobs[:MAX_JOBS]:
        address=str(j.get("location") or "").strip()
        if not address or any(s in address for s in ("미공개","확인 필요","주소 없음")):
            continue
        try:
            point=j.get("coordinates")
            if not point or j.get("coordinates_source_address")!=address:
                point=geocode_address(address)
            if not point:
                print("Unmatched workplace address; skipped",j.get("id",""))
                continue
            route=kakao_get("/v2/routing/publictraffic",{
                "start_x":origin["lng"],"start_y":origin["lat"],"s_name":"냉정역",
                "end_x":point["lng"],"end_y":point["lat"],
                "e_name":str(j.get("company") or "목적지"),
                "input_coord":"WGS84"})
            if route.get("status")!="OK":
                continue
            seconds=[r.get("properties",{}).get("totalTime") for r in route.get("routes",[])]
            seconds=[float(x) for x in seconds if isinstance(x,(int,float)) and x>0]
            if not seconds:
                continue
            j["coordinates"]=point
            j["coordinates_source_address"]=address
            j["origin_coordinates"]=origin
            j["transit_minutes"]=math.ceil(min(seconds)/60)
            j["transit_checked_at"]=now
            j["transit_provider"]="카카오맵 대중교통 경로 조회 API"
            landing=safe_landing((route.get("properties") or {}).get("landingURL",""))
            if landing:
                j["transit_route_url"]=landing
            else:
                j.pop("transit_route_url",None)
            changed+=1
            time.sleep(0.2)
        except (ValueError,KeyError,urllib.error.URLError,TimeoutError) as e:
            print("Skipped",j.get("id",""),type(e).__name__)
    if changed:
        PATH.write_text(json.dumps(jobs,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Updated commute routes:",changed)

if __name__=="__main__":
    run()

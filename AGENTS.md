# GYUL JOB RADAR — AI 에이전트 실행 지침

이 파일은 이 저장소에 연결된 AI 에이전트(웹 ChatGPT의 GitHub 연결, Codex 등)를 위한 **실행 절차서**입니다.
사용자가 아래 요청 중 하나를 하면 확인 질문 없이 바로 **새로고침 절차** 전체를 실행하고, 끝나면 결과를 한국어로 보고합니다.

> GitHub Actions(`scripts/auto_sync.py`)가 2시간마다 사람인 직종 목록과 등록 공고를 자동 점검합니다. 에이전트의 새로고침은 이를 **보완**합니다: 자동 점검에서 `last_check_result`가 `unknown`이거나 `last_checked_at`이 오래된 공고, 그리고 자동 점검 직종(디자인, 마케팅·홍보·조사, 상품기획·MD, 기획·전략) 밖의 키워드 검색을 우선합니다.

> 트리거 예: `새로고침`, `새로고침 해줘`, `갱신`, `업데이트`, `점검`, `리프레시`, `새 공고 찾아줘`, `귤레이더 돌려줘`

저장소: `akdamthevillan/GYUL-JOB-RADAR` · 사이트: https://akdamthevillan.github.io/GYUL-JOB-RADAR/

## 0. 꼭 지킬 원칙

- **데이터 파일(`data/*.json`)을 직접 커밋하지 않습니다.** 모든 변경은 `[GYUL-IMPORT]` Issue로 보냅니다. GitHub Actions가 검증하고 반영하며, 사이트 배포까지 자동으로 합니다.
- **실제로 보지 않은 것은 쓰지 않습니다.** 검색 결과 문구, 기억, 추측으로 `verified_open`이나 마감을 판정하지 않습니다. 확인하지 못하면 `unknown`/`재확인 필요`로 남깁니다.
- 사람인 접근제한 우회, 로그인 우회, 대량 자동 크롤링, 실제 입사지원 클릭·제출은 하지 않습니다. 차단되면 차단됐다고 기록합니다.
- Issue는 공개됩니다. 개인 연락처, 이력서, 로그인 화면, 스크린샷 원본을 올리지 않습니다.
- 날짜는 모두 **한국시간(KST)** 기준입니다. `YYYY-MM-DD`, 시각은 `2026-10-21T14:05:00+09:00` 형식입니다.

## 1. 현재 상태 읽기

다음 파일을 읽습니다(GitHub 연결 또는 raw URL `https://raw.githubusercontent.com/akdamthevillan/GYUL-JOB-RADAR/main/<경로>`).

| 파일 | 용도 |
| --- | --- |
| `data/jobs.json` | 현재 등록 공고. `id` = 사람인 `rec_idx` |
| `data/closed-postings.json` | 마감 이력. 여기 있는 `id`는 **절대 다시 등록하지 않음** |
| `data/search-config.json` | `search_strategy`(지역·키워드), `advisor_profile`(귤의 직무 기준) |
| `data/research-report.json` | 직전 조사 범위. 이번 조사에서 이어서 할 곳 판단 |

## 2. 기존 공고 재점검

한 번에 모든 공고를 볼 수 없으므로 아래 우선순위로 **15~30건**을 점검합니다(가능하면 더).

1. `last_check_result`가 `unknown`이거나, `verified_at`이 어제보다 오래된 공고
2. `deadline`이 오늘부터 7일 이내인 공고
3. `status`가 `recently_listed`인 공고
4. 나머지 중 `source_checked_at`(없으면 `first_seen`)이 가장 오래된 공고

공고 상세는 `https://www.saramin.co.kr/zf_user/jobs/view?rec_idx=<id>`(정적 HTML, 권장) 또는 `https://m.saramin.co.kr/job-search/view?rec_idx=<id>`로 엽니다. 열린 페이지의 공고번호가 같은지 확인합니다.

### 판정 기준

| 페이지에서 실제로 본 것 | 결과 |
| --- | --- |
| 같은 공고번호의 **입사지원** / **사람인 입사지원** 버튼이 보이고 비활성(`disabled`, `aria-disabled="true"`)이 아님. HTML에서는 `sri_btn_immediately` 또는 `for_btn_event` 클래스, `quickApply…('<id>')` | `apply_enabled` → 모집 중 |
| **본 채용정보는 마감되었습니다**, **접수마감** 버튼, `sri_btn_expired_apply` 클래스 | `closed` → 마감 |
| 홈페이지·이메일·전화 지원만 있음 | `external_apply` → 마감으로 보지 않음. 지원 방법을 기록 |
| 접속 실패·차단·로그인 필요·버튼을 찾지 못함 | `unknown` → 아무것도 바꾸지 않고 관찰만 기록 |

- 마감 HTML에도 `quickApplyMobile(...)` 문자열이 남아 있습니다. **onclick 문자열만으로 모집 중이라고 판단하지 않습니다.**
- 확인 방식(`method`): HTML 원문·DOM을 읽었으면 `page_dom`, 렌더링된 화면을 봤으면 `browser_visual`, 사용자가 준 스크린샷이면 `user_screenshot`입니다.

## 3. 신규 공고 찾기

`search_strategy.regions` × 키워드 조합을 등록일순 첫 페이지부터 검색합니다. 시간이 부족하면 `primary_keywords`(마케팅, 마켓팅, MD, 디자인, 기획, 일러스트, 포토샵)를 먼저 합니다. 직전 `research-report.json`에서 이미 조사한 조합은 뒤로 미룹니다.

검색 URL(`{키워드}`는 URL 인코딩):

| 지역 | URL |
| --- | --- |
| 부산광역시 전체 | `https://www.saramin.co.kr/zf_user/search?searchword={키워드}&loc_mcd=106000&recruitPage=1&recruitSort=reg_dt` |
| 경남 김해시 | `https://www.saramin.co.kr/zf_user/search?searchword={키워드}&loc_cd=110040&recruitPage=1&recruitSort=reg_dt` |
| 경남 양산시 | `https://www.saramin.co.kr/zf_user/search?searchword={키워드}&loc_cd=110100&recruitPage=1&recruitSort=reg_dt` |

후보를 거르는 기준:

- `rec_idx`가 `jobs.json`이나 `closed-postings.json`에 이미 있으면 신규가 아닙니다.
- 검색 결과에는 광고·추천으로 다른 지역 공고가 섞입니다. 근무지가 부산·김해·양산인지 확인합니다.
- 디자인·브랜딩·마케팅·SNS·콘텐츠·기획·온라인 MD와 관련된 공고만 받습니다. **회사명·업종·요구 경력연수만으로는 제외하지 않습니다.**
- 후보마다 **개별 상세 페이지를 열어** 2장 기준으로 판정합니다. 이미 마감된 신규 후보는 등록하지 않습니다(closed_postings에도 넣지 않아도 됨).
- 상세에서 실제로 확인한 값만 채웁니다: 근무지 주소(`location`), 급여(`salary`), 경력(`experience`), 고용형태(`employment`), 마감일(`deadline` 또는 `deadline_text`), 근무시간(`work_schedule`), 지원 방법(`application_method`), 담당업무·요건(`duties`), 복지(`benefits`), 업종(`company_business`).
- `category`는 다음 중 하나로 정합니다: `디자인`, `마케팅·기획`, `콘텐츠·SNS`, `브랜드·상품기획`, `온라인·디지털 운영`.

## 4. Issue 본문(JSON) 만들기

하나의 JSON 객체를 만듭니다. 최상위 키는 `jobs`, `closed_postings`, `observations`, `research_report`만 쓸 수 있습니다.

```json
{
  "jobs": [
    {
      "id": "55113455",
      "url": "https://www.saramin.co.kr/zf_user/jobs/view?rec_idx=55113455",
      "company": "(주)예시",
      "title": "브랜드 디자이너",
      "category": "디자인",
      "location": "부산 금정구 금강로 000",
      "salary": "면접 후 결정",
      "experience": "신입·경력",
      "employment": "정규직",
      "deadline": "2026-10-31",
      "application_method": "사람인 입사지원",
      "source_checked_at": "2026-10-21",
      "status": "verified_open",
      "verified_at": "2026-10-21",
      "verified_source_url": "https://www.saramin.co.kr/zf_user/jobs/view?rec_idx=55113455",
      "verification_evidence": "공고번호 일치 '입사지원' 버튼(class sri_btn_immediately), disabled 아님, 마감 안내 없음",
      "application_button_state": "apply_enabled",
      "application_evidence_kind": "page_dom",
      "application_checked_at": "2026-10-21"
    }
  ],
  "closed_postings": [
    {
      "id": "55162762",
      "reason": "접수마감 확인: 공고번호 일치 지원 컨트롤이 '접수마감'으로 표시됨",
      "closed_confirmed": "2026-10-21",
      "evidence_url": "https://www.saramin.co.kr/zf_user/jobs/view?rec_idx=55162762",
      "application_button_state": "closed",
      "application_evidence_kind": "page_dom",
      "application_checked_at": "2026-10-21"
    }
  ],
  "observations": [
    {
      "id": "55113455",
      "source_url": "https://www.saramin.co.kr/zf_user/jobs/view?rec_idx=55113455",
      "observed_at": "2026-10-21T14:05:00+09:00",
      "result": "apply_enabled",
      "method": "page_dom",
      "evidence": "공고번호 일치 '입사지원' 버튼 활성"
    }
  ],
  "research_report": {
    "last_run_at": "2026-10-21T14:30:00+09:00",
    "state": "partial",
    "existing_postings_checked": 20,
    "new_candidates_checked": 6,
    "observations": {"apply_enabled": 15, "closed": 3, "unknown": 8},
    "searches": [
      {"region": "부산광역시 전체", "keyword": "디자인", "page": 1, "state": "partial",
       "source_url": "https://www.saramin.co.kr/zf_user/search?searchword=%EB%94%94%EC%9E%90%EC%9D%B8&loc_mcd=106000&recruitPage=1&recruitSort=reg_dt",
       "result_rows_on_page": 40, "observed_at": "2026-10-21T14:10:00+09:00"}
    ],
    "note": "기존 20건 재점검, 부산·김해·양산 디자인/마케팅 첫 페이지 조사. 나머지 키워드는 미조사."
  }
}
```

위 값은 형식 예시입니다. 실제 공고 데이터가 아닙니다.

### 경우별 작성법

- **모집 중 확인(신규·기존 공통):** `jobs`에 위 예시처럼 버튼 근거 필드 7개(`status`, `verified_at`, `verified_source_url`, `verification_evidence`, `application_button_state`, `application_evidence_kind`, `application_checked_at`)를 모두 오늘 날짜로 넣고, `observations`에도 한 줄 추가합니다. 근거 필드가 하나라도 빠지면 자동으로 `재확인 필요`로 낮춰집니다.
- **마감 확인:** `closed_postings`에 넣습니다. `reason`에는 `접수마감`, `채용마감`, `지원마감` 중 하나가 반드시 들어가야 합니다. `closed_confirmed`와 `application_checked_at`은 같은 날짜입니다. `observations`에도 `result: "closed"`로 추가합니다.
- **확인 불가 / 외부 지원:** `jobs`에는 넣지 않고 `observations`에만 `unknown` 또는 `external_apply`로 기록합니다.
- **신규인데 버튼 확인 불가:** `jobs`에 `"status": "재확인 필요"`로 넣을 수 있습니다(버튼 근거 필드는 빼고).
- **근무지 좌표(선택):** 상세 HTML의 `jv_location` 요소에 `data-latitude`, `data-longitude`가 있으면 `"workplace_coordinates": {"lat": …, "lng": …, "precision": "posting_map", "source_url": "<공고 URL>", "checked_at": "<오늘>"}`로 넣습니다.
- **`research_report`:** 매 새로고침마다 넣습니다. 대시보드의 "최근 조사 범위와 결과"에 표시됩니다. `state`는 `partial`, `completed`, `blocked` 중 하나입니다. 신규 추가·마감 제외 건수는 Actions가 실제 반영 결과로 채우므로 쓰지 않아도 됩니다.

### 반려되는 경우 (하나라도 틀리면 Issue 전체가 반영되지 않음)

- `id`가 숫자 5~16자리가 아니거나, `url`의 `rec_idx`와 다름
- `jobs`에 **마감일(`deadline`)이 오늘보다 이전**인 공고가 있음(오늘 버튼으로 모집 중을 확인한 경우는 예외)
- `jobs`에 `application_button_state: "closed"`가 있음(마감은 `closed_postings`로)
- 날짜 형식 오류, 미래 시각, 시간대 없는 `observed_at`
- 값이 객체·배열인 필드(`company_info`, `workplace_coordinates`, `commute` 제외), 4000자 초과 문자열
- 한 Issue에 `jobs` 40건, `closed_postings` 40건, `observations` 80건 초과. 많으면 Issue를 나눕니다.

## 5. Issue 생성

- 제목: `[GYUL-IMPORT] 2026-10-21 14:30 새로고침` (반드시 `[GYUL-IMPORT]`로 시작)
- 본문: 짧은 요약 몇 줄 + 아래처럼 ```json 코드 블록 하나

````markdown
귤레이더 새로고침: 기존 20건 점검, 신규 3건, 마감 2건

```json
{ ... 4장의 JSON ... }
```
````

- **저장소 소유자(`akdamthevillan`) 계정으로 생성된 Issue만 처리됩니다.** GitHub 연결이 사용자 계정으로 Issue를 만들 수 있으면 직접 생성합니다.
- 직접 만들 수 없으면 사용자에게 다음 중 하나를 줍니다.
  1. 제목과 본문을 채운 링크: `https://github.com/akdamthevillan/GYUL-JOB-RADAR/issues/new?title=<URL 인코딩 제목>&body=<URL 인코딩 본문>`. 사용자는 열어서 **Submit**만 누르면 됩니다. 링크가 약 7000자를 넘으면 쓰지 말고 2번을 씁니다.
  2. 제목과 본문을 복사용 코드 블록으로 주고, 위 저장소의 **New issue**에 붙여 넣도록 안내합니다.

## 6. 반영 확인

- Issue가 만들어지면 Actions(`GYUL data intake and maintenance`)가 바로 실행됩니다. 2시간마다 정기 실행도 합니다.
- **정상 반영:** 몇 분 안에 Issue가 자동으로 닫히고, 이어서 사이트가 다시 배포됩니다.
- **반려:** Issue가 열린 채로 남고 `자동 반영 보류` 댓글에 사유가 달립니다. 사유를 고쳐 **Issue 본문을 수정**하면 다시 검사합니다. 새 Issue를 또 만들지 않습니다.
- 확인할 수 없으면 "Issue를 만들었고 Actions 반영을 기다리는 중"이라고 보고합니다. 반영됐다고 단정하지 않습니다.

## 7. 사용자에게 보고하는 형식

```
귤레이더 새로고침 결과 (YYYY-MM-DD HH:MM KST)
- 기존 공고 점검: N건 (모집 중 a · 마감 b · 확인 불가 c)
- 신규 공고: N건 추가 — 회사 / 제목 (목록)
- 조사 범위: 지역 × 키워드 (첫 페이지만 등) / 못 한 범위
- 반영: Issue #번호 생성 → 자동 반영 대기 | 반영 완료 | 반려 사유
```

검색한 범위와 실제로 열어 본 공고 수를 구분해 적습니다. 전체 검색을 끝내지 않았다면 끝냈다고 쓰지 않습니다.

## 8. Codex 등 셸이 있는 에이전트

셸과 네트워크를 쓸 수 있으면 아래 도구로 같은 절차를 더 정확히 할 수 있습니다. 반영 경로는 그래도 Issue입니다.

```sh
python scripts/inspect_html.py 'https://www.saramin.co.kr/zf_user/jobs/view?rec_idx=<id>'          # 공고 1건 버튼 판정 + 상세 필드
python scripts/discover_candidates.py --region '부산광역시 전체' --keyword 디자인 --output /tmp/c.json  # 검색 1페이지
python scripts/review_batch.py /tmp/batch.json                                                    # Issue 본문 사전 검증(변경 없음)
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
```

코드를 고칠 때는 `assets/radar.js`와 `scripts/status_rules.py`의 상태 판정을 함께 맞추고, `tests/fixtures/status-cases.json` 테스트를 통과시킵니다. 세부 정책은 `docs/personal-advisor.md`와 `docs/mobile-saramin-search-and-verification.md`를 참고합니다.

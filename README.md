# GYUL JOB RADAR

[사이트](https://akdamthevillan.github.io/GYUL-JOB-RADAR/) · [저장소](https://github.com/akdamthevillan/GYUL-JOB-RADAR)

부산 전체·김해·양산의 사람인 디자인·브랜딩·마케팅·SNS·콘텐츠·기획·온라인 MD 관련 채용공고를 하나의 목록으로 보여주는 개인용 대시보드입니다.

> **AI 에이전트(ChatGPT·Codex 등):** 사용자가 `새로고침`, `갱신`, `점검`을 요청하면 [AGENTS.md](AGENTS.md)의 절차를 그대로 실행하세요.

## 안전한 하이브리드 운영

- **자동 점검(GitHub Actions)**: `scripts/auto_sync.py`가 부산 전체·김해·양산의 사람인 직종 목록(디자인, 마케팅·홍보·조사, 상품기획·MD, 기획·전략)을 최신순으로 읽습니다. 목록의 각 공고 행에 있는 같은 공고번호의 입사지원·홈페이지 지원 버튼으로 접수 상태를 확인하고, 개별 공고 페이지는 처음 발견한 공고(상세 정보 수집), 목록에서 사라진 공고(마감 확인), 7일이 지난 공고(상세 갱신)만 엽니다. 기업정보 페이지는 회사당 30일에 한 번 읽습니다. 공고 제목·직무 태그로 분류해 귤 직무(`advisor_profile.focus_categories`: 디자인, 콘텐츠·SNS, 브랜드·상품기획, 온라인·디지털 운영, 마케팅·기획)만 저장하며, 콜센터·영업·판매·매장·알바·사무·개발·인테리어 시공·영상·애니메이션·3D 등 다른 직무는 추가하지 않고 이미 저장된 자동 수집분은 삭제합니다. 요청 간격 1.5초, 로그인·지원 클릭 없음. 접속 실패는 아무것도 바꾸지 않고 다음 실행에서 다시 확인합니다. 설정은 `data/search-config.json > auto_sync`.
- **ChatGPT·수동 확인**: 자동 점검을 보완합니다. 검색 색인만으로 `verified_open`을 판정하지 않으며, 사람인 접근제한 우회는 하지 않습니다.
- **GitHub Issues**: 채용 후보 전달함입니다. 저장소 소유자(`akdamthevillan`)가 생성한 제목 `[GYUL-IMPORT]`로 시작하는 Issue만 처리합니다. Issues는 **공개**되므로 개인 연락처, 이력서, 포트폴리오, 비공개 메모 등을 절대로 넣지 마세요.
- **GitHub Actions**: 한국시간 00·02·04·06·08·10·12·14·16·18·20·22시(UTC 홀수 시간)에 실행을 요청하며, GitHub 일정상 지연될 수 있습니다. Issue 데이터 검증·등록, 사람인 자동 점검, 중복 정리, 기한 경과 공고 제거, 마감 공고번호 기록을 수행합니다. Issue로 시작된 실행은 빠른 반영을 위해 자동 점검을 건너뜁니다.
- **GitHub Pages**: `main` 데이터 커밋 시 사이트 배포. HTML의 기존 단일 목록 디자인 유지.

## 채용 후보 전달

저장소 소유자가 새 Issue를 만들고 제목을 `[GYUL-IMPORT] 2026-10-16`처럼 정합니다. 본문에는 JSON 객체 하나를 넣습니다. 아래는 **형식 예시**이며 실제 공고가 아닙니다.

```json
{
  "jobs": [
    {
      "id": "12345678",
      "company": "예시기업",
      "title": "콘텐츠 마케터",
      "url": "https://www.saramin.co.kr/zf_user/jobs/view?rec_idx=12345678",
      "location": "정확한 근무지 주소 미확인",
      "experience": "원문 확인",
      "salary": "미공개",
      "status": "재확인 필요"
    }
  ],
  "closed_postings": []
}
```

- 새 공고는 `id`와 URL의 `rec_idx`가 일치해야 합니다. 기업명·업종·경력연수로 자동 제외하지 않습니다.
- `verified_open`은 **오늘 또는 어제(한국시간) 실제 공고 페이지의 활성 지원 버튼을 관찰**한 경우에만 허용합니다. `verified_at`, `verified_source_url`, `verification_evidence`뿐 아니라 `application_button_state=apply_enabled`, `application_evidence_kind=page_dom|user_screenshot|browser_visual`, `application_checked_at=당일`을 함께 제출해야 합니다. 검색 색인 문구만으로는 `재확인 필요`로 낮춥니다.
- `recently_listed`는 최근 3일 이내 검색 근거(`listing_evidence`, `listing_checked_at`)와 미래/당일의 `deadline`이 있어야 하며, 이 역시 실시간 접수 확인을 의미하지 않습니다.
- 접수 마감 공고는 `closed_postings`에 `id`, `reason`, `closed_confirmed`, `evidence_url`와 더불어 `application_button_state=closed`, `application_evidence_kind`, `application_checked_at`(마감 확인 일자)을 반드시 제출합니다. 검색 색인만으로 확정 마감으로 판단하지 않습니다.
- 이미 기록된 마감 ID는 다시 등록하지 않습니다. 같은 회사의 다른 공고는 ID가 다르면 유지합니다.
- 재무·평균연봉·입퇴사 지표는 검증 가능한 별도 출처와 기준연도 없이 자동 생성하거나 변경하지 않습니다.
- Issues에 형식이 잘못된 데이터가 있으면 적용하지 않고 다음 실행을 위해 Issue를 열어 둡니다. 반려 사유는 Issue 댓글(`자동 반영 보류`)로 한 번 남기며, 본문을 수정하면 다시 검사합니다. 정상 처리한 Issue는 데이터 반영 완료 후 자동 종료합니다.
- 본문은 JSON만 넣거나, 요약 문장 뒤에 ```json 코드 블록 하나를 넣을 수 있습니다. 선택 필드 `research_report`는 대시보드의 최근 조사 범위(`data/research-report.json`)를 갱신하며, 신규·마감 건수는 실제 반영 결과로 기록합니다.

## 모바일 검색 및 상태 판정

지역별(부산 전체·김해·양산)로 `마케팅`, `마켓팅`, `MD`, `디자인`, `기획`, `일러스트`, `포토샵` 및 확장 키워드를 사람인 모바일 검색 화면에서 한 건씩 조사합니다. 공고번호별로 **실제 하단 버튼**을 확인하지 못하면 지원 가능으로 확정하지 않습니다. 구체적인 절차는 [모바일 사람인 검색·검증 규칙](docs/mobile-saramin-search-and-verification.md)을 참고하세요. GitHub Actions 자체가 사이트 화면을 탐색하거나 버튼을 확인하는 것은 아닙니다.

## 데이터 및 갱신 시각

- [jobs.json](data/jobs.json) · [search-config.json](data/search-config.json) · [closed-postings.json](data/closed-postings.json)
- `scripts/import_issues.py`: 소유자가 제출한 Issue만 받아 구조·사람인 ID·검증 근거를 확인합니다.
- `scripts/auto_sync.py`: 사람인 직종 목록과 개별 공고 페이지를 읽어 신규 공고 추가, 접수 상태 갱신, 마감 공고 이동을 합니다.
- `scripts/cleanup.py`: 명확히 마감됐거나 **마감일이 지난** 공고만 제거하고 마감 ID를 기록합니다. 사람인에 네트워크 접속하지 않습니다.
- `scripts/refresh_meta.py`: 실제 공고/마감 데이터가 바뀌는 경우에만 Actions가 호출합니다. `last_updated_at`은 한국시간 ISO 8601이며 **데이터 변경 커밋과 함께** 푸시할 때만 공개됩니다.
- 단순 점검, 실패, Issue 종료, UI 변경만으로 `last_updated_at`을 수정하지 않습니다. 코드 테스트는 `python -m unittest discover -s tests -v`입니다.
- 카드의 주소는 도로명·지번까지 확인된 경우 카카오맵 검색(`map.kakao.com/?q=주소`)으로 연결합니다. API 키, 카카오 REST 호출, 이동시간 계산은 사용하지 않습니다. 구 단위 등 불완전한 주소에는 링크를 만들지 않습니다.

**제약:** 자동 점검은 사람인 공개 페이지 구조에 의존합니다. 구조가 바뀌거나 GitHub Actions 접속이 차단되면 그 회차는 상태를 바꾸지 않고 건너뛰며, 2시간마다 다시 시도합니다. 공고 상세·기업정보는 회차당 `max_detail_checks`·`max_company_checks`로 제한되므로 처음에는 여러 회차에 걸쳐 채워지고, 그동안 카드에는 목록 정보와 '상세 정보 수집 중'이 표시됩니다. 사람인 이용약관상 자동 접근 허용 여부는 운영자가 판단해야 합니다.

## 귤 맞춤 추천 (개편)

기본 정렬은 **귤 당도순**(종합 추천 지수, 단위 브릭스, 직무 적합 55% 중심)입니다. 기본 목록에는 접수 버튼이 확인되고 당도 `advisor_profile.min_score`(75) 이상인 공고만 표시하며, 나머지는 목록 끝 버튼이나 검색으로 볼 수 있습니다. 유니폼·SNS 디자인 실무와 브랜딩·패키지·편집 포트폴리오를 기준으로 추천 이유를 표시합니다. 연봉 3,000만 원은 선호 조건이며 미만·미공개 공고도 남깁니다. 즐겨찾기·지원 기록·숨김 복구는 이 브라우저에 저장됩니다.

거리·대중교통·연봉·직원 수 정렬은 출처가 확인된 비교 가능 데이터만 사용합니다. 미확인 값은 뒤로 정렬합니다. 실제 공고의 활성 입사지원 버튼은 코드·DOM으로 확인할 수 있으며 스크린샷은 필수가 아닙니다. 상태 모델, 데이터 입력과 조사 기록, 테스트 절차는 [개인 취업 도우미 개발·운영 문서](docs/personal-advisor.md)를 참고하세요.

실제 조사 범위와 미완료 항목은 `data/research-report.json` 및 대시보드의 최근 조사 결과에서 구분해 표시합니다. 기존 자료 전체를 현재 지원 가능한 공고로 간주하지 않습니다.

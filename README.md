# GYUL JOB RADAR

[사이트](https://akdamthevillan.github.io/GYUL-JOB-RADAR/) · [저장소](https://github.com/akdamthevillan/GYUL-JOB-RADAR)

부산 전체·김해·양산의 사람인 디자인·브랜딩·마케팅·SNS·콘텐츠·기획·온라인 MD 관련 채용공고를 하나의 목록으로 보여주는 개인용 대시보드입니다.

> **AI 에이전트(ChatGPT·Codex 등):** 사용자가 `새로고침`, `갱신`, `점검`을 요청하면 [AGENTS.md](AGENTS.md)의 절차를 그대로 실행하세요.

## 안전한 하이브리드 운영

- **ChatGPT**: 허용된 공개 자료로 신규 사람인 공고 후보를 조사합니다. 검색 색인만으로 `verified_open`을 판정하지 않습니다. 사람인 접근제한 우회나 대량 크롤링은 하지 않습니다.
- **GitHub Issues**: 채용 후보 전달함입니다. 저장소 소유자(`akdamthevillan`)가 생성한 제목 `[GYUL-IMPORT]`로 시작하는 Issue만 처리합니다. Issues는 **공개**되므로 개인 연락처, 이력서, 포트폴리오, 비공개 메모 등을 절대로 넣지 마세요.
- **GitHub Actions**: 한국시간 00·02·04·06·08·10·12·14·16·18·20·22시(UTC 홀수 시간)에 실행을 요청하며, GitHub 일정상 지연될 수 있습니다. 새로운 채용공고를 직접 크롤링하지 않고, 보류 중인 Issue 데이터 검증, 등록, 중복 정리, 기한 경과 공고 제거, 마감 공고번호 기록만 수행합니다.
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
- `verified_open`은 **당일 모바일 하단의 활성 `입사지원` 버튼을 실제로 관찰**한 경우에만 허용합니다. `verified_at`, `verified_source_url`, `verification_evidence`뿐 아니라 `application_button_state=apply_enabled`, `application_evidence_kind=page_dom|user_screenshot|browser_visual`, `application_checked_at=당일`을 함께 제출해야 합니다. 검색 색인 문구만으로는 `재확인 필요`로 낮춥니다.
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
- `scripts/cleanup.py`: 명확히 마감됐거나 **마감일이 지난** 공고만 제거하고 마감 ID를 기록합니다. 사람인에 네트워크 접속하지 않습니다.
- `scripts/refresh_meta.py`: 실제 공고/마감 데이터가 바뀌는 경우에만 Actions가 호출합니다. `last_updated_at`은 한국시간 ISO 8601이며 **데이터 변경 커밋과 함께** 푸시할 때만 공개됩니다.
- 단순 점검, 실패, Issue 종료, UI 변경만으로 `last_updated_at`을 수정하지 않습니다. 코드 테스트는 `python -m unittest discover -s tests -v`입니다.
- 카카오맵 길찾기는 주소가 확인된 경우 **냉정역 출발 / 확인된 주소 도착**을 URL에 전달하는 링크입니다. API 키, 카카오 REST 호출, 이동시간 계산은 사용하지 않습니다. 주소가 불완전하면 정확하지 않다고 표시하고 링크를 만들지 않습니다. 주소 기반 URL은 모든 기기에서 출발지·도착지가 자동 인식된다고 보장할 수 없습니다.

**제약:** API 키 없이 사람인 전체 신규 채용공고를 GitHub Actions가 자동 수집할 수는 없습니다. ChatGPT의 예약 조사 및 GitHub Issue 생성 역시 해당 예약 환경의 외부 접근과 쓰기 권한에 영향을 받습니다. 이 저장소는 데이터 전달 후 검증·반영을 자동화한 구조이며, 신규 후보 발굴의 100% 성공을 보장하지 않습니다.

## 귤 맞춤 추천 (개편)

기본 정렬은 **종합 추천순**입니다. 유니폼·SNS 디자인 실무와 브랜딩·패키지·편집 포트폴리오를 기준으로 추천 이유를 표시합니다. 연봉 3,000만 원은 선호 조건이며 미만·미공개 공고도 남깁니다. 즐겨찾기·지원 기록·숨김 복구는 이 브라우저에 저장됩니다.

거리·대중교통·연봉·직원 수 정렬은 출처가 확인된 비교 가능 데이터만 사용합니다. 미확인 값은 뒤로 정렬합니다. 실제 공고의 활성 입사지원 버튼은 코드·DOM으로 확인할 수 있으며 스크린샷은 필수가 아닙니다. 상태 모델, 데이터 입력과 조사 기록, 테스트 절차는 [개인 취업 도우미 개발·운영 문서](docs/personal-advisor.md)를 참고하세요.

실제 조사 범위와 미완료 항목은 `data/research-report.json` 및 대시보드의 최근 조사 결과에서 구분해 표시합니다. 기존 자료 전체를 현재 지원 가능한 공고로 간주하지 않습니다.

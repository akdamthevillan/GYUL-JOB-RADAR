# 🍊 GYUL JOB RADAR

[웹사이트](https://akdamthevillan.github.io/GYUL-JOB-RADAR/) · [저장소](https://github.com/akdamthevillan/GYUL-JOB-RADAR)

부산 사람인 디자인·마케팅·기획 채용공고.

## 갱신 방식
- 00:00 / 12:00 (Asia/Seoul): ChatGPT 예약 작업에서 `data/search-config.json`의 키워드로 공개 공고를 검색·검토하여 **GitHub 연결 및 사용 가능한 권한이 있을 때** `data/jobs.json`을 갱신하도록 예약했습니다.
- 00:20 / 12:20: GitHub Actions가 마감일 경과·마감 확정·중복된 기존 공고를 제거합니다. 외부 사이트에 접근하지 않습니다.
- `main`의 데이터 또는 사이트 코드가 변경되면 GitHub Pages를 자동 재배포합니다.
- 예약 작업에서 검색 또는 GitHub 수정이 불가능할 경우 갱신은 보장되지 않습니다. 마지막 검토일과 작업 실행 기록을 확인하세요.
- 사람인 검색 페이지 자동 크롤링·접근 제한 우회는 사용하지 않습니다.

## 검색 기준
`data/search-config.json` 참조. 부산 전체, 사상구·부산진구 등 주례동 인접 지역 우선. 디자인·콘텐츠·SNS·브랜드기획·상품기획·소비재 업종·자격증 키워드 포함. 신입·경력무관 및 자체 브랜드 기업 우대.

## 카드에 표시할 데이터
`data/jobs.json`에 다음 필드를 기록합니다.
- 필수: `id`(사람인 공고번호), `company`, `title`, `location`, `url`, `category`
- 권장: `salary`, `benefits`, `considerations`, `experience`, `employment`, `deadline`(YYYY-MM-DD), `first_seen`, `last_seen`, `verified_at`(YYYY-MM-DD), `status`, `score`
- `status=verified_open`은 해당 회차에 접수 중임이 확인되었을 때만 입력합니다. 2일 넘게 재확인하지 않으면 화면에서 '접수 확인 필요'로 바뀝니다.
- 확인할 수 없는 급여·복지·마감일은 '미공개' 또는 '확인 필요'. 추정치 금지.
- `status=closed`이거나 `deadline`이 지난 공고는 화면에서 자동 제외하고 정리 작업에서 삭제합니다.
- 사람인 `rec_idx`를 우선 중복 기준으로 쓰고, 없으면 정규화한 회사명·직무·위치를 기준으로 병합합니다.

## 기능
- 회사명·직무·지역 통합 검색
- 지역·직무·연봉 공개·접수 확인 필터 및 정렬
- 한눈에 보는 회사명·주소·연봉·복지 카드
- 최근 7일 등록, 관심 공고, 지원 표시
- CSV 내보내기, 브라우저 로컬 공고 추가 및 숨김
- 원본 사람인 검색 바로가기

**개인정보:** 공개 저장소·사이트에 개인 실명, 연락처, 이력서·포트폴리오 주소를 포함하지 않습니다. 관심·지원 정보는 브라우저에만 저장합니다.

사람인과 제휴하지 않은 개인용 페이지입니다.

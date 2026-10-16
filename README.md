# 🍊 GYUL JOB RADAR

부산 디자인·마케팅·기획 공고 목록. [웹사이트](https://akdamthevillan.github.io/GYUL-JOB-RADAR/)

## 데이터
- 초기 공고 21건은 과거 조사 링크이며, 접수 상태를 보장하지 않습니다.
- 매일 08:30(KST) GitHub Actions에서 Bing의 공개 RSS 검색 색인을 조회하여 **사람인 링크만** 추가합니다.
- 사람인 API 키는 필요하지 않습니다. 사람인 사이트를 직접 크롤링하지 않습니다.
- 색인에서 발견된 공고는 항상 **접수 확인 필요**입니다. 부산 근무지·실제 마감일·연봉·복지는 공고 원문에서 확인해야 합니다.
- 검색엔진 RSS가 차단되거나 결과를 반환하지 않으면 자동 추가되지 않습니다. 마지막 성공 시각과 오류 상태를 표시합니다.
- 검색 범위는 전체 부산 공고를 보장하지 않습니다.

## 운영
1. Settings → Pages → Build and deployment → Source를 **GitHub Actions**로 설정합니다.
2. Actions → Update job index and publish → Run workflow를 1회 실행합니다.
3. Actions 실행 권한이 부족하면 Settings → Actions → General → Workflow permissions에서 **Read and write permissions**를 설정합니다.
4. 이후 매일 실행합니다. GitHub Actions 예약 실행은 지연될 수 있습니다.

## 파일
- `index.html`: 화면 및 검색·필터·CSV 다운로드
- `data/jobs.json`: 공개 공고 목록
- `data/meta.json`: 갱신 상태
- `scripts/refresh.py`: 공개 검색 색인에서 사람인 공고 링크 탐색
- `.github/workflows/daily.yml`: 자동 갱신·배포

공개 저장소에 이력서·실명·연락처 등 개인 정보를 올리지 않습니다. 이 사이트는 사람인과 제휴하지 않습니다.

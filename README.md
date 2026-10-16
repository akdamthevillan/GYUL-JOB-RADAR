# 🍊 GYUL JOB RADAR

[웹사이트](https://akdamthevillan.github.io/GYUL-JOB-RADAR/) · [Actions](https://github.com/akdamthevillan/GYUL-JOB-RADAR/actions)

부산 디자인·마케팅·기획 채용공고 탐색.

## 사용 방법
- **사람인 실시간 검색**: 부산 전체, 디자인, 패키지, SNS, 콘텐츠 마케팅, 상품기획, GTQ 등 사람인 원본 검색 결과를 직접 엽니다.
- **저장된 공고**: 이전에 조사한 공고 링크와 공개 검색 색인에서 발견된 공고를 검색·필터합니다.
- **공고 직접 추가**: 사람인 공고 링크·회사명·업무를 입력하면 해당 브라우저에 저장됩니다(공개 저장소에는 전송되지 않음).
- **CSV 저장**: 현재 필터된 목록을 내보냅니다.

## 업데이트
- 매일 08:30 KST에 GitHub Actions 실행.
- 외부 **공개 검색엔진의 색인**에 나타난 사람인 링크만 탐색하며, 직접 사람인 채용 검색 페이지에 자동 요청하지 않습니다.
- 검색엔진 색인 결과가 없거나 수집에 실패하면 기존 공고를 보존하고 오류를 표시합니다. **모든 공고 수집이나 자동 신규 발견을 보장하지 않습니다.**
- 사람인의 사전 동의 없는 자동화된 데이터베이스 접근·크롤링은 약관으로 금지되어 있어 직접 수집 기능은 사용하지 않습니다.
- 실제 접수 상태, 근무지, 연봉, 복지는 사람인 원문에서 확인해야 합니다.

## 배포
1. Settings → Pages → Source: **GitHub Actions**.
2. Actions → Update job index and publish → Run workflow.
3. 공개 페이지에 개인 실명이나 이력서를 올리지 마세요.

## 파일
- `index.html`: 페이지 / 원본 검색 바로가기 / 로컬 등록 / CSV
- `data/jobs.json`: 초기 공고 및 공개 검색 색인 목록
- `data/meta.json`: 갱신 정보
- `scripts/refresh.py`: 검색엔진의 공개 색인 조회
- `.github/workflows/daily.yml`: GitHub Pages 배포 및 정기 실행

사람인과 제휴한 서비스가 아닙니다.

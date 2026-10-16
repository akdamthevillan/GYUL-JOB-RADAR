# 🍊 GYUL JOB RADAR

[채용공고 대시보드](https://akdamthevillan.github.io/GYUL-JOB-RADAR/) · [GitHub 저장소](https://github.com/akdamthevillan/GYUL-JOB-RADAR)

부산의 디자인·마케팅·기획 채용공고를 요청할 때 수동 갱신하는 개인용 웹사이트입니다.

## 갱신
1. ChatGPT에 '사람인 부산 공고 다시 확인하고 GYUL JOB RADAR 업데이트해줘'라고 요청합니다.
2. 확인 가능한 공개 사람인 공고를 조사하고 기존 `data/jobs.json`과 중복 비교합니다.
3. 신규 공고 추가·공고 정보 수정·확인된 마감 상태 변경 후 GitHub 저장소에 반영합니다.
4. `main`에 변경이 반영되면 GitHub Pages가 자동 배포됩니다.

예약 수집 및 사람인 검색페이지 직접 크롤링은 사용하지 않습니다. 공고의 접수 가능 여부와 상세 조건은 사람인 원문에서 최종 확인해야 합니다.

## 기능
- 디자인·마케팅·기획 공고 검색 및 지역 필터
- 사람인 부산 검색 바로가기
- 공고 수동 추가 (해당 브라우저에만 저장)
- CSV 다운로드

## 데이터
- `index.html`: 페이지
- `data/jobs.json`: 저장된 공고
- `data/meta.json`: 마지막 반영 상태
- `.github/workflows/daily.yml`: GitHub Pages 배포 (push와 수동 실행만)

개인 실명·이력서·연락처는 공개하지 않습니다. 사이트는 사람인과 제휴하지 않습니다.

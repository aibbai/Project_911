# 서울 응급의료 허브 v1

## 핵심 구조
- 일반 23개 자치구: 공공데이터포털 NMC 실시간 응급실 가용병상 API
- 강북구: 대한병원 7석, 서울현대병원 7석, 강북으뜸병원 3석 (등록 응급실 병상 수)
- 마포구: 신촌연세병원 6석 (등록 응급실 병상 수)
- 강북구·마포구는 `실시간 가용병상 확인 불가 / API 미제공`으로 표시
- 두 예외 구에는 인접 자치구의 실시간 가용병상도 함께 표시
- Safety DSSP-IF-00242 관련 코드/키/CSV 의존성 제거

## 실행
1. `.env_v1.example`을 참고해 `.env`에 `DATA_GO_KR_KEY`를 설정합니다.
2. `run_emergency_hub_v1.bat`를 실행합니다. (브라우저에서 메인 화면이 자동으로 열림)
3. 자동으로 안 열리면 `http://127.0.0.1:5000`에 접속합니다.

## 폴더 구조
```
app_integrated_v1.py          Flask 서버 (/ 메인, /beds 병상, /analysis 분석)
run_emergency_hub_v1.bat      Windows 실행 파일
templates/
  base.html                   공통 뼈대 (CSS·폰트·Tailwind)
  header.html                 공통 헤더 (페이지 이동 메뉴)
  footer.html                 공통 푸터
  main.html                   메인 화면            → /
  real_time.html              병상 관제 화면        → /beds
  predict.html                분석·예측 화면        → /analysis
static/css/                   화면별 CSS (SEOUL_EMERGENCY_HUB.css, 실시간_병상관제_v1.css)
static/js/                    화면별 JS (실시간_병상관제_v1.js)
outputs/dashboard_data.json   예측 노트북 결과 (분석 화면 데이터)
```

## 화면 파일 찾는 순서
- 메인: `.env`의 HOME_FILE → `main.html` → `SEOUL_EMERGENCY_HUB.html`
- 병상: `.env`의 BEDS_FILE → `real_time.html` → `실시간_병상관제_v1.html`
- 분석: `.env`의 ANALYSIS_FILE → `predict.html` → `데이터분석_예측.html`
- 예전 단독 HTML은 새 템플릿이 없을 때만 쓰는 백업입니다.
- `base.html`·`header.html`·`footer.html` 중 하나라도 없으면 화면 대신 오류 json이 표시됩니다.
- html을 고치면 서버를 재시작하지 않아도 새로고침만으로 반영됩니다.

# Render Web Service 배포

현재 상태는 **배포 준비**입니다. Render HTTPS URL 생성과 실제 브라우저 검증 전까지 인터넷 배포 완료로 판단하지 않습니다.

## 실제 소스 진단

| 항목 | 확인 결과 |
|---|---|
| 로컬 진입점 | `backend.app.main:app`, `services.main:app`은 호환 진입점 |
| Render 진입점 | `backend.app.render_app:app` — 기존 앱 팩토리·분석 함수를 재사용 |
| 프론트엔드 | `/`에서 `apps/web/offline.html`, `/analysis`, `/live` 제공. `/apps/web/` 허용 목록으로 JS/CSS/Leaflet 제공 |
| API 요청 | 브라우저는 same-origin `/api/...` 사용. 실제 UI JS/HTML/TSX에 localhost 요청 없음 |
| Python | `.python-version`으로 3.12 계열 지정 |
| 의존성 | FastAPI, Uvicorn, requests, python-dotenv. 기존 ingest의 openpyxl·선택 Postgres의 psycopg 보존. 배포에 불필요한 pytest/httpx/pandas는 `requirements-render.txt`에서 제외; 기존 로컬 `requirements.txt` 유지 |
| 시작 수집 | 기존 lifespan이 시작 시와 900초마다 `external.refresh()`를 백그라운드 실행. 페이지/상태 요청·분류 방식 유지 |
| 초기 DB | Storage/ResearchService/legacy Store가 디렉터리·스키마 자동 생성 |
| 원자료 | GitHub에는 원본 XLSX/CSV와 runtime DB가 없음. API 재수집만으로 과거 서울시 실적/세션 복원 불가 |
| 필수 정적 파일 | HTML/JS/CSS·Leaflet·공식 분류 JSON/가이드·`data/seed`·Python 소스. Node 빌드는 기본 FastAPI 화면에 불필요 |

## 재시작·데이터 복원 전략 (방법 A)

GitHub에 `data/seed/research.jsonl.gz`와 manifest를 포함합니다. 서울특별시 공공데이터로부터 기존 전처리기를 사용해 만든 약 3.51 MiB의 **파생 분석 입력**입니다.

- D1: 시설별 연간/월별 급속 kWh, 행수, 유형 이력 (187개 수요 시설)
- OA-21712: 공식 시설·주소·설비 근거 (188개 시설)
- D2: 시작/종료시각·시설명·행 식별자·품질 플래그 (215,532행)
- 포함하지 않음: 키·토큰, 수집 DB, 환경공단 운영상태/시각, 수동 confirmed/review, 원본 세션 본문·충전량

출처: [OA-22249](https://data.seoul.go.kr/dataList/OA-22249/F/1/datasetView.do), [OA-21712](https://data.seoul.go.kr/dataList/OA-21712/S/1/datasetView.do), [OA-22258](https://data.seoul.go.kr/dataList/OA-22258/F/1/datasetView.do). 제공·저작권자 서울특별시, 공공누리 제1유형(출처표시). 전처리로 만든 파생자료이며 원자료 그대로의 배포는 아닙니다. 원자료 해시와 파생 seed 해시는 manifest에 기록합니다.

복원 순서:

1. Render가 Python 패키지 설치 후 seed 해시를 검사합니다. 키와 외부 API는 build에 필요 없습니다.
2. 프로세스 시작 시 빈 runtime에 SQLite 스키마를 생성하고 seed를 단일 트랜잭션으로 복원합니다. 기존 seed 버전이면 다시 넣지 않고 기존 수동 검토를 보존합니다.
3. 즉시 UI와 `/health`를 제공합니다. 아직 관측이 없으면 운영 API는 준비 중/503을 표시하며 임의 시설·실시간 상태를 만들지 않습니다.
4. 기존 환경공단 수집 성공 후 기존 `ResearchService.prepare_all()`로 현재 관측에 시설을 연결합니다. seed 어댑터는 XLSX/CSV 읽기만 대체하며 매칭·D/Q/B·정비·시뮬레이션 함수는 상속한 원래 함수를 실행합니다.
5. 다음 수집 성공 시에도 같은 알고리즘으로 연결을 갱신합니다. 실패한 분석 준비는 원문 오류를 로그에 출력하지 않습니다. `/api/deployment/status`로 `phase`를 확인합니다.

A. runtime 없이 서버 실행: 가능. B. DB 자동 생성: 가능. C. 원본은 Git에 없음. D. 새 seed에서 정적 입력을 복원한 후 실제 수집에 연결. E. 현재 설비·상태는 API에서, 과거 수요·세션·시설대장은 seed에서 복원합니다.

수동 검토·과거 API 관측 이력은 seed로 복원되지 않습니다. 로컬 운영 DB는 수정하지 않습니다. seed를 변경하지 않은 재시작은 배포 서버의 수동 검토를 지우지 않습니다. seed 재생성은 원본이 있는 로컬에서만 실행합니다.

```powershell
.\.venv\Scripts\python.exe scripts/build_render_seed.py
.\.venv\Scripts\python.exe scripts/verify_render_seed_parity.py
```

## Render 정확한 설정

- Repository: `woojk4712/capstone1`
- Branch: `main`
- Runtime: Python 3
- Root Directory: 비움 (저장소 루트)
- Build Command:

```bash
pip install -r requirements-render.txt && python scripts/check_render_seed.py
```

- Start Command:

```bash
python -m uvicorn backend.app.render_app:app --host 0.0.0.0 --port $PORT --workers 1 --no-proxy-headers
```

- Health Check Path: `/health` → `{"status":"ok"}`. 환경공단 연결·DB 자료 준비와 분리합니다.
- 단일 worker: SQLite와 백그라운드 수집의 중복 실행 방지.
- `render.yaml`: 무료 Web Service Blueprint. New → Blueprint로 가져올 수도 있습니다. 수동 Web Service 생성 시 아래 환경변수를 직접 입력합니다.

## 환경변수 (이름만)

수동 Web Service에서 필수:

```text
CHARGEOPS_DEPLOYMENT
ME_SERVICE_KEY
ME_URL
ME_STATUS_URL
```

비밀이 아닌 설정·공식 URL은 `render.yaml`에 정의했습니다. 키는 Render Dashboard에서만 입력합니다. Blueprint는 ME_SERVICE_KEY를 별도로 요청합니다.

선택:

```text
PUBLIC_ORIGIN
CHARGEOPS_RUNTIME_DIR
KEPCO_SERVICE_KEY
KEPCO_URL
KEPCO_CONTRACT
```

`PUBLIC_ORIGIN`은 커스텀 도메인 사용 시 필요합니다. 기본 onrender.com은 Render가 제공하는 `RENDER_EXTERNAL_URL`을 사용해 HTTPS Origin을 검증합니다. 원래 수동 수집·관리 변경 차단은 유지하고 같은 출처의 계산 전용 시뮬레이션을 허용합니다. 외부 TLS 종료 후에도 클라이언트 IP를 localhost로 위장하거나 전달 헤더를 전부 신뢰하지 않습니다.

한전은 핵심 분석 필수가 아니므로 KEPCO 설정 없이 시작합니다. 키가 없어도 프로세스·health·정적 화면은 동작하고 실시간 API만 준비되지 않았음을 표시합니다. Render 모드에서만 Dashboard 환경변수를 읽도록 확장했으며 Windows 로컬은 기존 루트 `.env` 읽기와 `run-local.cmd`를 유지합니다. `.env`를 Render나 GitHub로 업로드하지 않습니다.

## 무료 플랜과 영구 저장

[Render 무료 안내](https://render.com/docs/free)에 따르면 15분 유휴 후 정지하고 다음 접속 시 재시작하며, 정지/재시작/재배포마다 로컬 SQLite 변경이 사라집니다. 재기동 자체는 약 1분이 걸릴 수 있고 실제 수집·매칭 시간이 추가됩니다. 이번 로컬 seed 복원은 약 2.1초였으며 Render CPU에서의 보장값이 아닙니다. 실제 API 재수집 시간은 이 환경에서 측정하지 못했습니다. 페이지 수와 네트워크/제공기관 응답에 따라 달라집니다.

무료에서도 seed로 정적 분석 입력은 복원되므로 파일 손실만으로 영구 빈 화면이 되는 문제는 해결했습니다. 단, 재기동 직후 API 인증 실패·timeout이면 최신 운영현황과 확정 연구시설 연결은 준비되지 않습니다. `/health` 200은 수집·연구 준비 완료를 의미하지 않습니다. `/api/deployment/status`의 ready, confirmed 수 및 `/api/system/status`의 fresh/connected를 함께 확인하세요.

무료 플랜은 메모리 512MB 제한이 있습니다. 기존 로컬 저장 관측에는 76,163개 설비가 있었으며 원래 코드가 Python에서 전체 관측을 읽고 지도·주변망을 계산합니다. 무료 Render에서 전체 실제 관측의 최대 메모리·응답시간은 아직 측정하지 못했습니다. 발표 전 실제 데이터로 검증해야 하며 OOM/재시작이면 더 큰 유료 인스턴스로 변경하세요. 데이터 규모를 줄이거나 기존 알고리즘을 임의로 바꾸지 않았습니다. API 장애 중에도 중간발표 준비 상태를 유지해야 한다면 유료 서비스+Persistent Disk가 더 안정적입니다.

[Persistent Disk](https://render.com/docs/disks)는 유료 서비스에서만 가능합니다. 유료로 전환할 때 디스크를 `/var/data`에 마운트하고 `CHARGEOPS_RUNTIME_DIR`을 그 아래 전용 폴더로 지정하면 동일한 SQLite 구조를 유지합니다. 빌드 시 디스크를 요구하지 않습니다. 모든 SQLite는 그 runtime 경로를 사용합니다. 다른 서비스/worker를 같은 DB에 붙이지 말고 저장 용량을 관리합니다. 이번 단계에서 PostgreSQL 이전이나 결제/디스크 생성은 수행하지 않습니다.

## 공개 후 확인

URL을 받은 뒤:

```powershell
.\.venv\Scripts\python.exe scripts/verify_render_url.py https://YOUR-SERVICE.onrender.com
```

이 도구는 응답 본문/키를 출력하지 않고 아래 URL의 HTTP 상태와 수집/연구 준비 여부를 검사합니다. 전부 200이어도 브라우저 UI 검증은 별도입니다.

- `/`, `/health`, `/api/system/status`, `/api/chargers`, `/api/analysis/stations`, `/api/deployment/status`
- Leaflet JS/CSS, 기본 프론트 JS/CSS

브라우저 확인 순서: 운영현황 지도 → 자치구·시설 검색 → 복구 순위·잠재 영향 → D2 정비 히트맵/후보 → Before/After 복구 선택·해제 → 데이터 품질. 개발자도구의 JS 오류·실제 요청 404/500/503을 확인합니다. 상태가 오래되면 명시적 과거 재현으로 구분하며 정상 대상이 없으면 빈 결과를 성공으로 위장하지 않습니다. 지도 타일은 HTTPS OpenStreetMap 외부 서비스이므로 실제 Render URL에서 별도 접속 확인합니다. 폰트는 브라우저 fallback이 있습니다. 기본 지도 마커는 divIcon/circleMarker이므로 별도 marker PNG를 요구하지 않습니다.

검증 결과·cold-start 시간·현재 수집 완료 시간·메모리·검색/순위/시뮬레이션 결과를 기록한 다음 실제 배포 완료로 판단합니다.

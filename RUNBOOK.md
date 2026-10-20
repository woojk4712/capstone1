# 로컬 실행과 구현 상태

현재 폴더에서 `run-local.cmd`를 실행하고 **http://127.0.0.1:8000**을 엽니다. 기본은 실제 데이터 연결 대기입니다. 상단 **샘플 데이터**를 직접 선택하면 시설 선택 → 복구 우선순위 체크 → 개선 전/후 → 초기화 흐름을 사용할 수 있습니다. 샘플의 시설 위치·실적·설비는 가상입니다.

## 실행 방법

### 1. 패키지 설치 없이 로컬 경량 실행

이 PC에는 시스템 Python이 없지만 Codex 내장 Python 3.12.14가 있습니다. `run-local.cmd`와 아래 스크립트는 이를 찾습니다. 다른 PC에는 Python 3.12 이상이 필요합니다.

```powershell
.\scripts\run.ps1 serve
# 원자료 등록/재검사 (openpyxl 필요)
.\scripts\run.ps1 ingest
# 외부 수집 1회
.\scripts\run.ps1 collect
# unittest 검사
.\scripts\run.ps1 test
```

경량 실행은 Python 표준 HTTP 서버·SQLite, 동일 분석 엔진과 브라우저 JS/CSS를 사용합니다. 지도는 OSM 래스터 타일과 좌표 투영, 차트는 CSS로 표시합니다. 실제 키가 없어도 원자료 품질 화면은 사용할 수 있습니다. 샘플은 자동으로 활성화되지 않습니다.

### 2. React / FastAPI 개발 실행

네트워크가 허용되는 환경에서 다음을 실행합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m services.ingest
.\.venv\Scripts\python -m uvicorn services.main:app --host 127.0.0.1 --port 8000
# 별도 터미널
npm install
npm run dev
# http://localhost:5173
npm run build
```

React·TypeScript·Vite 진입점은 `apps/web/src/main.tsx`입니다. React에서 동일 대시보드 뷰를 마운트하고, ECharts와 MapLibre를 주입합니다. Tailwind Vite 통합을 포함하며 화면 상세 스타일은 CSS입니다. 분석은 브라우저에서 재구현하지 않고 API 응답으로 통일했습니다.

현재 환경에서는 npm 저장소 접근이 `EACCES`로 차단됩니다. React 의존성 설치, TypeScript 검사, Vite 빌드, lock 파일 생성은 **미검증**입니다. FastAPI/uvicorn도 현재 내장 Python에 설치되지 않아 ASGI 실행은 **미검증**입니다. 위 버전 범위로 최초 설치한 뒤 생성되는 `package-lock.json`을 보관하세요. Docker도 현재 설치 경로가 없어 실행하지 못했습니다.

### 3. Docker Compose

`.env.example`을 `.env`로 복사한 뒤 값을 설정합니다. 키를 저장소에 커밋하지 마세요.

```powershell
Copy-Item .env.example .env
# .env를 로컬 편집한 뒤
 docker compose up --build -d
 docker compose exec api python -m services.ingest /sources/"서울시 소유 전기차 충전소의 충전량(12월말까지).xlsx" /sources/"서울시 소유 전기차충전기 일별 시간별 충전현황(2025년).xlsx"
 docker compose exec api python -m services.worker
```

웹: http://127.0.0.1:8080, API: http://127.0.0.1:8000/api/v1/health. DB 포트는 외부에 노출하지 않습니다. 개발용 DB 암호는 로컬 설정으로 바꿀 수 있습니다. worker는 별도 프로세스로 수집하며 웹 조회가 외부 API를 기다리지 않습니다. PostGIS에는 스냅샷별 공간 좌표와 GiST 인덱스, 반경 질의 함수를 저장합니다. Python 분석 엔진은 단위 테스트와 동일한 구면 직선거리를 계산합니다.

## API 연결과 검증

서버만 `.env`를 읽습니다. `.env` 수정 후 API·worker를 다시 시작하세요. 프런트엔드에는 인증키를 전달하지 않습니다.

- `ME_SERVICE_KEY`: 환경공단 공공데이터포털 키. 인코딩/디코딩 키의 중복 인코딩을 방지합니다.
- `ME_INVENTORY_URL`: 설비 목록 경로. 기본 `getChargerInfo`는 실행 대상 후보이며 최신 가이드 및 인증 응답으로 확인해야 합니다.
- `ME_STATUS_MAP`, `ME_FAST_TYPES`: 최신 가이드/실응답에서 확인한 상태 코드·급속 유형 목록을 JSON으로 설정합니다. 검증 전에는 빈 값과 UNKNOWN 상태를 사용합니다.
- `ME_MAPPING_VERIFIED`: 검토 후 true. 숫자 코드를 임의로 정상/중지로 확정하지 않습니다.
- `ME_INVENTORY_CURRENT_STATUS_VERIFIED`: 설비 목록의 상태가 현재 상태 확인을 의미한다는 제공기관 근거가 있을 때만 true. 기본 false이며 `statUpdDt`를 상태 변경시각이라는 이유만으로 현재 확인시각으로 사용하지 않습니다.
- `KEPCO_SERVICE_KEY`, `KEPCO_URL`: **전력데이터개방포털** 키와 해당 승인 API 주소. 공공데이터포털의 환경공단 키와 동일하다고 가정하지 않습니다.
- `KEPCO_ITEMS_PATH`, `KEPCO_TOTAL_PATH`, `KEPCO_KEY_PARAM`: 실제 응답의 목록·전체 건수 경로와 키 파라미터를 설정합니다.
- `KEPCO_FIELD_MAP`: `{ "id": "실제설비ID필드", "updated_at": "ISO시각필드", "status": "상태필드" }`, `KEPCO_STATUS_MAP`은 검증된 상태 매핑. 현재 JSON 경로 추출과 공통 XML item 형태를 지원하므로 다른 구조는 어댑터 수정이 필요합니다.

수집기는 모든 페이지의 건수·페이지 번호·응답 해시를 검사합니다. 부분 수집은 발행하지 않습니다. 시간초과는 최대 3회 지수 재시도, 인증/할당량 오류는 별도 상태입니다. 실패 전 수신 원문도 `data/raw`에 보관하며 키를 포함한 요청 URL은 로그에 남기지 않습니다. 한전 장애는 환경공단 스냅샷을 막지 않습니다. 증분 상태 API는 현재 수집하지 않으며, 현재 설비 목록의 상태 확인 의미가 검증되기 전 모든 실관측 상태가 보류됩니다.

2026-10-16에 [환경공단 소개 페이지](https://www.data.go.kr/data/15076352/openapi.do)에서 가이드 v1.25의 존재, 상태 조회 경로·페이지 변수·`statUpdDt` 의미를 확인했습니다. 가이드 파일 본문 및 인증 실응답은 확보하지 못했습니다. [한국전력 소개 페이지](https://www.data.go.kr/data/15147132/openapi.do)는 전력데이터개방포털 가입·인증을 안내하는 LINK API입니다. 실제 승인 주소·필드·코드는 미확정입니다. 숫자 코드와 API 실연동이 검증되었다고 간주하면 안 됩니다.

## 시설 매칭 검토

데이터 품질 → **시설 매칭 검토**에서 원자료명, 후보 시설의 주소·좌표, 검토자와 근거를 확인한 뒤 저장합니다. `.env`의 `ADMIN_TOKEN`이 쓰기 인증에 필요하며 토큰은 브라우저 저장소에 저장하지 않습니다. 이름 유사도는 후보 생성에만 사용합니다.

승인된 명칭만 실제 급속 실적과 연결합니다. 독립 물리 설비, 출력 공유 없음, 접근·호환성 확인은 별도로 기록합니다. 공유출력 그룹 계산은 현재 구현 범위에서 제외하여 해당 시설의 정밀 복구 선택을 제한합니다. 현재 매칭 편집기는 시설 하나와 원자료명 하나의 연결을 지원하며 별칭 병합·다대다 정규화는 보류합니다.

매칭 수정은 원본 API 스냅샷을 변경하지 않습니다. 매칭 버전으로 파생 스냅샷을 구분하고 기존 분석 실행에 포함된 상태·수요·Q95를 고정합니다. 새 관측이 오면 기존 시나리오에 이전 관측 기준 표시를 합니다. 반경을 바꾸면 선택을 초기화하여 새 기준으로 계산합니다. 전후 비교 자체는 필터와 지도 위치를 유지합니다.

한전 설비의 공통 ID가 없으면 교차검증은 `매칭 불가`입니다. 검토된 설비 대응표는 `Store.put('links', {'charger_id': 'ME:시설:설비', 'secondary_id': '한전 설비 ID', 'approved': True, 'evidence': '동일 물리 설비 근거'})`로 서버에서 등록할 수 있습니다. 상세 API는 이 표와 검증된 필드 매핑을 사용해 일치/불일치/5분 초과 시차/매칭 불가를 반환합니다. 현재 관리자 UI에는 설비별 한전 대응표 편집기가 없습니다.

## 원자료와 정비 분석

[원자료 품질 보고서](reports/source-quality.md), [기계 판독 보고서](reports/source-quality.json)를 제공합니다. 원본 XLSX는 수정하지 않았습니다. 원본 SHA-256, 시트·행 번호와 값, 품질 플래그는 `data/raw/<해시>.json.gz`에 기록합니다. 등록을 반복해도 같은 파일은 같은 자산 ID로 유지합니다. 원본 중복 유지 합산이 기본이며 동일 행 제거 민감도 합계는 별도로 기록합니다.

현재 시간별 파일은 2025년입니다. 2026년 종료 세션의 2025년 중첩분만 반영합니다. 종료≤시작·24시간 초과·음수 세션을 삭제하지 않고 원본에 플래그를 남기며 중첩 계산에서 격리합니다. 원본 시간별 열의 단위가 `kW`로 기재되어 있으므로 세션 분석에는 에너지를 사용하지 않습니다.

정비 추천은 급속 전용 이력과 일별 커버리지가 확인되어야 합니다. 현재 첨부만으로 확인되지 않아 실제 시설 추천은 보류합니다. 검토자가 근거를 확보하면 매칭 PATCH 본문에 `fast_only_history_verified`와 `covered_days: ["2025-01-01", ...]`를 기록할 수 있습니다. 원자료 세션이 없는 날을 임의로 커버리지에 넣으면 안 됩니다. 엔진은 15분 간격·60/120분 창·요일별 20일·자정/연말 경계와 비중첩 상위 3개 후보를 처리합니다. 2023~2024 파일을 원본 자산으로 추가할 수 있지만 현재 공개 조회는 2025년만 지원하며 다년 추천은 확장 작업입니다.

## 검증과 한계

```powershell
python -m unittest discover -s tests -v
node --check apps/web/src/dashboard.js
# 의존성과 브라우저 설치 후, 로컬 서버 실행 상태에서
npx playwright install chromium
npm run test:ui
```

[검증 결과와 미완료 항목](reports/verification.md)을 확인하세요. 이번 환경에서 로컬 HTTP 실행과 엔진/API 테스트를 검증했습니다. 브라우저 도구의 사용 가능한 브라우저가 0개여서 화면 캡처·모바일·키보드 시각 검증은 실행하지 못했습니다. UI 테스트 스크립트는 제공하지만 통과했다고 표시하지 않습니다. 실제 API 키·승인 응답·매칭 근거가 없어 실관측 분석 인수 조건은 아직 충족하지 못했습니다.

지도는 © OpenStreetMap contributors를 표시하고 표준 래스터 타일을 사용합니다. OSM 이용정책에 따라 대량 다운로드·선취득을 하지 않습니다. 타일 네트워크가 막히면 안내와 시설 좌표를 표시합니다. React 실행에서 타일 URL은 `VITE_TILE_URL`로 분리했습니다. 경량 실행은 기본 OSM URL을 사용합니다. API 키·원본 자료·DB는 정적 서버의 허용 목록에 포함되지 않습니다. 공개 배포는 수행하지 않았습니다.

외부 대체망 시설은 매칭 검토의 원자료 시설명에서 **외부 대체망 설비 검토 · 실적 연결 없음**을 선택해 설비 근거를 기록할 수 있습니다. 이 시설은 주변 정상 대체망으로만 사용하고 대상 시설 수·실적 정규화 모집단·출력 카드에는 넣지 않습니다. 실관측 대상 후보는 원자료와 동일한 명칭 또는 수동 검토된 시설로 한정하며, 동일 명칭만으로 실적을 자동 연결하지 않습니다.

## 2026-10-16 기능 확장

현재 기본 반경은 **500m**, 새 영향도는 **(D + Q + B) / 3 (0~1), impact-mean-v0.2**입니다. 기존 설계의 곱셈식·기본 1km와 구분합니다. 개선 전후 UI는 복구 시뮬레이션 탭에만 표시합니다. 자치구 전체 필터·시설명 자동완성·지도 휠/드래그·상태별 KPI·우선순위 전용 Panel을 추가했습니다.

상세 구현과 직접 검증은 [reports/upgrade-notes.md](reports/upgrade-notes.md)를 확인하세요. `run-local.cmd`는 서버 확인/백그라운드 실행 후 기본 브라우저를 엽니다. 자동 화면검사는 `node scripts/ui-check.mjs`(17개), 모델 검사는 `npm run test:model`(7개), Python 검사는 58개 통과했습니다. 이전 단락의 "브라우저 검증 미실행"은 초기 구현 당시 기록이며 최신 결과는 위 보고서가 우선합니다.

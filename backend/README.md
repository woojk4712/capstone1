> 최신 설치·수정 이력·공개 배포는 [루트 README](../README.md)와 [배포 문서](../docs/DEPLOYMENT.md)를 우선하세요. 아래는 단계별 개발 기록으로 과거 분류·수치가 포함됩니다.

# 외부 API 백엔드

루트 `.env`만 읽습니다. 프로세스 환경변수, `.env.example`, Vite 설정에서 키나 API 주소를 가져오지 않습니다. `.env` 내용과 요청 URL·응답 원문·예외 원문은 로그에 남기지 않습니다.

필수 설정 이름은 `ME_SERVICE_KEY`, `ME_URL`, `ME_STATUS_URL`, `KEPCO_SERVICE_KEY`, `KEPCO_URL`입니다. `backend/app/settings.py`의 `Path(__file__).resolve().parents[2]`가 프로젝트 루트입니다. 절대경로 `.env`를 읽으므로 실행 폴더가 달라도 동일합니다. 인증값 앞뒤/내부의 공백·NBSP·제로폭 공백은 로딩 시 제거하되 퍼센트 인코딩된 키를 자동 디코딩하지 않습니다. `ME_INVENTORY_URL`은 더 이상 사용하지 않습니다. 설정 변경 후 서버를 재시작하세요.

## 실행

사용자의 Windows PowerShell에서 다음 순서로 실행합니다. Agent/Sandbox에서는 이 실호출 명령을 실행하지 않습니다.

```powershell
cd "C:\Users\SAMSUNG\OneDrive\바탕 화면\capstone_mid"
.\run-local.cmd
```

위 두 명령 후 브라우저에서 `/api/system/status`, `/api/chargers`, `/`를 확인하면 됩니다. .venv와 서버 패키지는 준비되어 있어 일반 실행에 추가 설치가 필요하지 않습니다. run-local.cmd는 시스템 Python을 사용하지 않습니다. .venv가 없거나 패키지가 누락되면 오류를 표시하며 최초 설치에만 scripts/run_backend.ps1 -Install을 사용합니다. 대시보드는 http://127.0.0.1:8000/ , FastAPI 문서는 http://127.0.0.1:8000/docs 입니다.

요청 전송에는 requests, 환경변수에는 python-dotenv를 추가했습니다. 기존 D1/D2 패키지는 유지했습니다. 저장은 기존 sqlite3, 설정은 기존 Settings를 사용하므로 사용하지 않는 SQLAlchemy/pydantic-settings 의존성을 추가하지 않았습니다. FastAPI의 Pydantic 의존성은 FastAPI 설치 시 함께 설치됩니다.

`run-local.cmd`는 `.venv`만 사용하며 기본으로 collection_enabled=true인 FastAPI를 실행합니다. 패키지가 없다고 미리보기로 대체하지 않습니다. 미리보기는 `run-local.cmd --preview` 또는 `--no-collect`를 명시해야 합니다. 관리 중인 미리보기는 PID/instance 검증 후 실제 API 모드로 교체됩니다. 실행 후 runtime/uses_project_venv/collection_enabled를 재검증하고 일치해야 성공으로 처리합니다. 최종 실행 표와 검증 범위는 `reports/final-local-startup.md`에 있습니다.

첫 API 작업 전의 사이드바/KPI/탭/지도·상세 패널 디자인과 1차 수정 기능을 `/` 및 React 진입점에 복원했습니다. `/analysis`도 유지합니다. React는 npm Leaflet 1.9.4를 번들에 포함하고, 설치 없는 HTML은 CDN Leaflet을 사용합니다. CDN이 막히면 기존 SVG 지도 어댑터로 실제 좌표만 표시합니다. 이는 데이터 Mock 대체가 아닙니다. React 개발 서버는 `npm install` 후 `npm run dev`로 실행하며 `/api`는 Vite가 백엔드로 프록시합니다.

## 데이터 경로

프론트엔드 → 내부 FastAPI → 환경공단/한전 → SQLite → 내부 API → 지도 순서입니다. 백그라운드 수집은 시작 시와 15분마다 실행하며, 프론트엔드 조회로 외부 요청을 증가시키지 않습니다. 수집 도중 서버는 기존 성공 스냅샷을 제공합니다. 전체 페이지 수집에 성공했을 때만 새 데이터를 트랜잭션으로 반영합니다. 자동 HTTP 재시도와 리다이렉트는 하지 않습니다.

환경공단은 서울(`zcode=11`) 목록을 수집하고 ME_STATUS_URL의 최근 5분 변경 목록을 ID로 결합합니다. 증분 목록에 없는 설비는 목록 응답의 필드를 유지하고 없는 필드는 만들지 않습니다. 로컬 단일 테스트는 사용자가 요청한 pageNo=1, numOfRows=10, dataType=JSON만 전송합니다. 모든 서비스키는 requests의 params에 저장된 값 그대로 전달합니다. 지정 필드에 addrDetail, method도 포함합니다. `status`, `output_kw`, `latitude`, `longitude`, `collected_at`, `analysis_eligible`는 내부 계산 필드입니다.

`data/runtime/external-api.sqlite`의 `status_snapshots`는 원본 상태코드, 출력, 제공기관 상태 변경시각(`api_updated_at`), 백엔드 수집시각(`collected_at`)을 분리합니다. 실패해도 마지막 성공 데이터는 삭제하지 않지만 `/api/chargers`는 수집 실패 시 캐시 성공으로 위장하지 않고 HTTP 503과 status/source/error_type을 반환합니다. 15분 이상 지난 저장 데이터는 UNKNOWN 처리하고 대체망 추천에서 제외합니다. 성공적으로 0건을 수집한 경우에만 HTTP 200과 빈 목록을 반환합니다.

## 분류 검증

공식 [환경공단 명세](https://www.data.go.kr/data/15076352/openapi.do)는 인증 오류코드, 페이지 변수, `statUpdDt`가 상태 변경시각이라는 점을 설명합니다. 이번 환경에서는 인증 응답과 v1.25 가이드 본문을 확보하지 못했으므로 숫자 상태/급속 유형을 임의로 확정하지 않습니다.

루트 `.env`의 기존 설정 `ME_STATUS_MAP`(JSON 객체), `ME_FAST_TYPES`(JSON 배열)를 승인 명세와 실제 응답으로 검토한 후 `ME_MAPPING_VERIFIED=true`로 설정하세요. 상태 매핑의 내부 값은 AVAILABLE, CHARGING, STOPPED, MAINTENANCE, COMM_ERROR, UNKNOWN 중 하나입니다. 검증 전에도 실제 목록은 `unclassified_items`로 볼 수 있지만 화면은 분류 검증 대기로 표시하고 분석은 보류합니다. `/api/chargers`의 `items`는 검증된 급속 유형, 유효 좌표/출력, 삭제되지 않음(`delYn=N`), 이용제한 없음(`limitYn=N`)이 확인된 설비입니다. 존재하지 않는 필드를 기본 N으로 만들지 않습니다.

## 한전 계약

한전의 첫 응답 검사용 요청은 `docs/kepco_request_contract.json`으로 분리했습니다. 사용자가 제공한 예시의 apiKey, metroCd=11, cityCd=11, returnType=json을 적용하고 주소와 키는 루트 .env에서 읽습니다. pagination은 예시에 없어 미확인으로 두고 첫 응답만 검사합니다. `scripts/test_kepco_api.py`는 응답 필드/상태 매핑이 없어도 이 확인된 요청을 실행합니다. 실제 응답 구조 증거만 data/runtime/kepco-schema.json에 기록합니다.

운영 중 교차검증 어댑터는 실제 응답에서 검토한 `KEPCO_CONTRACT`가 있어야 활성화됩니다. 요청만 확인됐다는 이유로 KEPCO_FIELD_MAP/KEPCO_STATUS_MAP을 생성하지 않습니다. 한전 미검증은 환경공단과 D1/D2 분석을 막지 않으며 미검증 한전 안내는 웹에 표시하지 않습니다. 실제 연결 및 교차검증 정보가 있을 때만 해당 카드와 상세 항목을 표시합니다.

`KEPCO_CONTRACT`는 루트 `.env`의 JSON 객체이며 `verified`(true), `source`(검토 명세 출처), `key_param`(확인된 인증 파라미터), `items_path`(확인된 목록 경로), `id_field`, `status_field`, `status_map`(검증된 내부 상태 매핑)을 요구합니다. 추가 요청 변수는 `params`에 명시합니다. 현재는 승인된 단일 응답 목록 계약을 지원합니다. 페이지형/다른 인증 방식은 해당 승인 명세에 맞춰 어댑터를 확장해야 합니다.

서로 다른 API의 ID를 같은 설비라고 가정하지 않습니다. SQLite `charger_links`에 확인된 대응을 등록하고 `approved=1`로 지정해야 상세 API에 교차검증 정보를 제공합니다. 대응표나 비교 시각 검증이 없으면 일치/불일치를 확정하지 않습니다.

## 진단·검사

```powershell
python -m backend.app.collect --diagnose
python -m backend.app.collect
python -m unittest discover -s tests -v
node scripts/test-live-ui.mjs
```

진단과 실호출은 사용자 로컬 실행 결과로 판정합니다. Agent 검증은 주입 응답·임시 SQLite 및 외부 호출이 꺼진 미리보기만 사용합니다. DNS, SSL, timeout, ConnectionError, HTTP, 인증, 요청 파라미터, JSON/XML 오류를 구분하고 예외 원문은 출력하지 않습니다. 현재 결과는 `reports/local-integration-verification.md`를 확인하세요. 기존 sandbox의 network_permission_denied는 사용자 로컬 API 실패 판정 근거가 아닙니다.
## 핵심 분석대상 범위 (현재)

### 최종 분석 화면과 공식 시설대장 연결

최신 구현은 `backend/app/research.py`와 `apps/web/src/research-ui.js`입니다. 운영현황과 환경공단 수집은 기존 경로를 사용하며, 복구 우선순위·정비시간·시뮬레이션은 별도 연구 API를 사용합니다. 기술 진단은 데이터 품질 탭에서만 표시합니다.

실제 파일 세 개는 프로젝트 루트에 있으며 원본을 수정하지 않습니다. 파일이 루트에 없을 때만 `data/input/`에서 같은 이름을 찾습니다.

```powershell
.\.venv\Scripts\python.exe scripts\prepare_analysis.py --all
```

이 명령으로 D1 전처리, OA-21712 공식 이름·주소·유일성에 따른 매칭, D2 전처리, 분석 준비와 정비 후보 계산을 수행합니다. 외부 API를 호출하지 않습니다. 준비 결과는 SQLite에 반영되어 실행 중인 웹 API에서도 서버 재시작 없이 읽습니다. 웹 데이터 품질에서 수동 확정/보류한 결과도 다음 분석 조회에 반영됩니다.

`station_match`는 confirmed_auto/confirmed_manual/review/unmatched를 지원하며 독립 근거는 `match_evidence`에 저장합니다. 같은 이름만으로 자동 확정하지 않고 다중 주소·statId 충돌은 검토로 남깁니다. 기존 confirmed는 수동 확정과 호환합니다.

분석 API:

- `GET /api/analysis/stations`: Final 확정 핵심시설만 반환
- `GET /api/analysis/overview?radius=500&weight=equal`: 실제 복구 검토순위, 별도 잠재 영향, D/Q/B와 주변망
- `GET /api/analysis/quality`, `GET /api/analysis/matches`: 자료·연결률·매칭 근거
- `POST /api/analysis/matches/review`: 로컬 동일 출처의 명시적 사용자 검토 저장
- `GET /api/analysis/maintenance/{statId}`: 2025년 관측일 시작건수 히트맵과 1시간/2시간 후보
- `POST /api/analysis/simulate`: 원자료를 변경하지 않는 명목 정격출력 시나리오

기본은 Final, Preview OFF, 과거 관측 재현 OFF입니다. `preview=true`는 유일한 정규화 이름 정확 일치 review 후보를 추가하되 미확정 연구 검토로 표시합니다. `replay=true`는 마지막 실제 저장 관측을 과거 관측 시점으로 명시해 재현하며 현재 결과로 표시하지 않습니다. 가정 고장/복구는 `hypothetical=true`로 분리합니다. 어느 모드도 원본 환경공단 stat 또는 confirmed 상태를 바꾸지 않습니다.

유형은 OA-21712의 급속/완속 명시, 식별자, 용량 일치로 개별 설비를 확인합니다. 주변 유형 미확인 설비가 있으면 B/Impact는 확인된 급속망 기준 상한이므로 Final 복구순위에서 제외하고 잠재 영향 검토에만 표시합니다. 운영중지는 고장 확정이 아니며 점검중은 실제 복구 검토 대상에서 제외합니다.

최신 실제 수치와 브라우저 검증: `reports/research-workflow.md`. 아래의 이전 단계 설명보다 최신 보고서를 우선합니다.

운영현황 지도·검색·KPI는 `/api/chargers`의 실제 원자료에서 서울특별시 주소, 삭제되지 않은 설비(`delYn=N`), 유효 좌표를 확인하고 `statId`로 묶어 사용합니다. 환경공단 분류가 검증되면 백엔드에서 확인한 급속 대상만 표시하며, 검증 전에는 완속을 포함할 수 있는 서울 원자료임을 명시하고 원본 코드를 표시합니다. D1-D3 confirmed 수와 한전 상태는 운영현황 표시 조건에 포함하지 않습니다.

복구 우선순위·실제 이용량·정비시간·복구 시뮬레이션의 분석대상은 `GET /api/analysis/stations`의 confirmed 시설로 유지합니다. 전국 원자료는 별도 `/live` 화면 및 주변 대체망 입력으로 보존합니다. 전국 저장 건수를 핵심 분석 시설 수로 사용하지 않습니다. 한전 정보는 현재 운영현황에서 사용하지 않으며 데이터 품질 화면에만 “한전 교차검증: 미사용”으로 표시합니다.

D1 실제 엑셀은 프로젝트 루트에 있습니다. 전처리/후보표 재생성은 `.\.venv\Scripts\python.exe scripts\prepare_analysis.py`이며 외부 API를 호출하지 않습니다. 원본과 중복/0kWh 기록은 보존합니다. 결과는 `data/runtime/analysis.sqlite` 및 `data/runtime/analysis/`에 저장됩니다.

이름 유사도는 후보 생성에만 사용합니다. 현재는 OA-21712 공식 시설대장을 통한 자동 확정과 사용자 수동 확정을 구분합니다. `data/runtime/analysis/station-match-review.csv`의 후보 주소와 독립 근거를 확인하고 모호한 시설만 검토하세요. 최신 명령과 검증 결과는 `reports/research-workflow.md`를 참고하세요.

신규 백엔드 라우트 적용에는 일반 Windows PowerShell의 `.\run-local.cmd --restart`가 필요합니다. 이번 운영현황 변경은 프론트엔드 수정이므로 실행 중인 서버에서 페이지를 강력 새로고침하면 됩니다. 키·URL·외부 수집 코드는 변경하지 않았습니다. 분류 미검증은 API 미연결이 아니라 별도 검증 대기 상태입니다. 최신 브라우저 검증은 `reports/seoul-operations-fix.md`를 참고하세요.



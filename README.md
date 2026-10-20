# 실제 충전수요 및 운영상태 기반 서울시 전기차 충전 인프라 취약성 분석과 유지보수 운영최적화

실제 충전실적과 환경공단 운영상태를 연결해 서울 충전소 지도, 운영중지 복구 검토, 정비 후보시간, 복구 전후 정격출력 비교를 제공하는 캡스톤 프로젝트입니다.

- 저장소: https://github.com/woojk4712/capstone1
- 계획서: **실제충전수요 및 운영상태기반 서울시 급속충전 인프라 취약성 분석과 유지보수 운영최적화** (강성록, 김재우)
- 문서 갱신: 2026-10-20
- 공개 배포 상태: 업로드·외부 배포 확인 전입니다. 아래 배포 구성의 준비와 실제 서비스 공개는 구분합니다.

## 프로젝트 개요

환경공단 충전기 운영상태, 서울시 실제 충전량(D1), 공식 시설대장(OA-21712), 시간대별 충전이력(D2)을 이용하는 웹 시스템입니다. 한국전력(KEPCO)은 현재 핵심 연구분석 의존성이 아니며 선택적·미사용입니다.

## 화면과 기능

| 화면 | 구현된 동작 |
|---|---|
| 운영현황 | 서울 주소·삭제 여부·실제 좌표로 시설을 묶은 지도, 자치구/시설 검색, 상태·출력 필터, KPI, 상세 패널 |
| 복구 우선순위 | 서울 운영중지 설비 전체의 운영 점수와, D1 연결 연구시설의 수요 포함 분석을 구분 |
| 정비시간 | 실제 D2 세션의 요일×시간 히트맵, 연속 1시간/2시간 후보와 유효 관측일·보류 사유 |
| 복구 시뮬레이션 | 같은 관측시점의 선택 설비를 가상 복구하여 출력·설비 수·누적 회복량 비교 |
| 데이터 품질 | 원자료·수집 신선도·매칭 근거·분석 제외 사유·시설 연결 검토 |

실제 운영중지, 잠재 영향, 가정 시나리오, 과거 관측 재현을 구분합니다. API 실패나 실적 미연결을 0으로 바꾸거나 가짜 시설·히트맵으로 채우지 않습니다. 운영중지는 물리적 고장 확정이 아닙니다.

## 지금까지의 제작 과정과 수정 방향

이 문서는 현재 소스와 `reports/`에 남은 개발·검증 기록을 기준으로 정리했습니다. 이전 대화 전체를 복원한 기록은 아닙니다. 초기 설계는 [초기 README 보관본](docs/history/initial-design.md)에 보존했습니다. 초기 제안과 현재 코드를 비교할 때는 본 문서를 우선합니다.

1. **연구 질문과 데이터 기준 확립**: 설치 대수 중심 비교에서 실제 이용실적·정격출력·주변 대체망을 함께 보는 의사결정 지원으로 구체화했습니다. 과거 2025년 실적과 현재 관측을 분리하고, 서울 전체 급속시설 전수조사로 표현하지 않도록 했습니다.
2. **지도 중심 디자인 구현**: 참고 디자인에 맞춰 사이드바·상단 탭·흰색/회색 카드·지도와 우측 상세 패널을 구성했습니다. 검색 자동완성, 자치구 이동, 지도 확대·드래그, 이름 툴팁, 선택 마커 강조와 모바일 배치를 보완했습니다.
3. **필터와 탭의 역할 정리**: 자치구·시설·상태·출력 필터가 지도·목록·KPI에 같은 범위를 적용하도록 고쳤습니다. 복구 순위와 시뮬레이션은 해당 탭에만, 기술 진단은 데이터 품질 탭에 모았습니다. 화면 로딩·성공한 빈 결과·오류·오래된 관측을 분리했습니다.
4. **실제 API 연결과 실행기 개선**: 브라우저에서 공공데이터 키를 제거하고 FastAPI→외부 API→SQLite 구조로 바꿨습니다. 전체 페이지 수집 성공 후 반영, 실패 유형 구분, 마지막 관측 보존, 15분 신선도 판정과 명시적 재현 옵션을 적용했습니다. `run-local.cmd`는 프로젝트 가상환경과 서버 상태를 확인합니다.
5. **공식 명세 기반 분류**: 환경공단 v1.25 가이드와 해시 검증 계약을 사용합니다. 원본 상태코드·상태변경시각·수집시각을 분리합니다. 한전은 확인된 계약과 대응표가 있을 때만 보조적으로 사용하며 현재 연구분석에는 사용하지 않습니다.
6. **D1→시설대장→환경공단 연결**: 이름 유사도는 후보 생성에만 사용하고 공식 주소·시설 유일성·설비 ID 충돌·좌표 일관성을 검사하도록 강화했습니다. 자동/수동 확정과 독립 근거, 수동 보류를 보존합니다. 기록상 확정 시설은 81→100개로 늘었고 연구 정비 가능 시설은 84개였습니다. 이는 당시 데이터 결과이며 고정 상수가 아닙니다.
7. **분석식과 연구 화면 보완**: 초기 곱셈식, 이후 로그/Q95·고정 200kW 기준의 평균식에서, 최신 연구 경로는 평균순위 D·시설 출력비 Q·시설 대비 대체망 B를 사용하는 방식으로 발전했습니다. 미확인 주변 유형이 있으면 정확한 순위와 검토용 상한을 구분합니다.
8. **복구 대상 누락 해결**: D1에 연결되지 않은 서울 운영중지 설비도 복구 화면에 포함했습니다. 실적이 없는 시설의 수요를 만들어 넣지 않고 운영 점수 `(Q+B)/2`를 사용하며, D1이 연결된 경우 수요 포함 점수를 별도로 제공합니다. 관측을 고정해 지도·순위·선택·시뮬레이션이 같은 데이터를 사용합니다.
9. **공개 준비**: 재현용 원자료·해시·설치법·검증 명령·공개 서버 전용 진입점·Docker 구성을 추가했습니다. 공개 서버의 관리 변경과 수동 수집은 차단하고 계산 전용 시뮬레이션만 같은 출처에서 허용합니다.

관련 기록: [UI 개선](reports/upgrade-notes.md), [명세 분류](reports/me-v125-verification.md), [연구 구현](reports/research-workflow.md), [시설 연결 재검증](reports/analysis-expansion-verification.md). 기록별 수치와 식은 해당 단계의 결과입니다.

## 기술 구성과 파일 구조

```text
브라우저 → FastAPI 내부 API → SQLite → 분석 결과
                  ↓ 15분 주기
             환경공단 외부 API
D1 XLSX + D2 XLSX + 공식 시설대장 CSV → 전처리·시설 연결 → 분석 SQLite
```

- Python 3.12, FastAPI/Uvicorn, SQLite, requests, pandas/openpyxl
- 실제 기본 화면: `apps/web/offline.html` + JavaScript/CSS + 로컬 Leaflet (파일명 offline은 API 없는 서비스라는 의미가 아닙니다)
- 별도 React 19/TypeScript/Vite 진입점: `index.html`, `apps/web/src/main.tsx`
- `backend/app/main.py`: 로컬 API·수집·화면 라우트
- `backend/app/public.py`: 공개 서버 전용 진입점
- `backend/app/research.py`: 시설 연결·연구 분석·정비시간
- `backend/app/operational_view.py`, `operational_recovery.py`: 관측 고정·서울 복구 목록
- `services/`: 기존 분석 엔진과 `/api/v1` 호환 API. 과거 계산식과 최신 연구식을 혼용하지 않습니다.
- `scripts/`, `tests/`: 실행·전처리·진단·검증
- `infra/`, `compose.public.yaml`: 서버 배포 구성

## 주요 데이터와 데이터 파일 준비

원본 공공데이터 3개는 Git에서 제외합니다. 현재 로컬 원본은 삭제·이동하지 않습니다. 기본 웹 서버는 원본 없이도 실행되지만 실적·시설 연결·정비 분석을 재생성하려면 아래 파일과 본인 키로 수집한 환경공단 관측이 필요합니다.

| 자료·ID | 필요한 파일명 | 크기(bytes) | 필요 여부·재다운로드 | 저장 경로 |
|---|---|---:|---|---|
| 서울시 충전량 D1 · OA-22249 | `서울시 소유 전기차 충전소의 충전량(12월말까지).xlsx` | 1,795,169 (약 1.71 MiB) | 연간 급속 수요 분석 필수 · [공식 다운로드](https://data.seoul.go.kr/dataList/OA-22249/F/1/datasetView.do) | 프로젝트 루트 `./` |
| 서울시 시간별 충전이력 D2 · OA-22258 | `서울시 소유 전기차충전기 일별 시간별 충전현황(2025년).xlsx` | 8,205,516 (약 7.83 MiB) | 정비시간 분석 필수 · [공식 다운로드](https://data.seoul.go.kr/dataList/OA-22258/F/1/datasetView.do) | 프로젝트 루트 `./` |
| 서울시 공식 시설대장 · OA-21712 | `서울시 소유 전기차 충전소 정보.csv` | 73,385 (약 71.67 KiB) | 시설 연결·설비 근거 필수 · [공식 다운로드](https://data.seoul.go.kr/dataList/OA-21712/S/1/datasetView.do) | 프로젝트 루트 `./` |
| 한국환경공단 전기자동차 충전소 Open API | 원본 응답·수집 DB는 포함하지 않음 | 수집별 상이 | 운영상태·좌표·출력 · [API 신청](https://www.data.go.kr/data/15076352/openapi.do) | 키는 `.env`, 관측은 `data/runtime/`에 생성 |

파일명과 경로를 정확히 유지하세요. 현재 D1은 루트 또는 `data/raw/`, D2와 시설대장은 루트 또는 `data/input/`을 찾습니다. 혼동을 줄이기 위해 위 표처럼 세 파일 모두 루트에 두는 방식을 권장합니다. `data/input/manifest.json`은 작은 출처·크기·SHA-256 기록이므로 Git에 유지합니다. 파일은 공식 사이트 갱신에 따라 바뀔 수 있으며, 동일 수치를 재현하려면 manifest와 같은 버전이 필요합니다.

저작권자·제공기관은 서울특별시입니다. 공공데이터 출처와 이용조건은 공식 데이터셋 페이지를 따릅니다. 원자료는 수정하지 않으며 전처리의 중복 의심·0kWh·비정상 행 플래그를 보존합니다. D2 2023~2024년은 현재 2025 분석 입력에 포함하지 않습니다. 소형 설정 데이터 `docs/me_v125_classification.json`, `docs/kepco_request_contract.json`, 공식 분류 가이드와 지도 라이선스는 유지합니다.

`data/runtime/`의 수집 DB, `analysis.sqlite`, 스냅샷, 캐시와 서버 로그는 Git에 포함하지 않습니다. 새 clone에서는 서버 첫 실행으로 SQLite 스키마를 생성하고, 외부 수집 성공 후 `scripts/prepare_analysis.py --all`로 분석 DB를 재생성합니다. 수동 confirmed/review 판단과 과거 관측 이력은 자동 재현을 보장하지 않으므로 필요하면 Git 외부의 안전한 백업으로 관리합니다.

`.env`, 키, 원본 API 응답, 로컬 DB·로그·가상환경·캐시·계획서 원문은 배포 대상에서 제외했습니다. Leaflet은 [동봉 라이선스](apps/web/vendor/LICENSE.leaflet)를, 지도는 [지도 출처](apps/web/src/MAP_SOURCES.md)를 따릅니다. 소스코드의 별도 오픈소스 이용허락은 아직 지정하지 않았습니다.

## 로컬에서 재현하기

Python 3.12와 Git을 설치합니다. 기본 FastAPI 화면은 Node 설치 없이 실행할 수 있습니다.

```powershell
git clone https://github.com/woojk4712/capstone1.git
cd capstone1
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# 위 표의 원본 3개를 다운로드해 프로젝트 루트에 둔 후:
.\.venv\Scripts\python.exe scripts/verify_source_data.py
```

기존 `.env`가 있으면 복사로 덮어쓰지 마세요. 새 `.env`의 `ME_SERVICE_KEY`에 본인의 공공데이터포털 승인 키를 입력합니다. 키는 `VITE_` 변수나 프론트엔드에 넣지 않습니다. `ME_URL`, `ME_STATUS_URL`은 예제의 공식 URL을 사용합니다. 기본 백엔드는 프로세스 환경변수 대신 루트 `.env`를 읽으므로 서버에서도 파일 마운트가 필요합니다.

```powershell
.\run-local.cmd
# 첫 수집 성공 후 별도 터미널에서:
.\.venv\Scripts\python.exe scripts/prepare_analysis.py --all
```

접속: http://127.0.0.1:8000/ , API 문서: http://127.0.0.1:8000/docs . 실행기 상세는 [RUNBOOK](RUNBOOK.md)을 참고하세요. 전처리는 외부 API를 호출하지 않습니다. 빈 설치에서 환경공단 수집 전에 전처리하면 시설 연결이 아직 준비되지 않으므로 수집 성공 후 다시 실행합니다. 원자료 변경·수동 검토 후 분석 조회에 반영되며 수치는 저장 관측과 매칭 상태에 따라 달라집니다.

운영체제 공통 직접 실행:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
# 수집 성공 후 다른 터미널의 같은 가상환경에서 실행
python scripts/prepare_analysis.py --all
```

키가 없으면 화면·자료 검증은 가능하지만 최신 운영현황이나 확정 시설 분석이 완성되지 않습니다. `--preview`는 명시적인 미리보기 모드이며 실서비스 검증을 대신하지 않습니다.

React 개발 경로가 필요하면 Node.js 22에서 다음을 실행합니다. `/api`는 8000번 백엔드로 프록시됩니다.

```bash
npm install
npm run dev
npm run build
```

## 주요 분석 방법

D = 실제 수요 중요도, Q = 설비 출력 비중, B = 주변 대체망 부족도입니다. 수요 연결 설비는 D+Q+B를 평균·가중 결합하고, 서울 전체 운영중지 복구검토는 Q+B 기반 운영 영향도를 사용합니다. 정비시간은 D2의 요일·시간 이용패턴, 복구 Before/After는 정격출력을 기준으로 합니다.

### 최신 분석 기준

- 연구 분석은 확인된 급속 설비·확정 시설을 사용합니다. D는 유효 핵심시설 연간 급속 kWh의 평균순위 정규화(동률 평균, 단일시설 0.5), Q는 개별 출력/시설 출력 P, B는 `P/(P+A)`입니다. 기본 Impact는 `(D+Q+B)/3`이며 수요·출력·대체망 강조 가중치를 지원합니다.
- 연구 주변망 A는 동일 시설을 제외한 500m/1km 정상·제한 없음·급속 확인 정격출력입니다. 미확인 유형이 있으면 상한 검토로 표시합니다. 반경은 직선거리이며 다른 자치구·서울 경계 밖의 대체망도 포함합니다.
- 서울 전체 운영 복구 화면은 D1 미연결 설비도 보존하며 `OperationalImpact=(Q+B)/2`를 사용합니다. 이 경로의 주변망은 커넥터 유형 전체에서 확인된 정상·제한 없음 출력입니다. 연구 급속망 기준과 구분합니다. D가 연결되면 `DemandImpact=(D+Q+B)/3`를 추가합니다.
- 현재 복구 대상은 검증된 운영중지 상태입니다. 점검·통신오류·불확실 상태를 고장으로 바꾸지 않습니다. 오래된 관측은 현재 순위를 보류하고 재현 선택을 요구합니다.
- 정비 후보는 관측된 날짜의 시작건수·진행 중 기록·반기 안정성을 사용합니다. 무기록일을 0으로 채우지 않으며 혼합시설·운영시간 미확인 등은 보류합니다.
- 복구 시뮬레이션은 정격출력 변화만 계산합니다. 정상 출력 증가=중지 출력 감소=선택 회복 kW이며 원본 상태를 바꾸지 않습니다. 수요·대기시간·수리비 예측이 아닙니다.

## 주요 API

| 요청 | 용도 |
|---|---|
| `GET /api/system/status` | 수집·분류·신선도 |
| `GET /api/operations/stations?stopped_only=true` | 서울 운영중지 시설 |
| `GET /api/operations/recovery?radius=500` | 같은 관측의 복구 검토 목록 |
| `POST /api/operations/simulate` | 운영 복구 계산 |
| `GET /api/analysis/stations` | 확정 연구시설 |
| `GET /api/analysis/overview?radius=500&weight=equal` | 연구 분석·잠재 영향 |
| `GET /api/analysis/maintenance/{statId}` | 정비시간 |
| `GET /api/analysis/quality` | 품질·매칭·제외 사유 |
| `POST /api/analysis/simulate` | 연구 가정/복구 시나리오 |
| `POST /api/analysis/matches/review` | 로컬 전용 수동 검토 |

`preview=true`, `replay=true`, `hypothetical=true`는 명시적 검토·재현·가정 옵션입니다. 기본 Final/Preview OFF/과거 재현 OFF를 유지합니다. 시뮬레이션에는 조회한 `observationAt`을 전달해야 하며 관측 충돌 시 409를 처리합니다.

## 검증

```bash
python scripts/verify_source_data.py
python -m unittest discover -s tests -v
node --test tests/dashboard-model.test.mjs tests/live-inventory.test.mjs
npm run build
```

GitHub Actions의 `.github/workflows/verify.yml`은 Python·프론트 모델·Vite 빌드를 검사합니다. 원본이 Git에 없으므로 원자료 해시는 다운로드 후 로컬에서 검사합니다. 외부 인증 API와 지도 타일 성공 여부는 이 테스트만으로 보장하지 않습니다. 브라우저 회귀 검사 스크립트는 `scripts/check-operational-recovery.mjs`, `scripts/check-research-workflow.mjs`에 있습니다. 현재 실행 결과와 공개 확인의 한계는 [공개 준비 검증](reports/publication-verification.md)에 기록합니다.

## 환경변수와 보안

`.env.example`의 공개 URL과 변수명·비밀값 없는 설정을 참고해 루트 `.env`를 만듭니다. `ME_SERVICE_KEY`는 환경공단 키, `ME_URL`/`ME_STATUS_URL`은 해당 요청 URL입니다. `KEPCO_SERVICE_KEY`/`KEPCO_URL`은 선택적 한전 설정이며 현재 핵심 분석에 사용하지 않습니다. 인증 토큰·비밀번호는 예제에 넣지 않습니다.

기존 백엔드는 루트 `.env`를 직접 읽습니다. 현재 정상 동작하는 설정 읽기·수집 경로는 변경하지 않습니다. API 키를 소스·README·로그에 복사하거나 `VITE_`로 시작하는 프론트 변수에 넣지 않습니다. `.env`, runtime DB·로그·캐시·원본 데이터는 ignore 대상입니다.

업로드 전 검사 도구는 비밀값이나 일치한 줄을 출력하지 않습니다.

```powershell
.\.venv\Scripts\python.exe scripts/audit_github_upload.py --scope candidates
git check-ignore .env
# git add 후 반드시 실제 staged 내용도 검사
.\.venv\Scripts\python.exe scripts/audit_github_upload.py --scope staged
```

FAIL이면 commit/push를 중단하고 해당 파일을 검토합니다. 비밀정보 검사 결과·파일 목록은 [GitHub 준비 결과](reports/github-upload-preparation.md)에 기록합니다.

## GitHub 업로드 범위

이번 작업은 소스코드의 안전한 GitHub 업로드 준비입니다. 웹 UI, 수집 방식, 상태 분류, 시설 매칭과 confirmed/review, D/Q/B, 복구·정비·시뮬레이션 계산은 변경하지 않습니다.

GitHub Pages는 설정하지 않습니다. FastAPI 백엔드가 필요하므로 인터넷 공개 배포는 GitHub 업로드 후 별도로 진행합니다. 기존 배포 참고 구성은 보존하지만 이번 작업에서 배포하거나 활성화하지 않습니다. 원격 이력이 있으면 먼저 가져와 병합하며 force push는 사용하지 않습니다.

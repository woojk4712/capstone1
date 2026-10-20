# 서울시 핵심 분석대상 분리 결과

## 연결 상태와 분석 상태

기존 화면은 분석용 `state.base` 및 `/api/v1/overview`의 준비 여부를 원자료 표시와 함께 취급했습니다. 이전 전국 원자료 adapter는 `items/unclassified_items`를 그대로 분석 시설로 묶어 12,936개 시설을 메인 지도에 표시했습니다. 이 목록은 서울시 핵심 분석대상이 아닙니다.

이번 작업 시작 시 활성 애플리케이션 소스에는 정확히 `데이터 미연결`, `미연결`, `API 미연결`이라는 문자열이 남아 있지 않았습니다. 따라서 사용자 화면의 해당 문구가 어느 오래된 캐시/빌드에서 나왔는지 단정하지 않습니다. 남아 있던 분석 데이터 부재 fallback과 `Boolean(state.base)` 조건을 추적해 API 상태 판단에서 분리했습니다. 위치별 검색 결과는 `reports/connection-state-search.md`에 있습니다.

| 위치/조건 | 의미 및 변경 |
|---|---|
| `dashboard.js::load` | system/status·chargers와 analysis/stations를 따로 처리. 분석 응답 실패는 `분석 결과 준비 중`이며 API 성공을 지우지 않음 |
| `renderNotice` | API, 전국 원자료, 핵심 시설 매칭, 급속/상태 분류를 별도 표시 |
| `renderSummary` | API 연결이 아니라 핵심 데이터 응답 여부와 현재 구 필터를 사용. 분류 미검증 수치는 검증 필요로 표시 |
| `renderRanking`, `simulationView`, `analysisInfo` | 핵심 대상/분석 실행 준비 여부에 따른 분석 화면. 원자료 API 연결 상태와 분리 |
| `renderAutocomplete` | `/api/analysis/stations`의 confirmed 핵심 시설만 검색. 전국 목록을 검색 후보로 넣지 않음 |
| `renderMap` | 핵심 시설만 기본 지도에 표시. 선택 시 조회한 반경 내 대체망만 추가 |
| `qualityView`, `/live` | 전국 원자료 및 매칭 후보 검토를 별도 화면으로 분리. 원자료 화면임을 명시 |
| `services/api.py::snapshot` | live overview는 확인된 핵심 시설과 필요한 주변망만 분석. 명시적 sample 경로는 별도 유지 |

프론트 상태는 `apiConnected`, `rawDataAvailable`, `d1Available`, `stationMatchingReady`, `analysisDatasetReady`, `classificationVerified`로 분리했습니다. 새로고침마다 내부 API를 same-origin 상대경로로 조회합니다. 연결 상태를 localStorage/sessionStorage에 저장하지 않습니다.

## 실제 D1 확인

프로젝트 루트의 `서울시 소유 전기차 충전소의 충전량(12월말까지).xlsx`를 다시 읽었습니다. 원본 파일을 변경하지 않았습니다.

- 실제 컬럼: `날짜`, `충전소명`, `충전기 유형`, `충전량(kWh)`
- 데이터 행: **67,993행**
- 전체 고유 충전소명: **213개**
- 2025년 급속 기록이 있는 고유 충전소명: **187개**
- 전체 0kWh 행: **339행**, 보존
- 전체 동일 행 초과: **109행**, 보존

별도의 `normalized_station_name`을 만들고 2025년 급속 행만 연간/월별로 집계했습니다. 원본명으로 집계하며 정규화 이름이 같다고 서로 다른 원본명을 합치지 않았습니다. 월 자료가 없거나 수치가 유효하지 않은 경우 값을 임의 생성하지 않습니다.

저장 위치:

- `data/runtime/analysis.sqlite`: D1 집계 및 `station_match`
- `data/runtime/analysis/d1-preprocessed.csv`: 원본 컬럼과 모든 행을 보존한 별도 전처리 파일
- `data/runtime/analysis/station-match-review.csv`: D1-D3 후보 검토표

## 매칭 정책과 실제 결과

`station_match`는 요청한 원본명/정규화명/statId/시설명/주소/status/method/confidence/review_note를 보유합니다. 정확한 정규화 이름과 이름 유사도(0.55 이상)를 이용해 서울 주소의 D3 후보를 최대 3개씩 생성합니다. 점수는 후보 정렬용이며 동일 시설 확률이 아닙니다.

이름이 완전히 같아도 자동 confirmed로 처리하지 않습니다. D1에는 주소·좌표·statId가 없으므로 시설대장, 실제 주소, 위치 등 독립 근거를 확인해야 합니다. 한 D1 시설 또는 한 D3 시설을 이중 confirmed로 등록하여 kWh를 중복 집계하지 못하도록 제약을 뒀습니다.

| 실제 데이터 상태 | 개수 |
|---|---:|
| confirmed | 0 |
| review | 187 |
| unmatched | 0 |
| 최종 핵심 분석대상 | 0 |

위 review 수는 후보 행 수가 아닌 **D1 고유 시설명 수**입니다. 후보가 존재한다는 뜻이지 187개 모두 동일 시설이라는 뜻은 아닙니다. 이름만으로 확정 수를 늘리지 않았습니다.

## API와 분석 범위

- `GET /api/analysis/stations`: confirmed + D1 급속 기록 + 유효한 서울 D3 설비가 있는 시설만 반환합니다.
- `GET /api/analysis/matches`: 실제 후보표와 상태별 시설 수를 반환합니다.
- `GET /api/analysis/stations/{statId}/alternatives?radius=500` 또는 `1000`: 선택 핵심 시설 주변의 다른 정상 급속 설비를 반환합니다.

핵심 응답에는 요청한 분석 ID, statId, 시설명, 주소, 좌표, 2025년 연간/월별 급속 kWh, 급속 설비 수 및 출력이 포함됩니다. 분류 미검증 또는 출력/상태를 계산할 수 없는 값은 `null`입니다. `classificationVerified=false`여도 confirmed 시설 자체를 API 미연결로 취급하지 않습니다.

전국 환경공단 76,163행은 삭제하지 않았습니다. 대체망은 자치구나 서울 경계로 자르지 않으며, 같은 statId·삭제 설비·제한 접근 설비를 제외합니다. 공식 검증된 급속 유형/정상 상태에 해당하는 설비만 사용합니다. 유형/상태 분류 미검증 시 `분류 검증 필요`, 상태가 오래됐으면 `최신 상태 확인 필요`를 반환하고 출력 합계를 추측하지 않습니다.

legacy 영향도/시뮬레이션은 핵심 시설만 대상과 KPI에 포함하며, 주변망은 `analysis_target=false`로 분리합니다. 기존 물리 설비/공유출력 등 분석 검증 조건은 유지하여, 시설 confirmed만으로 복구 점수를 임의 확정하지 않습니다. D2 세션의 급속 전용/관측일 근거가 없으면 계획정비 추천도 기존대로 보류됩니다.

## 검증

- Python **114개 테스트 통과**: 원본 중복·0 유지, 연도/급속 필터, 이름만으로 자동 confirmed 금지, 수동 확정의 유일성, null 계산, 삭제 설비 제외, 경계 밖 대체망, 같은 statId 제외, FastAPI 신규 라우트 통합 포함.
- JS 데이터 모델 **12개 테스트 통과**: 핵심 confirmed 필터, 구 필터, 핵심 검색, 잘못된 좌표 제외, API 연결/분류 독립성 포함.
- 격리 브라우저 테스트 통과: 전국 원자료를 메인 마커/검색에서 제외, 핵심 시설의 구 필터와 KPI, overview 실패 후 API/원자료 연결 상태 유지. 테스트 데이터는 브라우저에만 주입했으며 운영 DB에 넣지 않았습니다.
- 실제 D1와 실제 수집 DB를 **읽기 전용**으로 연 별도 FastAPI에서 system/status·chargers·analysis/stations 모두 HTTP 200, confirmed=0/review=187, 메인 마커=0, 검색 후보=0, 25개 구+전체 필터를 확인했습니다. 이는 실제 자료 검증이며 Mock 데이터가 아닙니다.

실제 8000번 서버에서는 신규 서비스 변수와 기존 HTML 함수의 이름 충돌을 발견해 수정했습니다. 통합 테스트로 수정 확인 후 일반 Windows PowerShell의 서버 재시작을 요청했습니다. 최종 8000번 브라우저 결과는 `reports/core-analysis-browser.json`의 `base` 및 HTTP 상태를 기준으로 구분합니다. 별도 검증 포트 결과를 8000번 배포 결과로 혼동하지 않습니다.

## 사용자가 제공/확인해야 할 자료

D1 엑셀은 이미 있습니다. 추가로 필요한 것은 **D1 시설명과 실제 주소·좌표·소유 시설대장 등을 연결하는 독립 확인 근거**입니다. 검토표에서 후보 주소 등을 확인한 뒤, 근거가 확인된 시설만 다음 명령으로 수동 확정할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe scripts\prepare_analysis.py --confirm-name "D1의 실제 충전소명" --stat-id "확인된 환경공단 statId" --evidence "주소·시설대장 출처 및 동일 시설 확인 근거"
```

위 명령은 사람이 실제 근거를 확인한 후 사용하는 도구이며, 예시 문자열을 그대로 실행해서는 안 됩니다. 이름 유사도만으로 확정하지 마세요. 후보 재생성은 `.\.venv\Scripts\python.exe scripts\prepare_analysis.py`이며 기존 confirmed는 보존합니다.

FastAPI 라우트 수정 반영:

```powershell
cd "C:\Users\SAMSUNG\OneDrive\바탕 화면\capstone_mid"
.\run-local.cmd --restart
```

정상 수집이 완료된 뒤 http://127.0.0.1:8000/ 를 Ctrl+F5로 새로고침하세요. 현재 confirmed가 0개이므로 핵심 지도도 0개가 정확한 결과입니다. 원자료 API 성공과 분류/매칭 준비 상태는 별도로 표시됩니다.

# 탭별 실제 데이터 연결 수정

웹사이트: http://127.0.0.1:8000/

## 최종 8000번 서버 확인

최종 브라우저 실행은 `stale=false`, 과거 관측 재현 OFF 상태로 통과했다. 실제 관측시각은 2026-10-17 13:16:41 KST다. JavaScript 런타임 오류 0건, 일반 새로고침 및 핵심시설 API 실패 격리 검증도 통과했다.

| 탭 | 실제 데이터 | 화면·상호작용 결과 |
|---|---|---|
| 운영현황 | 서울 70,121기 / 12,146개 시설 | KPI·지도·자치구·검색·Hover/Click 통과 |
| 복구우선순위 | 실제 복구후보 0기 / 잠재 영향순위 200기 | 빈 이유 안내, 순위표·D/Q/B·반경·가중치·행 지도 연결 통과 |
| 정비시간 | 분석가능 68개 시설 | 시설 선택·요일시간 히트맵·1시간/2시간 결과 통과 |
| 복구시뮬레이션 | 가정 73개 시설 186기 / 서울 단순 24개 시설 45기 | 모드·자치구·검색·설비 선택·Before/After·회복률·지도·누적 그래프 통과 |
| 데이터 품질 | 자동확정 81개 / 검토 106개 | 기술정보와 시설 검토 화면 표시 통과 |

최신 저장 관측으로 시나리오를 다시 호출해 충전기 원자료 fingerprint와 snapshot 건수가 호출 전후 동일함을 확인했다. 최종 시나리오 검사도 과거 재현 OFF다. 수집·원자료·기존 연구 산식은 유지했다.

## 데이터 흐름

| 탭 | API | 프론트 상태 / 의존성 |
|---|---|---|
| 운영현황 | `/api/chargers`, `/api/system/status` | `state.operations`만으로 지도·KPI·검색 생성. 핵심시설과 status 조회는 원자료 표시를 지연시키지 않음 |
| 운영현황 저장 관측 | `/api/operations/observations` | 최신 조회 실패/오래된 관측일 때만 명시된 시각의 실제 저장값 표시. 연결 성공으로 바꾸지 않음 |
| 복구우선순위 | `/api/analysis/overview?radius=...&weight=...&preview=...&replay=...` | 독립 priorities store. 실제 복구/잠재 영향순위 분리, 잠재순위 기본 표시 |
| 정비시간 | `/api/analysis/stations`, `/api/analysis/maintenance/{statId}` | 독립 maintenance store. 순위 계산·현재 운영상태 수집과 무관하게 D2 결과 표시 |
| 실제/가정 시뮬레이션 | `/api/analysis/overview`, POST `/api/analysis/simulate` | 독립 simulation store. 모드에 맞는 시설·충전기만 선택, 실제 대상 없음은 비활성화 |
| 서울 단순 시뮬레이션 | `/api/operations/stations?stopped_only=true`, POST `/api/operations/simulate` | 서울 실제 운영중지 설비만 선택. 현재 필터 시설의 정격출력 비교, D/Q/B 계산 없음 |
| 데이터 품질 | `/api/system/status`, `/api/analysis/quality`, `/api/analysis/matches` | 운영·분석 표시와 독립. 일부 API 실패 시 조회된 자료 유지 |

명확한 순위 응답이 필요한 외부 클라이언트에는 `/api/analysis/recovery-ranking`, `/api/analysis/potential-impact`가 `status/count/reason/items`를 제공한다. 웹은 기존 overview 계산을 재사용한다.

## 확인한 원인

- 운영현황 로딩이 핵심시설 조회 완료까지 대기했고 지도 캡션·일부 표시가 `state.base`에 의존했다.
- 실제 복구후보가 0인 목록을 기본 표시해 잠재 영향순위가 없는 것처럼 보였다.
- 분석 탭의 기존 공통 필터는 CSS로 숨겨졌지만 대체 필터가 없었다.
- 정비시간이 불필요하게 순위 overview를 기다리고 분석 보류 시설까지 기본 선택목록에 넣었다.
- 분석 탭들이 자치구·시설·복구 선택·Before/After 상태를 공유했다.
- 단순 서울 운영현황 시뮬레이션의 데이터 소스와 선택 경로가 없었다.
- JS/CSS/HTML에 명시적인 캐시 방지 응답이 없었다.

## 변경 범위

수집 코드, .env, API 키, 원자료, 시설매칭, D/Q/B·정비시간 산식, 기존 연구 시뮬레이션 산식은 변경하지 않았다.

- `apps/web/src/dashboard.js`: 독립 운영현황 로딩, 관측 KPI, 상태 구성, 적절한 로딩·오류·저장관측 표시.
- `apps/web/src/dashboard-model.js`: 명시적인 서울 전체 설비 표시 옵션, 저장 관측의 분류와 현재 상태 분리.
- `apps/web/src/research-tabs.js`: 탭별 상태, 독립 조회, 잠재순위, 정비시간 시설 선택, 시뮬레이션 세 모드.
- `apps/web/src/research-ui.js`: 기존 매칭 검토 유지, 품질자료 조회 실패 분리, 지도 생명주기 정리.
- `apps/web/src/style.css`: 탭 필터·선택 UI, 로딩 화면, 운영화면에서 분석 품질 필터 제외.
- `backend/app/main.py`: 읽기 전용 운영 관측·단순 시나리오 API, 순위 응답 wrapper, UI no-store 헤더.
- `backend/app/operational_view.py`: 실제 저장 관측의 서울 필터 및 원자료를 변경하지 않는 단순 정격출력 시나리오.
- `scripts/check-tab-runtime.mjs`: 8000번 실제 Chrome 브라우저 end-to-end 검사.
- `scripts/check_scenario_storage.py`: 실제 원자료/snapshot 불변 및 출력·회복률 검사.
- `scripts/check-research-workflow.mjs`: 기존 브라우저 검사 선택자를 새 모드 UI에 맞춤.
- `scripts/verify_analysis_server.py`: 읽기 전용 검증용 단순 시나리오 요청 허용.
- `tests/test_operational_view.py`: 선택 검증, 출력 보존, 원자료 불변, 명시적 과거관측 재현 검사.

## 검증 근거

- `reports/tab-runtime-verification.json`: 실제 localhost Chrome의 지도·필터·검색·순위·히트맵·전후 비교·일반 새로고침·core API 실패 격리·JS 오류 결과.
- `reports/tab-runtime-simulation.png`: 실제 데이터로 렌더링한 시뮬레이션 화면.
- `reports/scenario-storage-verification.json`: 원자료 및 snapshot 불변, 실제 출력 시나리오 계산 결과. 수집기가 별도로 실행 중이므로 수집에 의한 관측 갱신과 구분한다.
- Python 132개, Node 15개 검사 통과.

검증 스크립트는 현재 상태가 오래된 경우에만 과거 관측 재현을 명시적으로 선택한다. 해당 실행의 `stale` 및 `observationAt`은 JSON 보고서에 기록한다. 현재 수집 완료 후 재실행한 최종 결과를 우선한다.

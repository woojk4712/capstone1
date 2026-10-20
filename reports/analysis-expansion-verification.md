# 실제 분석 연결 및 시설 확정 확대

## 최초 실제 8000번 API 추적

원본 응답의 수치·오류 유형만 기록했다. API 키·응답 원문은 기록하지 않았다.

| API | HTTP | status | count / items | reason / 오류 |
|---|---:|---|---|---|
| `/api/system/status` | 200 | 필드 없음 | items 필드 없음 | ME connected=false, stale=true, connection_error |
| `/api/chargers` | 503 | error | items 필드 없음 | connection_error |
| `/api/analysis/stations` | 200 | 필드 없음 | 81 / 81 | 없음 |
| `/api/analysis/overview?radius=500` | 200 | 필드 없음 | 81 / 81 | stale=true, potential=0, priorities=0 |
| `/api/analysis/recovery-ranking` | 200 | ok(이전 응답 형식) | 0 / 0 | latest_observation_required |
| `/api/analysis/potential-impact` | 200 | ok(이전 응답 형식) | 0 / 0 | latest_observation_required |
| `/api/operations/stations?stopped_only=true` | 200 | 필드 없음 | 24 / 24 | 없음 |
| `/api/analysis/maintenance/SE000001` | 200 | READY | items 필드 없음 | 히트맵·1h/2h 응답 있음 |

원본 진단 메타데이터: `analysis-api-baseline.json`. **items 필드가 없는 응답은 실제 0건이라는 의미가 아니다.** 현재 수집 상태는 시간에 따라 변하므로 최종 응답을 별도로 확인한다.

## 원인 및 상태 처리

- 시설 81개가 고정된 것은 아니었다. DB 확정 상태와 파일 변경시각에 따라 핵심시설을 다시 계산하고 있었다.
- 최초 실행 서버에서는 최근 ME 연결 오류 때문에 `stale=true`였다. 기존 산식은 오래된 운영상태로 현재 Impact를 확정하지 않으므로 potential/priorities를 보류했다. 이 결과와 실제 운영중지 0개는 다른 상태다.
- 화면은 LOADING(요청 진행), EMPTY(성공·대상 없음), ERROR(요청 실패), STALE(최신 관측 필요)를 구분한다. STALE에서 저장 관측 분석은 명시적으로 선택하며 현재 상태로 표시하지 않는다.
- 실제 복구 대상이 0개일 때는 “현재 확인된 핵심 분석시설에는 운영중지 복구 대상이 없습니다.”로 안내한다. 잠재 영향순위, D2 정비시간, 가정 시나리오, 서울 단순 시나리오와 분리한다.
- 시나리오 모드 변경 시 자치구와 시설 검색을 초기화해 이전 소스의 필터가 새 소스를 숨기지 않게 했다. 선택 설비의 가상 상태를 상세정보에도 별도로 표시하며 원본 stat은 보존한다.
- no-store가 적용되어 있으며 service worker 파일은 없다.

## 공식 시설대장 기반 추가 검증

원본 충전소명·주소는 변경하지 않았다. 별도 물리 주소 키에서 서울/서울시/서울특별시, 괄호·상세주소, 도로명 내부 공백, 번호가 포함된 도로명을 처리했다. 도로명 주소와 지번은 임의로 서로 변환하지 않으며, 지하/지상 및 산 지번 구분을 보존한다.

자동확정 조건:

1. D1 명칭과 OA-21712 명칭 정확 정규화 일치, 공식 시설 후보 유일.
2. 공식 대장과 D3의 물리 주소 일치, 해당 이름·주소의 D3 후보 유일. D3 이름이 다르면 주소 후보 전체가 유일한 경우에만 허용.
3. 공식 시설 후보의 역방향 연결 유일성, D3 시설 경계 일관성 확인.
4. 충전기 ID 충돌 없음, 유효 좌표 존재, 같은 statId 설비 좌표가 150m 안에 일관됨.

시설 내 `1/2` 순번 ID를 전역 공통 ID로 간주하지 않았다. 이름 유사도 점수만으로 확정하지 않았다. 모든 확정 행에 match_method, match_evidence, confidence_reason을 저장한다. 직접 확인된 manual 확정 및 수동 보류는 재처리 시 보존한다.

| 지표 | 재검증 결과 |
|---|---:|
| D1 급속 기록 시설 | 187 |
| 기존 confirmed_auto | 81 |
| 추가 confirmed_auto | 19 |
| confirmed_manual | 0 |
| 최종 confirmed | 100 |
| review | 87 |
| unmatched | 0 |
| 시설 연결률 | 53.48% |
| 급속 kWh 연결률 | 54.04% |
| 설비 확인 시설 | 94 |
| D2 연결 시설 | 100 |
| 정비시간 분석가능 시설 | 84 |
| 1시간/2시간 후보 생성 | 각 84 |

확정 19개 근거: `matching-added-confirmations.json`. 이전 상태: `matching-before-reverification.json`.

남은 review 사유는 시설별로 중복 없이 집계했다.

| 사유 | 시설 |
|---|---:|
| 공식 시설대장에 D1과 정확히 연결할 명칭 없음 | 74 |
| 같은 명칭·물리 주소에 D3 statId 복수 | 12 |
| 지원하는 서울 물리 주소로 확인 불가 | 1 |

명칭 미일치에는 시설대장에 아예 없는 시설과 가로등 등 설비 위치를 구분하는 이름이 포함된다. 해당 구분을 임의로 제거하거나 다른 비슷한 주차장으로 연결하지 않는다. 복수 statId는 단순 로컬 충전기 순번으로 구별할 수 없어 공식 식별 근거 또는 수동 시설 확인이 필요하다.

## 동적 재계산 및 검증

한 번의 명령을 유지했다.

```powershell
.\.venv\Scripts\python.exe scripts\prepare_analysis.py --all
```

분석 대상에 81/100을 상수로 넣지 않았다. `/api/analysis/stations`가 서버 재시작 전에 실제로 81에서 100으로 증가함을 확인했다. API 계산 캐시는 분석 DB 변경시각에 따라 갱신한다. 열린 분석/품질 화면도 revision API를 10초 간격으로 확인해 변경 시 다시 읽는다.

데이터 품질 화면에 Funnel·정확/상한 Impact·제외/보류 사유를 추가했다. 사유 지표는 시설/설비 등 단위가 다르고 서로 중복될 수 있다. 접근 제한 속성은 별도 진단이며 기존 산식의 제외 조건을 임의로 바꾸지 않았다.

Python 138개, Node 15개 검사 통과. 실제 저장 자료를 사용하는 검증 서버에서 지도·검색·순위·히트맵·시뮬레이션·일반 새로고침 및 core API 실패 격리 검증을 통과했다. 8000번 최종 브라우저 결과는 `tab-runtime-verification.json`의 base/status/observationAt을 확인한다.

API 키·URL·환경공단 수집, D1/D2 원본, D/Q/B 및 정비시간 산식은 변경하지 않았다.

## 최종 8000번 실제 브라우저 결과

최종 실행은 `base=http://127.0.0.1:8000`, `stale=false`, 저장 관측 재현 OFF였다. 실제 관측시각은 2026-10-17 14:09:25 KST다. 최근 수집이 완료된 이후 최신 데이터로 검증했으며, 처음의 connection_error/collection_in_progress 상태와 구분한다.

| 지표 | 최신 관측 결과 |
|---|---:|
| core stat=4 | 0 |
| potential Impact | 231 |
| 정확 Impact | 20 |
| 상한검토 Impact | 211 |
| 서울 전체 stat=4 (삭제 제외) | 45 |
| 핵심시설 가정 시나리오 선택가능 | 92시설 / 218기 |
| 서울 실제 운영중지 단순 시나리오 | 24시설 / 45기 |
| 정비시간 선택가능 | 84시설 |

다섯 탭의 실제 지도·검색·필터·순위 행·1h/2h·시뮬레이션 전후·Funnel을 검증했다. 원자료를 그대로 다시 전처리하는 실제 명령 실행 후, 열린 브라우저가 revision 변경을 감지하여 재시작 없이 자동 갱신됨을 검증했다. 일반 새로고침, core API 실패 시 운영현황 유지도 통과했고 JavaScript 런타임 오류는 0건이다.

최종 API별 HTTP/status/count/reason/items 길이는 `analysis-api-final.md` 및 `analysis-api-final.json`에 저장했다. 최종 화면 검증은 `tab-runtime-verification.json`, 가상 시나리오의 원자료/snapshot 불변 검사는 `scenario-storage-verification.json`에 기록했다.

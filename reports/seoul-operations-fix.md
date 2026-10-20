# 서울 운영현황 표시 수정 결과

운영현황이 confirmed 핵심 분석시설과 같은 데이터를 사용하던 조건을 분리했습니다. D1-D3 confirmed=0은 분석시설 매칭 대기를 의미하며, 환경공단 API 실패를 의미하지 않습니다. 한전 상태는 운영현황의 표시·분류·분석 준비 판단에서 제외했습니다.

## 실제 브라우저 확인

실행 중인 `http://127.0.0.1:8000/`에서 실제 저장된 환경공단 데이터로 검증했습니다. 진단용 외부 API 요청을 추가 실행하지 않았고, API 키·URL·수집 코드·환경변수를 변경하지 않았습니다. 테스트에서는 외부 배경지도 타일만 차단했습니다. Leaflet의 실제 충전소 마커를 검사했습니다.

| 항목 | 결과 |
|---|---|
| `/api/system/status` | HTTP 200, 환경공단 연결됨 |
| `/api/chargers` | HTTP 200, 실제 원자료 |
| `/api/analysis/stations` | HTTP 200, confirmed 0개 |
| 전국 저장 충전기 | 76,163기 |
| 서울 표시 대상 | 70,121기 |
| 서울 statId 충전소 / 마커 | 12,146개 / 12,146개 |
| 강남구 필터 | 마커 995개, 검색목록도 해당 구 적용 |
| 마커 Hover / Click | 실제 이름 / 원본 필드 상세 표시 확인 |
| 분석시설 매칭 | confirmed 0 / review 187 / unmatched 0 |
| 복구 우선순위 지도 | confirmed 기준 0개, 매칭 준비 중 |
| 한전 | 운영화면 경고 없음, 품질 화면에 미사용 표시 |
| JavaScript 오류 | 없음 |

서울 표시 조건은 주소가 서울특별시로 시작하고 `delYn=N`이며 좌표가 유효한 실제 설비입니다. 같은 `statId`는 하나의 충전소로 묶습니다. **현재 70,121기는 급속만의 숫자가 아닙니다. 완속과 미분류 설비가 포함된 서울 원자료입니다.**

## 분류 검증의 한계

`classification_verified=false`를 유지했습니다. 사용자가 제공한 `https://apis.data.go.kr/B552584/EvCharger`는 서비스 기본 주소이며 코드표 원본이 아닙니다. [공식 API 안내](https://www.data.go.kr/data/15076352/openapi.do)에 안내된 가이드 v1.25의 코드표 본문을 확보하지 못해 급속 유형 및 상태 의미를 검증 완료로 바꾸지 않았습니다. 실제 데이터에는 유형 10·11, 상태 9도 있으므로 일부 코드만 추정해 전체 분류로 적용하지 않습니다.

검증 전에는 원본 `chgerType`, `stat`, `statUpdDt`를 상세에 표시하고 해석이 필요한 급속·상태별 수치에는 분류 검증 필요를 표시합니다. 검증 후에는 백엔드의 검증된 급속 대상 승인값을 이용하며 한전 코드를 참조하지 않습니다.

## 회귀 검증

- `node --test tests/dashboard-model.test.mjs tests/live-inventory.test.mjs`: 14개 통과
- `node scripts/check-core-fixtures.mjs`: 서울 운영현황과 D1 분리, 자치구 필터, 분류 독립, overview 오류 독립, 실제 화면 Mock 대체 금지 확인
- `node scripts/check-seoul-operations.mjs`: 실제 localhost API와 브라우저에서 위 결과 확인
- 결과: `reports/seoul-operations-browser.json`
- 화면: `reports/seoul-operations-live.png`

사용자는 기존 서버의 웹사이트에서 Ctrl+F5로 새로고침하면 됩니다. 환경공단 연결·원자료·서울 운영현황·D1 매칭·코드 분류는 별도의 상태로 표시됩니다.

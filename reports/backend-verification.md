# ?? ?? ?? (2026-10-16)

???? ??? ? API ??? ?? `.env`? ??????. ?? ????? ??? ??????. ?? ??? ? `ME_SERVICE_KEY`, `ME_URL`, `KEPCO_SERVICE_KEY`, `KEPCO_URL` ?? ???? ??????. ?? ?? ???? ?????.

- ????: `network_permission_denied`, HTTP ?? ??.
- ??: `schema_unverified`, ?? ????? ?? ????? ???.

?? ??? URL ?? ? ?? ?????.

---

# 외부 API 백엔드 검증 결과

검증일: 2026-10-16. 실제 키·설정된 API URL·응답 원문은 이 보고서에 포함하지 않았습니다. 루트 `.env` 내용은 변경하지 않았습니다.

| 단계 | 결과 | 근거와 제한 |
|---|---|---|
| 루트 `.env` 로딩 | 성공 | `ME_SERVICE_KEY`, `KEPCO_SERVICE_KEY` 존재. `ME_URL`, `KEPCO_URL` 없음 또는 빈 값. 값은 출력하지 않음 |
| 환경공단 공개 도메인 연결 진단 | 실패 | `network_permission_denied`. HTTP 응답 없음. DNS/SSL/timeout으로 오판하지 않음 |
| 환경공단 인증 API 실호출 | 미실행 | `ME_URL` 미설정. 승인 주소를 추측하거나 키를 다른 URL로 전송하지 않음 |
| 한전 API 실호출 | 미실행 | `KEPCO_URL` 미설정. 승인 요청·응답 스키마도 미검증 |
| JSON/XML 파싱 | 성공, 격리 테스트 | JSON과 XML 목록·인증 오류·빈 목록·잘못된 스키마 처리. 실응답 파싱 성공을 의미하지 않음 |
| `/api/chargers` 실제 HTTP 반환 | 정상 오류 처리 | 현재 실제 서버는 HTTP 503과 데이터 미수집 원인을 반환. 내부 서비스/격리 HTTP 테스트에서는 성공 200, 상세 200, 잘못된 반경 422 검증 |
| `/api/system/status` | 성공 | HTTP 200. 존재 여부 boolean, 연결 상태, 마지막 성공 시각, 건수만 반환. 런타임은 현재 `stdlib_fallback` |
| FastAPI HTTP 실행 | 미검증 | FastAPI/uvicorn/httpx 미설치, 패키지 확보 실패. FastAPI 전용 테스트 1개 skip. 호환 서버 결과를 FastAPI 결과로 간주하지 않음 |
| SQLite 상태 스냅샷 | 성공, 격리 테스트 | 상태 변경시각과 수집시각 구분, 원자적 전체 수집 반영, 실패 시 이전 성공 결과 보존 |
| 실제 Leaflet 마커·Hover·Click | 차단 | Leaflet 패키지 및 CDN 확보 실패, 실제 수집 목록 없음. 다른 라이브러리나 가짜 마커로 통과 처리하지 않음 |
| 상세 패널·반경 변경 | 성공, 브라우저 격리 응답 | 충전소 상세, 두 시각 표시, 1000m 조회 요청 검증. fixture는 브라우저에서만 사용하며 실제 DB에 쓰지 않음 |
| API 실패 UI | 성공, 실제 브라우저 | API 연결 실패, 데이터 미수집, 마지막 성공 수집 없음, 지도 라이브러리 연결 실패 표시. 자동 샘플 대체 없음 |
| 모바일·브라우저 실행 | 성공 | 가로 넘침 없음, JavaScript 런타임 오류 없음 |
| 키·URL 노출 검사 | 성공 | 백엔드·프론트·스크립트·보고서 텍스트와 실제 내부 API 응답 검사. 노출 0건. `.env`와 SQLite 웹 접근 HTTP 404 |

Python 테스트: **73개 통과 / 1개 skip / 실패 0개**. 기존 JS 모델 테스트 7개 통과. 새 브라우저 테스트 7개 통과, 실제 Leaflet 마커 테스트 1개 차단. React 프로덕션 빌드와 Docker 실행은 의존성을 확보하지 못해 검증하지 않았습니다.

검증 근거 파일: `live-ui-verification.json`, `live-security-verification.json`, `live-api-error.png`. 이전 보고서의 테스트 결과와 구분합니다.

## 구현 파일

- `backend/app/settings.py`: 루트 `.env` 전용 로딩, 값 없는 존재 여부 응답, 비밀값 필터링.
- `backend/app/services/transport.py`: 키 없는 도메인 진단용 전송, 안전한 오류 분류, 리다이렉트 차단, JSON/XML 처리.
- `backend/app/services/me_api.py`: 지정 필드만 변환, 서울 범위 페이지 수집, 완전성 검증, 미검증 분류 보류.
- `backend/app/services/kepco_api.py`: 승인 명세 기반 계약이 없으면 호출 차단.
- `backend/app/main.py`: 요청한 4개 FastAPI GET 경로, 백그라운드 수집, 명시적 정적 파일 허용 목록.
- `backend/app/storage.py`: SQLite `status_snapshots`, 현재 목록, 연결 상태, 검증된 설비 대응표.
- `apps/web/src/live-api.js`: 내부 API만 호출하는 Leaflet 지도·상세·연결 오류 UI.

## 로컬에서 실연동을 완료하는 데 필요한 설정

1. 루트 `.env`의 `ME_URL`, `KEPCO_URL`에 해당 키로 승인받은 API 주소를 저장합니다. 기존 키는 유지합니다.
2. 환경공단의 상태코드·급속 유형은 실제 응답과 승인 명세를 검토한 기존 `ME_STATUS_MAP`, `ME_FAST_TYPES`, `ME_MAPPING_VERIFIED` 설정으로 활성화합니다. 한전은 검토한 `KEPCO_CONTRACT` 및 설비 대응표가 필요합니다.
3. 네트워크 연결이 가능한 PC에서 `scripts/run_backend.ps1 -Install`로 FastAPI 의존성을 설치·실행합니다. React는 `npm install` 후 `npm run dev`로 실행합니다.
4. 서버 재시작 후 실제 인증 응답, Leaflet 마커, FastAPI HTTP 테스트를 다시 실행합니다. 현재 데이터 성공 수집 건수는 0건이고 마지막 성공 수집은 없습니다.

자세한 실행·계약 설정은 [백엔드 설명](../backend/README.md)을 확인하세요. [환경공단 공식 명세](https://www.data.go.kr/data/15076352/openapi.do)는 오류코드·페이지 변수와 `statUpdDt`의 의미를 확인하는 데 사용했습니다. 이번 작업에서는 인증 응답과 가이드 본문을 확보하지 못해 숫자 상태코드의 의미를 임의 확정하지 않았습니다.

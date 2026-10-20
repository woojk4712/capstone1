# Windows 로컬 API 최종 실행 점검

코드·격리 테스트와 사용자 로컬의 실제 API 인증 결과를 구분한 기록입니다. 이번 작업에서는 Agent/Sandbox에서 환경공단·한전 외부 API를 호출하지 않았으며, sandbox 네트워크 권한 오류를 사용자 로컬 API 실패로 판정하지 않았습니다.

| 항목 | 결과 |
|---|---|
| .venv 사용 | run-local.cmd가 프로젝트 .venv만 사용. 파일 없음/패키지 누락 시 명시적 오류 |
| 실제 FastAPI 실행 | 설치된 .venv에서 FastAPI HTTP 실행 검증. 다른 서버로 자동 fallback 없음 |
| collection_enabled | 기본 실행 true. --preview 또는 --no-collect를 명시한 경우에만 false |
| 환경공단 환경변수 | ME_SERVICE_KEY, ME_URL, ME_STATUS_URL configured 확인 |
| 한전 환경변수 | KEPCO_SERVICE_KEY, KEPCO_URL configured 확인 |
| 환경공단 수집 시작 | 기본 lifespan에서 즉시 수집 시작. 주입 응답으로 목록+상태 호출 검증, 실제 인증 호출은 사용자 Windows 실행 후 확인 |
| /api/chargers | 실제 저장 데이터 200 경로 검증. 실패 503과 status/source/error_type 세 필드만 반환 |
| SQLite | 상태 코드/출력/api_updated_at/collected_at 저장 및 원자적 반영 검증 |
| 지도 연결 | /api/chargers의 실제 좌표를 기존 지도에 전달. 좌표 없음/실패 시 가짜 위치 생성 없음. 실제 Leaflet·제공기관 데이터 확인은 사용자 실행 후 수행 |
| 한전 교차검증 | 미검증 상태 유지. 환경공단 수집과 독립 |
| 사용자 명령 | cd 프로젝트 → .\run-local.cmd → 브라우저 3개 주소 확인 |

## 단순화한 사용자 실행

1. Windows PowerShell에서 프로젝트 이동:

   ```powershell
   cd "C:\Users\SAMSUNG\OneDrive\바탕 화면\capstone_mid"
   ```

2. 기본 실제 수집 서버 실행:

   ```powershell
   .\run-local.cmd
   ```

3. 브라우저에서 확인:

   - http://127.0.0.1:8000/api/system/status
   - http://127.0.0.1:8000/api/chargers
   - http://127.0.0.1:8000/

기존에 관리 중인 미리보기 서버가 있으면 PID와 instance token을 검증한 뒤 실제 수집 서버로 교체합니다. 다른 프로세스는 임의 종료하지 않습니다. 미리보기/수집 끄기는 `run-local.cmd --preview` 또는 `run-local.cmd --no-collect`를 명시해야 합니다. 기본 실행에는 이 옵션을 넣지 않습니다.

실행기는 새 서버의 runtime=fastapi, uses_project_venv=true, collection_enabled=true를 재확인한 뒤에만 기본 실행 성공 메시지를 표시합니다. 검증하지 못하거나 다른 서버가 포트를 점유하면 명시적으로 실패합니다. 키 값, 요청 URL, 응답 원문을 출력하지 않습니다.

## 상태 응답과 데이터 처리

`/api/system/status`는 environment의 다섯 configured boolean, collection_started_at, last_me_success_at, last_kepco_success_at, stored_charger_count, recent_errors, collecting을 제공합니다. 서비스키 실제 값은 포함하지 않습니다.

첫 수집 중 아직 데이터가 없으면 /api/chargers는 HTTP 503과 collection_in_progress를 반환합니다. 성공 후 실제 목록은 items(검증된 급속)와 unclassified_items(분류 검증 대기 실제 목록)에 들어갑니다. 최신 코드표 검증 없이 상태·급속 분류를 확정하지 않습니다. 웹은 첫 성공 결과를 자동 갱신하며 사용자가 선택한 시뮬레이션의 기존 기준은 보존합니다.

환경공단 정보/상태 API를 requests params로 호출하고, 실제로 제공된 필드만 결합합니다. 한전 응답 필드·상태 매핑을 추측하지 않습니다. 한전 미검증 시 웹에 `한전 교차검증: 미검증`을 표시합니다.

## 검증 범위

- Python 90개 통과: FastAPI 기본 lifespan의 collection_enabled=true, 시작 직후 목록·상태 조회, 임시 SQLite 저장, 실제 HTTP 200/503 경로, 한전 독립성, 명시적 preview의 외부 호출 없음 검증.
- JS 모델 8개 통과: 기존 분석/검색/필터와 /api/chargers 좌표 연결, 좌표 결측 시 마커 누락 검증.
- 브라우저 17개 검사: 기존 UI·명시적 DEMO·필터·검색·지도 Hover/Click·시뮬레이션·오류 UI·모바일 회귀 검사. 실제 Leaflet 외부 리소스 및 실제 제공기관 응답은 로컬 후속 확인 대상.
- Agent에서 검증용 서버는 명시적으로 --preview로 실행했습니다. 이 서버의 false 값을 기본 실행 결과로 보고하지 않습니다. 사용자의 위 3단계가 실제 수집 모드 전환입니다.

로컬 개별 진단 스크립트 test_me_api.py/test_kepco_api.py는 유지했습니다. 환경공단 성공 출력은 HTTP STATUS, resultCode, resultMsg, totalCount, item 개수, 첫 item 필드명만 포함합니다.

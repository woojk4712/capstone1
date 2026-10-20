# FastAPI 수집 시작 및 현재/과거 상태 분리

## 확인된 원인

기존 `last_attempt_at`은 요청 직전이 아니라 전체 수집의 성공/실패 처리 후 저장되었습니다. 따라서 새 `collection_started_at`과 오래된 `last_attempt_at`이 함께 보이는 것만으로 HTTP 요청이 없었다고 단정할 수는 없었습니다. 수집 대기 또는 진행 중에도 SQLite의 과거 `network_permission_denied`가 현재 오류처럼 반환되는 문제는 확인했습니다.

기존 lifespan은 `collect=True`일 때 즉시 `asyncio.to_thread(external.refresh)`를 실행하는 구조였습니다. 이 흐름을 유지하면서 실제 요청 시작 시각, 단계 및 실행 결과를 관측할 수 있도록 수정했습니다.

## 변경

- lifespan에서 `reset_runtime()`을 먼저 실행합니다. 과거 오류와 요청 시각은 provider의 `history` 및 `previous_error`로 분리합니다. 새 실행의 `connected=false`, `current_error=null`, `last_attempt_at=null`, `stage=pending`으로 시작합니다. 과거 성공 수집시각과 충전기/snapshot 데이터는 삭제하지 않습니다.
- 첫 수집 작업은 기존처럼 즉시 시작합니다. `collect_me()`가 수집 시작 시각을 기록하고, 실제 요청 함수 진입 직전에 `last_attempt_at`을 저장합니다. 요청 완료 때 이 시각을 완료 시각으로 덮어쓰지 않습니다.
- `/api/system/status`에 `last_me_attempt_at`, `collection_revision=2`를 추가했습니다. `providers.ME`에는 현재 `connected`, `last_attempt_at`, `last_success_at`, `current_error`, `stage`와 과거 `previous_error`, `history`가 구분됩니다. 기존 `error`는 현재 오류를 나타내는 호환 필드입니다.
- `POST /api/admin/collect/me`는 스케줄 주기를 기다리지 않고 ME 수집을 실행하고 완료 결과를 반환합니다. 이미 ME 수집이 진행 중이면 데이터 충돌 방지를 위해 해당 작업이 끝난 후 순서대로 실행합니다. 한전은 이 endpoint에서 호출하지 않습니다.
- `backend/app/services/me_api.py::fetch_me_chargers()`로 요청·JSON/XML 파싱을 통합했습니다. FastAPI의 전체 페이지 수집과 `scripts/test_me_api.py`가 같은 함수를 사용합니다. 로컬 테스트는 기존 10행 첫 페이지, 백엔드는 기존 서울 범위의 전체 페이지 및 상태 병합을 유지합니다. 단일 페이지 테스트 성공이 전체 페이지 수집 완료를 대신하지는 않습니다.
- 요청/응답/파싱/건수/DB 저장/완료 및 실패 단계를 안전한 로그로 남깁니다. 예외 원문, URL, 키 또는 실제 행 데이터는 로그에 쓰지 않습니다. Launcher의 서버 로그 파일은 `data/runtime/server.stderr.log`입니다.
- `run-local.cmd`는 이전 수집 구현(`collection_revision<2`)의 관리 서버도 PID/instance 검증 후 교체합니다. 임의의 다른 서버는 종료하지 않습니다.
- 웹사이트 및 분석 모델, API 키·URL·매핑 설정은 변경하지 않았습니다.

## 검증

아래 검증은 실제 외부 호출 없이 임시 DB와 주입 응답으로 수행했습니다. 운영 DB에 테스트 데이터를 넣지 않았습니다.

| 확인 | 결과 |
|---|---|
| 새 lifespan이 ME 요청 함수에 진입 | 통과 |
| 응답 대기 중에도 `collection_started_at < last_attempt_at` | 통과 |
| 과거 권한 오류가 current에서 사라지고 history에 보존 | 통과 |
| 수집 성공 시 성공 시각·SQLite 건수 갱신 | 통과 |
| `/api/chargers` HTTP 200 및 충전기 반환 | 통과 (주입 응답) |
| 수동 수집이 scheduler 없이 실행 | 통과 |
| 테스트 스크립트와 수동 수집의 공통 함수 사용 | 통과 |
| request/database 실패 단계와 안전한 로그·응답 | 통과 |
| 전체 Python 테스트 | 107개 통과 |

실제 Windows API 수집 결과는 수정된 서버를 일반 Windows PowerShell에서 다시 실행한 뒤 확인해야 합니다. 이번 작업에서는 외부 네트워크/키/DNS 진단을 다시 수행하지 않았습니다.

## 사용자 실행

```powershell
cd "C:\Users\SAMSUNG\OneDrive\바탕 화면\capstone_mid"
.\run-local.cmd
```

상태: http://127.0.0.1:8000/api/system/status

`collection_revision=2`인지 먼저 확인한 후 `last_me_attempt_at`, `providers.ME.stage`, `providers.ME.current_error`, `last_me_success_at`, `stored_charger_count`를 확인합니다. 초기 수집 중에는 HTTP 503 `collection_in_progress`가 정상이며, 수집 완료 후 `/api/chargers`가 HTTP 200이어야 합니다.

수동 ME 수집 (완료까지 대기):

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/admin/collect/me" | Select-Object status,fetched,stored,collected_at,stage,error_type,message
```

이 endpoint는 개발용입니다. 서버는 기존대로 `127.0.0.1`에 바인딩하며, 브라우저의 다른 Origin에서 보낸 수집 요청은 거부합니다.

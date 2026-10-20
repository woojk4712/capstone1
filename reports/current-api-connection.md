# 현재 환경공단 연결 점검

데이터가 없던 직접 원인은 실행 중인 서버가 `collection_enabled=false`인 미리보기 모드였기 때문입니다. 루트 `.env`의 필수 환경변수 5개는 모두 인식됩니다. 키 값은 출력하거나 보고서에 저장하지 않았습니다.

수집 모드 FastAPI로 교체하여 요청을 시작했으나, Agent에서 시작한 현재 프로세스는 외부 연결 권한 제한(`network_permission_denied`)을 받았습니다. 외부 HTTP 상태코드는 없습니다. 따라서 인증키의 유효성이나 사용자의 일반 Windows 터미널에서의 API 성공 여부는 아직 판단할 수 없습니다. 현재 `/api/chargers`는 HTTP 503과 오류 유형만 반환합니다.

## 수정 사항

- `run-local.cmd`는 프로젝트 `.venv`의 FastAPI 수집 서버를 기본 실행합니다.
- 이미 수집 모드여도 환경공단 오류가 `network_permission_denied`이면 기존 관리 서버를 교체합니다. 사용자가 일반 Windows 터미널에서 실행할 때 Agent의 제한을 가진 서버를 그대로 재사용하던 문제를 수정했습니다. PID와 instance token이 모두 일치해야 종료합니다.
- 주 화면의 한전 미검증 배너와 미연동 한전 품질 카드를 숨겼습니다. 별도 지도 화면에서도 미연동 카드와 미검증 상세 항목을 숨겼습니다. 백엔드 진단 상태와 실제 검증 결과는 유지합니다.
- 주 화면에 네트워크 제한 원인과 일반 Windows 터미널에서 실행할 명령을 안내합니다.
- 외부 호출 실패 시 실제 데이터와 마커를 만들거나 Mock으로 자동 대체하지 않습니다.

## 확인 결과

| 항목 | 결과 |
|---|---|
| 루트 `.env` 및 필수 환경변수 5개 | 모두 인식 |
| 프로젝트 `.venv` / FastAPI | 실행 확인 |
| `collection_enabled` | `true` |
| 환경공단 수집 시도 | 시작 확인 |
| 현재 프로세스의 외부 요청 | `network_permission_denied`, 외부 HTTP 응답 없음 |
| `/api/chargers` | HTTP 503, 실제 데이터 미수집 |
| SQLite | 저장 코드 및 주입 응답 기반 수집 테스트 통과; 실제 관측 저장은 미완료 |
| 한전 미검증 UI | 주 화면·품질 탭·별도 지도에서 숨김 확인 |
| 실패 시 가짜 마커 방지 | 브라우저 확인 통과 |
| Python 테스트 | 92개 통과 |
| 데이터 모델 테스트 | 8개 통과 |

## 사용자 실행

Agent 명령창이 아닌 **일반 Windows PowerShell**에서 아래를 실행하세요. 별도의 키 입력이나 수정은 필요 없습니다.

```powershell
cd "C:\Users\SAMSUNG\OneDrive\바탕 화면\capstone_mid"
.\run-local.cmd
```

현재 제한된 관리 서버는 자동 교체됩니다. 이후 http://127.0.0.1:8000/api/system/status 에서 `last_me_success_at`, `stored_charger_count`, `recent_errors.ME`를 확인하세요. 첫 수집이 끝나면 웹 화면은 자동으로 다시 조회합니다.

사이트: http://127.0.0.1:8000/

실제 응답: http://127.0.0.1:8000/api/chargers

일반 Windows에서 새로 시작한 뒤에도 실패하면 해당 프로세스의 오류 유형을 기준으로 DNS/SSL/timeout/인증/파라미터 등을 구분해야 합니다. 현재 Agent의 권한 오류만으로 사용자의 키나 로컬 네트워크가 잘못되었다고 결론 내릴 수 없습니다.

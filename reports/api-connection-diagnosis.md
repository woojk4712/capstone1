# API 미연결 원인과 조치

## 확인된 원인

1. 루트 `.env`의 ME_SERVICE_KEY, ME_URL, ME_STATUS_URL, KEPCO_SERVICE_KEY, KEPCO_URL은 모두 정상 인식됐습니다. 이번 미연결을 키 누락이나 로더 실패로 설명할 수 없습니다.
2. 8000번 서버의 실제 runtime은 `stdlib_preview_no_external_calls`, collecting=false, 성공 수집 없음이었습니다. 앞선 웹 화면 복구 과정에서 `--no-collect`로 실행했으므로 `.env`를 저장해도 외부 API 요청 자체가 시작되지 않았습니다.
3. 해당 서버의 내장 Python에는 fastapi/uvicorn/requests/python-dotenv가 설치되지 않았고 프로젝트 `.venv`도 없었습니다. 기존 실행기는 이 상태를 미리보기 서버로 조용히 대체했습니다.
4. 한전의 요청 예시(apiKey, metroCd, cityCd, returnType)는 반영되어 있지만 실제 응답 필드와 상태 의미는 미검증입니다. 이 문제는 환경공단 수집을 막지 않습니다.

## 해결한 부분

- Windows pip 캐시에 있는 Python 3.12 호환 wheel을 프로젝트의 `.runtime/wheels`로 복사하고 `.venv`를 생성했습니다. 인터넷 다운로드 없이 FastAPI, uvicorn, requests, python-dotenv, httpx 및 의존성을 설치했습니다.
- `.venv`의 `pip check`가 통과했습니다. FastAPI HTTP 테스트와 실행기 프로세스 관리 검사를 포함한 Python 테스트 **88개 모두 통과**했습니다. 이전에 skip했던 FastAPI 테스트도 실행했습니다.
- `run-local.cmd`는 프로젝트 `.venv`를 우선 사용합니다. `start_local.py`도 잘못된 Python으로 시작하면 `.venv`를 선택합니다.
- 기본 실행은 실제 FastAPI 수집 모드입니다. 패키지가 없을 때 미리보기로 조용히 대체하지 않고 설치 필요를 알립니다. 미리보기는 `--preview`를 명시해야 실행됩니다.
- 실행기가 직접 띄운 미리보기 서버는 PID와 서버 인스턴스 ID가 일치할 때만 종료하고 실제 API 서버로 교체합니다. 다른 서버나 오래된 PID 기록으로 프로세스를 종료하지 않도록 검사합니다.
- Windows 가상환경 실행기가 별도 Python 프로세스로 넘기는 경우 런처 PID와 서버 PID가 다른 점도 처리했습니다. 실행 시 전달한 인스턴스 토큰과 실제 서버 PID를 확인한 관리 기록이 저장되며, 현재 서버의 재시작 준비 상태도 확인했습니다.
- `/api/system/status`에 collection_enabled를 추가하고 웹 화면에도 미리보기에서 수집이 꺼져 있음을 명시했습니다.

## 현재 상태와 사용자 실행

현재 8000번은 설치된 `.venv`의 **실제 FastAPI**로 실행되며 `/`, `/docs`가 HTTP 200입니다. 다섯 환경변수는 모두 configured입니다. 다만 사용자의 이전 요청에 따라 Agent에서는 외부 API를 호출하지 않도록 collection_enabled=false로 실행했습니다. 이는 로컬 API 인증 실패라는 뜻이 아닙니다.

사용자의 Windows에서 프로젝트 폴더의 **run-local.cmd를 한 번 실행**하면 실행기가 현재의 관리 중인 미리보기를 실제 API 수집 서버로 교체합니다. 추가 pip 설치는 필요하지 않습니다. 서버가 뜨면 첫 전체 수집이 완료될 때까지 기다린 뒤 새로고침합니다.

```powershell
cd "C:\Users\SAMSUNG\OneDrive\바탕 화면\capstone_mid"
.\run-local.cmd
```

웹사이트: http://127.0.0.1:8000/

수집 상태: http://127.0.0.1:8000/api/system/status

실제 목록: http://127.0.0.1:8000/api/chargers

로컬 실행 후에도 수집 오류가 나오면 현재 설치된 같은 Python으로 다음을 실행하면 키 없이 HTTP/인증/요청/파싱 오류를 구분할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe scripts\test_me_api.py
.\.venv\Scripts\python.exe scripts\test_kepco_api.py
```

이번 조치에서 실제 API 인증 성공을 주장하지 않습니다. 이전 sandbox 네트워크 제한을 사용자 로컬 API 실패로 판정하지 않았고, 응답 필드·상태 매핑을 추측하거나 Mock 데이터로 대체하지 않았습니다. 서비스키 값은 출력·변경하지 않았습니다.

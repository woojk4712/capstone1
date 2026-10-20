# Windows 로컬 실연동 준비 결과

이번 작업에서는 Agent/Sandbox에서 환경공단·한전 API를 호출하지 않았습니다. 이전 sandbox의 network_permission_denied 기록으로 사용자 로컬 API 성공/실패를 판정하지 않습니다. 실제 인증 호출은 사용자 Windows PowerShell에서 실행하는 두 스크립트와 FastAPI가 수행합니다.

| 확인 항목 | 결과 |
|---|---|
| 실제 루트 `.env` 인식 | 확인. pathlib 절대경로, 실행 위치 독립 |
| ME_SERVICE_KEY | configured |
| ME_URL | configured |
| ME_STATUS_URL | configured. 사용자 제공 공식 상태 URL 추가 |
| KEPCO_SERVICE_KEY | configured |
| KEPCO_URL | configured. 사용자 입력값 유지 |
| 환경공단 로컬 테스트 | scripts/test_me_api.py 생성. requests params, 키 자동 디코딩/출력 없음 |
| 한전 로컬 테스트 | scripts/test_kepco_api.py 생성. 사용자 요청 예시의 apiKey/metroCd/cityCd/returnType 사용 |
| FastAPI 실제 실행 | 실행 코드·backend/requirements.txt 준비. 사용자 로컬 패키지 설치 및 실행 확인 대기 |
| /api/chargers 연동 | 실제 수집→SQLite→JSON 경로 준비. 실패 시 503, mock 대체 없음. 로컬 실응답 확인 대기 |
| SQLite snapshot | 원자적 수집 저장과 api_updated_at/collected_at 구분 테스트 통과 |
| 로컬 실행 명령 | 아래 5단계 |
| 원래 UI 복원 | `/`와 React 진입점을 사이드바·KPI·5개 탭·지도/상세가 있는 기존 디자인으로 복원. 1차 기능 수정 유지 |

키 값과 설정된 API 주소는 보고서·코드·로그·화면에 출력하지 않았습니다. 기존 키와 한전 주소를 유지하고 상태 조회 주소만 추가했습니다. 공백/NBSP/제로폭 공백을 정리하여 로드합니다. 퍼센트 인코딩된 인증키 문자열은 자동 변환하지 않습니다.

## 검증한 범위

- Python: **82개 통과, FastAPI HTTP 테스트 1개 skip**. 스크립트에 주입한 JSON/XML 응답, 키 비출력, 요청 params 유지, 상태 조회 결합, 오류 분류, SQLite 저장, 기존 분석 모델 연결을 검사했습니다.
- JS 모델: **7개 통과**. 기존 필터·검색·범위·시뮬레이션 로직을 유지했습니다.
- 기존 UI: **17개 통과**. 외부 호출을 끈 미리보기 서버와 외부 리소스를 차단한 브라우저로 원래 레이아웃·검색·KPI·지도 조작·Hover·상세·시뮬레이션·모바일·오류 UI를 확인했습니다. 명시적 sample 선택 시 `DEMO / MOCK DATA` 표시를 확인했습니다.
- 실제 API 키를 사용하는 호출은 수행하지 않았습니다. FastAPI/requests/python-dotenv는 Agent 환경에 미설치이며 여기서 설치/접속을 반복하지 않았습니다.
- 실제 Leaflet 라이브러리의 외부 타일·실데이터 마커 및 React 프로덕션 빌드는 사용자 로컬 의존성 설치 후 확인해야 합니다. 이번 UI 검사는 기존 SVG 지도 어댑터를 사용했습니다. 임의 라이브러리로 Leaflet 성공을 가장하지 않았습니다.

## 남겨둔 검증 경계

환경공단의 최신 공식 가이드 전체와 실제 응답이 확인되기 전까지 ME_MAPPING_VERIFIED를 true로 바꾸지 않았습니다. ME_STATUS_MAP/ME_FAST_TYPES도 추측해 설정하지 않았습니다. 첫 성공 응답에서 실제 필드명과 누락 필드만 data/runtime/me-schema.json에 기록합니다. `addrDetail`, `method`를 포함한 지정 필드 중 실제 존재하는 필드만 저장합니다. 분류 검증 전 API JSON의 unclassified_items에 실제 수집 목록을 제공하고 지도는 상태 불확실로 표시합니다. 분석용 급속 목록 items는 검증된 유형만 포함합니다. 기존 D1/D2 매칭·물리 설비·공유출력 검증 기준도 유지했습니다.

한전 요청은 사용자 제공 예시를 근거로 첫 응답 검사를 활성화했습니다. 공식 매뉴얼 전체, 파라미터 필수 여부, pagination은 아직 확인되지 않았으므로 이를 추측해 선언하지 않았습니다. 실제 응답 필드와 상태 의미는 첫 로컬 응답 후에만 검토합니다. KEPCO_FIELD_MAP/KEPCO_STATUS_MAP은 작성하지 않았습니다. 한전 상태 미검증은 환경공단과 D1/D2 분석을 중단하지 않습니다.

## 사용자 Windows 실행: 최대 5단계

1. 프로젝트로 이동하고 의존성 설치:

   ```powershell
   cd "C:\Users\SAMSUNG\OneDrive\바탕 화면\capstone_mid"
   python -m pip install -r backend\requirements.txt
   ```

2. 실제 `.env` 존재 여부 검사:

   ```powershell
   python scripts\check_env.py
   ```

3. 환경공단 1회 로컬 호출:

   ```powershell
   python scripts\test_me_api.py
   ```

4. 한전 1회 로컬 호출:

   ```powershell
   python scripts\test_kepco_api.py
   ```

5. FastAPI 실행:

   ```powershell
   python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --no-access-log
   ```

실행 후 http://127.0.0.1:8000/api/chargers 와 http://127.0.0.1:8000/ 를 확인합니다. 서버가 시작되면 백그라운드 수집이 먼저 진행되므로 완료 후 새로고침하세요. 한전 로컬 테스트가 실패하거나 응답 매핑이 미검증이어도 5단계를 실행할 수 있습니다. `python` 명령이 없는 PC에는 Python 3.12 이상을 PATH에 설치해야 합니다. 기존 Python 자동 탐색 경로는 backend/README.md에 설명했습니다.

복원 UI 미리보기: http://127.0.0.1:8001/ . 이 서버는 `--no-collect`로 실행했고 실제 외부 API를 호출하지 않습니다. 사용자 FastAPI가 사용할 8000번 포트를 점유하지 않습니다.

명세 확인 근거는 [제공기관 검토 기록](../docs/provider-verification.md), 실행·설계 설명은 [백엔드 README](../backend/README.md)에 있습니다.

# Render 배포 준비 검증

2026-10-21. 실제 Render 서비스/HTTPS URL은 아직 생성·검증하지 않았습니다.

## 진단과 선택

- 업로드 저장소 로컬 main은 d915ee1(기존 GitHub README 이력 병합)입니다. GitHub 페이지는 조회했으나 이 환경의 Git HTTPS fetch는 차단되어 원격 최신 SHA를 재확인하지 못했습니다. 해당 기존 이력을 보존한 저장소에 배포 준비 commit을 추가합니다.
- 기본 앱은 backend.app.main:app, services.main:app은 호환 진입점이며 FastAPI가 HTML/JS/CSS/Leaflet과 API를 함께 제공합니다. production UI의 localhost 하드코딩은 없습니다.
- 기존 설정은 .env 전용이어서 Render Dashboard 환경변수를 읽는 명시적 Render 모드만 추가했습니다. 로컬 .env 우선 동작과 Windows 실행기는 그대로입니다.
- runtime은 없는 상태에서 디렉터리/SQLite 스키마를 생성합니다. 정적 서울시 실적은 ME 재수집으로 복원되지 않으므로 방법 A(파생 seed)를 선택했습니다. 무료 DB 손실 후에도 정적 입력을 복원하고 실제 수집 후 원래 매칭/분석을 다시 실행합니다.
- data/seed 약 3.51 MiB: D1 수요 187개, 공식 시설 188개, D2 215,532행. 키·실관측·수동 확정·원본 raw body가 없습니다. 서버 상태나 과거 관측을 현재 데이터로 위장하지 않습니다.
- paid Persistent Disk 경로를 선택할 수 있도록 모든 앱 SQLite의 runtime 경로를 Render 모드에서 지정 가능하게 했습니다. 유료 리소스를 생성하지 않았으며 Postgres 이전은 수행하지 않았습니다.

## 수행한 검증

- Python 전체 회귀 테스트: 157개 통과 (기존 152 + Render 5).
- Node 모델 테스트: 15개 통과.
- raw 원자료 → seed 복원 후 D1 수요 테이블, D2 계산 필드 전 행, 공식 시설 근거, D1 시설 유형 이력의 동일성 PASS. 기존 원자료·기존 운영 DB를 수정하지 않는 임시 DB에서 검사했습니다.
- seed 복원 로컬 소요 약 2.08초. 원자료를 다시 파싱하는 export는 약 19.89초였으며 Render 시작 때 export를 수행하지 않습니다.
- 원본 없는 빈 runtime에서 health/UI/정적 asset/시스템 상태/연구 시설 목록 200, 키·관측이 없을 때 chargers 503, seedReady=true 확인. API 미준비와 프로세스 health를 분리했습니다.
- 환경변수 opt-in, legacy 환경변수 로더의 키 보존, seed 해시 오류 차단, 재기동 시 manual 검토 보존 확인.
- synthetic 운영 관측의 수집 성공 후 원래 매칭 호출, 실제 seed D2 정비 후보, D/Q/B·복구 시뮬레이션 정격출력 보존을 확인했습니다. 실제 제공기관 연결 성공을 의미하지 않습니다.
- 실제 headless Chrome + 격리 FastAPI/임시 DB에서 지도 DOM, 검색, 복구순위, 정비 히트맵, Before/After 시뮬레이션, 품질 탭 확인. JS runtime error 0, 내부 HTTP 오류 0. 테스트에서 외부 지도 타일·Google font는 차단했습니다.
- run-local.cmd, API collector/분류 모듈, research.py·operational_recovery.py·operational_view.py, UI 소스 변경 없음. 변경한 공유 파일은 설정/경로/앱 팩토리 주입/health 추가에 한정됩니다.

## 공개 후 반드시 남은 검사

Render 실제 build/install, API 인증·네트워크·재수집 완료 시간, 실제 데이터의 512MB 메모리 적합성, 외부 OSM 타일, HTTPS Origin 시뮬레이션, cold start를 확인해야 합니다. 이전 로컬 저장 관측은 76,163기였으므로 무료 메모리 충분성을 주장하지 않습니다. API가 재기동 중 실패하면 최신 운영현황과 연결된 연구시설이 준비되지 않을 수 있습니다. 안정적인 발표가 필요하면 paid 메모리/디스크를 실제 데이터 규모에 맞춰 선택합니다.

/health만 성공한 것은 배포 기능 전체의 성공이 아닙니다. `scripts/verify_render_url.py` 및 docs/RENDER_DEPLOYMENT.md의 브라우저 절차를 수행해야 합니다.

# 공개 준비 검증 (2026-10-20)

## 수행 결과

- 원자료 3개 SHA-256 검증 통과. 파일을 수정하지 않았습니다.
- Python unittest 전체 152개 통과 (기존 149개 + 공개 서버 검증 3개).
- Node 모델 테스트 15개 통과.
- 공개 앱의 화면·정적 JS·Leaflet·health 응답 200 확인 (격리 TestClient).
- 공개 앱의 수동 수집·시설 검토 저장·legacy 변경 403 확인.
- 외부 클라이언트의 시뮬레이션은 지정된 Origin에서만 허용하며 누락·타 출처 요청은 403 확인.
- Git 업로드 후보에서 실제 로컬 .env의 키/토큰/암호 값 일치 0건. .env·runtime SQLite·캐시·가상환경 제외 확인.

## 아직 확인하지 못한 항목

- npm 설치는 외부 네트워크 제한으로 완료하지 못했습니다. 오프라인 재시도도 @playwright/test 캐시 부재(ENOTCACHED)로 실패했습니다. 따라서 React/Vite production build는 이번 환경에서 미검증입니다. 기본 FastAPI HTML/JS 제공 경로는 npm 없이 동작합니다. 잠금파일이 생성되지 않아 설치 안내와 CI는 npm install을 사용합니다.
- Docker 실행 도구가 없어 공개 이미지 build와 compose 실기동은 미검증입니다.
- GitHub HTTPS Git 통신은 연결 실패였습니다. 연결 가능한 브라우저도 발견되지 않았습니다. 원격 저장소의 현재 내용·인증 상태·공개 설정은 확인하지 못했습니다.
- 워크스페이스 루트 .git은 생성 후 설정 쓰기가 Permission denied로 차단되었습니다. 별도 release/repository.git에 메타데이터를 구성하고 소스 zip과 Git bundle을 준비합니다. 기존 원격 이력을 강제로 변경하지 않습니다.
- GitHub 업로드 성공과 실제 외부 배포 URL이 확인되지 않았으므로 공개 웹사이트 정상 작동을 확인했다고 주장하지 않습니다.
- 이번 검사는 격리 데이터와 임시 DB를 사용했습니다. 기존 보고서의 실관측 수치는 해당 기록 시점의 결과이며 이번 실인증 API 성공을 의미하지 않습니다.

## 완성된 배포 준비물

루트 README, 초기 설계 보관본, 데이터 provenance manifest/검사 도구, public FastAPI 진입점, 관리 API 보호, Dockerfile·Compose, CI, 재현용 공공데이터를 포함합니다. 실제 서버 구성과 최종 외부 검증은 docs/DEPLOYMENT.md를 따릅니다.

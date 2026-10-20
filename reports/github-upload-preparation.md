# GitHub 업로드 준비 결과

2026-10-20. 이번 작업은 Git 업로드 정리와 문서화만 수행합니다. 실행 중인 서버 재시작·외부 API 수집·분석 재전처리·DB 갱신·GitHub Pages 설정은 수행하지 않습니다.

## 검사 범위와 결과

- 전체 프로젝트의 알려진 실제 .env 비밀값(원문·URL 인코딩/디코딩), 하드코딩 의심 자격증명과 토큰 패턴을 값 출력 없이 검사했습니다. 소스·설정·문서·로그·기존 release 사본과 ZIP/XML 및 gzip 내용을 포함했습니다. 설치된 라이브러리·패키지 캐시·가상환경·Git 객체 저장소는 검사 대상에서 제외했습니다. 루트 .env는 비밀정보의 허용 저장 위치로 유지합니다.
- 전체 파일 검사: secret scan: PASS. 후보 파일 검사와 실제 staged blob 검사는 commit 전에 별도로 수행합니다. 패턴 검사는 알려지지 않은 모든 비밀정보의 부재를 수학적으로 보증하지는 않습니다.
- .env ignore 확인, .env.example 추적 가능 확인. 실제 키·토큰·암호를 문서나 보고서에 복사하지 않았습니다.
- runtime DB·상태 이력·캐시·서버 로그·원본 API 응답·가상환경·Node 의존성·브라우저 및 테스트 임시파일·생성된 진단 JSON/스크린샷을 Git에서 제외합니다. 파일은 로컬에 그대로 둡니다.
- D1 1,795,169 bytes, D2 8,205,516 bytes, OA-21712 73,385 bytes. 세 원본은 분석 재생성에 필요하지만 공식 데이터셋 페이지에서 다시 다운로드할 수 있으므로 모두 추적 제외합니다. 작은 manifest와 명세 분류 설정은 유지합니다. 파일명·ID·출처·루트 저장 경로는 README에 기록했습니다.
- 새 clone의 runtime DB는 서버 시작 및 실제 수집 후 분석 준비 명령으로 재생성됩니다. 수동 confirmed/review 결과와 과거 관측 이력은 로컬에 보존되며 자동으로 동일하게 재현되지는 않습니다.
- 기존 Python/JS 소스, API 수집·상태 분류·시설 매칭·D/Q/B·정비·시뮬레이션·UI 실행 파일은 변경하지 않습니다. 문서·ignore·CI 원자료 검사 단계·읽기 전용 업로드 검사 도구만 정리합니다.
- 원본 데이터를 제외하므로 CI에서 원본 해시 검증은 제거했습니다. 다운로드 후 로컬에서 scripts/verify_source_data.py를 사용합니다. 기존 Python·Node·빌드 검증 단계는 유지합니다.

## Git 환경 제한과 준비 저장소

루트 .git은 main 브랜치의 빈 저장소입니다. 현재 실행 환경에서 .git/config 및 index.lock 쓰기가 Permission denied로 차단되어 루트 저장소의 remote 설정과 add/commit이 불가능했습니다. 파일 권한을 우회하거나 변경하지 않습니다.

따라서 ignore를 적용한 업로드 후보만 `release/github-ready/`에 복사하고 그 폴더에 독립적인 main 저장소를 준비합니다. 이 폴더에는 .env, runtime DB, 원본 XLSX/CSV가 없습니다. 기존 release/source-repository, 과거 bundle/ZIP과 구분하며 오래된 묶음을 업로드하지 마세요.

origin 대상은 https://github.com/woojk4712/capstone1.git 입니다. github.com:443 연결이 차단되어 원격 이력·README commit·인증·branch를 확인하지 못했습니다. 원격 내용 병합은 확인 가능한 환경에서 수행하며 force push는 사용하지 않습니다.

일반 Windows PowerShell에서 준비 저장소로 이동해 아래 명령을 실행합니다. 로컬 init/add/commit을 반복할 필요가 없습니다.

```powershell
cd "C:\Users\SAMSUNG\OneDrive\바탕 화면\capstone_mid\release\github-ready"
git status
git remote -v
git fetch origin
# 원격 main이 있을 때만 실행
if (git branch -r --list origin/main) {
    git -c pull.rebase=false pull origin main --allow-unrelated-histories --no-edit
    if ($LASTEXITCODE -ne 0) { throw "병합 충돌을 확인하세요. 해결 전에는 push하지 마세요." }
}
# 원격 내용을 병합했다면 먼저 아래 검사를 다시 수행
py -3.12 scripts/audit_github_upload.py --scope candidates
if ($LASTEXITCODE -ne 0) { throw "secret scan FAIL: push 중단" }
git push -u origin main
```

fetch 실패 시 인증·네트워크를 해결한 뒤 진행하세요. README 충돌은 양쪽의 유용한 내용을 보존하고 해결합니다. 원격 소스 충돌이 있으면 로컬 파일을 일괄 덮어쓰지 마세요. push 성공 후 git ls-remote origin refs/heads/main의 SHA와 git rev-parse HEAD를 비교합니다.

## 최종 로컬 검증

업로드 후보 152개 및 실제 staged blob 전체: secret scan: PASS. 금지된 원본 데이터/runtime/비밀 설정 staged 경로 0개. 실행 소스의 작업 전후 SHA-256 동일, 로컬 원자료 3개의 SHA-256 동일을 확인했습니다. 준비 저장소의 .env ignore를 확인했습니다. commit/push의 최종 상태는 Git 명령 결과를 기준으로 보고합니다.

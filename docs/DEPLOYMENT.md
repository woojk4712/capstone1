# 공개 서버 배포와 GitHub 업로드

이 문서는 배포 가능한 구성과 운영 절차입니다. 서버가 이미 공개되었다는 뜻은 아닙니다.

## GitHub 업로드

현재 환경에서 GitHub 통신이 가능하면 일반 Git 저장소에서 다음을 실행합니다.

```powershell
git remote add origin https://github.com/woojk4712/capstone1.git
git add .
git commit -m "Document implementation and prepare public deployment"
git push -u origin main
```

기존 원격 이력이 있으면 먼저 fetch하여 별도 브랜치에서 병합·검토합니다. 강제 push로 기존 내용을 덮어쓰지 않습니다. 이 작업 환경은 `.git` 쓰기와 GitHub 외부 통신이 제한되어 있어 `release/source-repository`에 독립 저장소를 준비할 수 있습니다. 해당 폴더의 저장소 또는 bundle은 원격 이력을 확인한 후 업로드합니다. `.env`나 `data/runtime`은 추가하지 않습니다.

## 서버 조건

Docker Compose가 설치된 Linux 서버, 도메인과 HTTPS 역방향 프록시, 환경공단으로의 HTTPS 연결, 본인 명의 승인 API 키가 필요합니다. GitHub 저장소 공개만으로 서버가 생성되지는 않습니다. 유료 서버 결제나 계정 생성은 이 구성에 포함하지 않습니다.

```bash
git clone https://github.com/woojk4712/capstone1.git
cd capstone1
cp .env.example .env
# 편집기로 .env의 ME_SERVICE_KEY 입력. 기존 .env는 덮어쓰지 않습니다.
chmod 600 .env
docker compose -f compose.public.yaml up -d --build
docker compose -f compose.public.yaml ps
curl -f http://127.0.0.1:8000/api/v1/health
```

`infra/public.Dockerfile`은 기본 HTML/JS와 FastAPI를 함께 제공합니다. npm 빌드는 이 서버 경로에 필요 없습니다. 이미지에는 키·실행 DB를 넣지 않으며 루트 `.env`를 읽기 전용 마운트합니다. SQLite는 `public-runtime` 볼륨에 보존됩니다. 단일 수집기를 위해 worker는 1개입니다. `docker compose down -v`는 저장 관측·수동 검토를 삭제하므로 사용하지 마세요.

환경공단 최초 수집이 성공한 뒤 분석을 준비합니다.

```bash
curl -f http://127.0.0.1:8000/api/system/status
docker compose -f compose.public.yaml exec web python scripts/verify_source_data.py
docker compose -f compose.public.yaml exec web python scripts/prepare_analysis.py --all
curl -f http://127.0.0.1:8000/api/analysis/stations
```

`connected=true`와 `stale=false`를 함께 확인합니다. 공개 앱은 수동 수집 HTTP 경로를 차단하며 시작 시 및 15분 주기로 수집합니다. 재전처리는 서버 터미널에서 수행합니다. 처음 API가 준비되지 않았다면 분석 대상 0개를 정상 연구 결과로 발표하지 않습니다.

## HTTPS 연결 예시

Caddy가 호스트에서 실행 중인 경우 아래 `charge.example.com`을 본인 도메인으로 바꿉니다. DNS도 서버에 연결되어 있어야 합니다. Caddy를 별도 컨테이너에서 실행한다면 localhost는 이 설정과 달라집니다.

```caddyfile
charge.example.com {
    reverse_proxy 127.0.0.1:8000 {
        header_up Host {host}
        header_up -Origin
        header_up Origin {http.request.header.Origin}
    }
}
```

HTTPS는 프록시에서 종료합니다. 앱은 전달 헤더를 신뢰하는 대신 외부 HTTPS 주소를 명시적으로 사용해 시뮬레이션 출처를 확인합니다.

루트 `.env`의 `PUBLIC_ORIGIN` 값을 실제 HTTPS 주소로 설정하세요. 공개 시뮬레이션은 이 정확한 Origin만 허용합니다. 관리 변경·수동 수집·legacy 쓰기는 공개 앱에서 항상 403입니다. 시설 매칭 검토는 인증된 관리 터미널/로컬 실행에서 수행합니다. 조회 API에 보이는 데이터 품질의 수동 검토 버튼은 공개 서버에서 저장되지 않습니다.

## 공개 후 확인

```bash
curl -f https://charge.example.com/
curl -f https://charge.example.com/api/v1/health
curl -f https://charge.example.com/api/system/status
curl -f 'https://charge.example.com/api/operations/stations?stopped_only=true'
curl -f 'https://charge.example.com/api/operations/recovery?radius=500'
curl -f https://charge.example.com/api/analysis/quality
# 아래는 403이어야 함
curl -i -X POST https://charge.example.com/api/admin/collect/me
```

실제 브라우저에서 지도 타일·자치구·검색·복구 탭·정비시간·시나리오 전후 출력을 확인합니다. 개발자도구 Network에서 404/500 및 JavaScript 오류가 없는지, API 키가 응답·JS에 없는지 확인합니다. 시나리오 요청은 `/api/operations/recovery`에서 받은 설비 ID와 `observationAt`을 사용합니다. 오래된 관측을 현재 실시간 데이터로 표시하지 않습니다.

배포 URL, 확인 시각, HTTP 결과, 수집 신선도와 브라우저 결과를 `reports/publication-verification.md`에 추가한 후 README의 공개 상태를 갱신합니다.


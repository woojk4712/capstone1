param([switch]$Install)
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
$taskPython = Join-Path (Get-Location) '.venv/Scripts/python.exe'
if ($Install) {
    if (!(Test-Path -LiteralPath $taskPython)) {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        $runtimePython = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
        if ($pythonCommand) { $bootstrapPython = $pythonCommand.Source }
        elseif (Test-Path -LiteralPath $runtimePython) { $bootstrapPython = $runtimePython }
        else { throw 'Python 3.12 이상이 필요합니다.' }
        & $bootstrapPython -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw '가상환경 생성 실패' }
    }
    & $taskPython -m pip install -r backend/requirements.txt
    if ($LASTEXITCODE -ne 0) { throw '패키지 설치 실패: 인터넷 연결을 확인하세요.' }
}
if (!(Test-Path -LiteralPath $taskPython)) { throw '먼저 .\scripts\run_backend.ps1 -Install 을 실행하세요.' }
$env:PYTHONIOENCODING = 'utf-8'
& $taskPython -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --no-access-log
exit $LASTEXITCODE

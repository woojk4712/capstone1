param([ValidateSet('serve','ingest','collect','test')][string]$Task='serve')
$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot/..
$pythonCommand=Get-Command python -ErrorAction SilentlyContinue
$runtimePython=Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
if($pythonCommand){$taskPython=$pythonCommand.Source}
elseif(Test-Path -LiteralPath $runtimePython){$taskPython=$runtimePython}
else{throw 'Python 3.12 이상을 설치하고 python을 PATH에 등록하세요.'}
$env:PYTHONIOENCODING='utf-8'
switch($Task){
 'serve' { & $taskPython -m services.local_server }
 'ingest' { & $taskPython -m services.ingest }
 'collect' { & $taskPython -m services.worker }
 'test' { & $taskPython -m unittest discover -s tests -v }
}
exit $LASTEXITCODE

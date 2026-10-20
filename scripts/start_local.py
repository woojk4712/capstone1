"""One-click local launcher. Uses the same Python interpreter, preserves an existing server."""
import argparse,json,os,subprocess,sys,time,urllib.request,webbrowser,importlib.util,signal,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
URL='http://127.0.0.1:8000'
PROCESS_FILE=ROOT/'data/runtime/server-process.json'

def server_status():
    try:
        with urllib.request.urlopen(URL+'/api/system/status',timeout=2) as response: return json.load(response)
    except (OSError,ValueError): return {}

def record_managed_server(status,instance_id,launcher_pid):
    pid=status.get('process_id')
    if status.get('instance_id')!=instance_id or not isinstance(pid,int) or pid<=0: return False
    PROCESS_FILE.parent.mkdir(parents=True,exist_ok=True)
    PROCESS_FILE.write_text(json.dumps({'pid':pid,'launcher_pid':launcher_pid,'instance_id':instance_id}),encoding='utf-8')
    return True

def stop_managed_server(status):
    try: record=json.loads(PROCESS_FILE.read_text(encoding='utf-8'))
    except (OSError,ValueError): return False
    if record.get('pid')!=status.get('process_id') or not record.get('instance_id') or record['instance_id']!=status.get('instance_id'): return False
    try: os.kill(record['pid'],signal.SIGTERM)
    except OSError: return False
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        if not ready(): return True
        time.sleep(.1)
    return False
def ready():
    try:
        with urllib.request.urlopen(URL+'/api/v1/health',timeout=2) as response: return json.load(response).get('status')=='ok'
    except (OSError,ValueError): return False

def needs_restart(status, preview=False):
    if not status: return False
    if status.get('runtime')!='fastapi' or status.get('uses_project_venv') is not True or status.get('collection_enabled') is not (not preview):
        return True
    # A server started by an isolated agent can retain its network restrictions.
    # Re-launch from the caller's Windows terminal instead of reusing that process.
    return not preview and (status.get('recent_errors',{}).get('ME')=='network_permission_denied'
                            or status.get('collection_revision',0)<2)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--no-browser',action='store_true');parser.add_argument('--restart',action='store_true');parser.add_argument('--preview','--no-collect',dest='preview',action='store_true');args=parser.parse_args()
    venv=ROOT/'.venv/Scripts/python.exe'
    if not venv.is_file():
        sys.exit('프로젝트 .venv가 없습니다. scripts/run_backend.ps1 -Install 실행이 필요합니다. 시스템 Python으로 대체하지 않습니다.')
    if Path(sys.executable).resolve()!=venv.resolve():
        os.execv(str(venv),[str(venv),str(Path(__file__).resolve()),*sys.argv[1:]])
    fastapi_available=all(importlib.util.find_spec(name) for name in ('fastapi','uvicorn','requests','dotenv'))
    if not fastapi_available:
        sys.exit('FastAPI/uvicorn/requests/python-dotenv 패키지가 없습니다. .venv에 backend/requirements.txt를 설치하세요. 다른 서버로 대체하지 않습니다.')
    status=server_status() if ready() else {}
    wrong_mode=bool(status) and (args.restart or needs_restart(status,args.preview))
    if wrong_mode and not stop_managed_server(status):
        sys.exit('8000번 서버의 실행 모드가 다르며 관리 PID/instance 검증이 되지 않습니다. 해당 서버를 직접 종료한 뒤 다시 실행하세요.')
    if ready() and not status:
        sys.exit('8000번의 서버 상태를 검증할 수 없습니다. 다른 프로세스는 종료하지 않습니다.')
    if not ready():
        logs=ROOT/'data'/'runtime';logs.mkdir(parents=True,exist_ok=True)
        kwargs=dict(cwd=ROOT,stdin=subprocess.DEVNULL,stdout=(logs/'server.stdout.log').open('ab'),stderr=(logs/'server.stderr.log').open('ab'))
        instance_id=uuid.uuid4().hex
        kwargs['env']=dict(os.environ,CHARGEOPS_INSTANCE_ID=instance_id)
        if os.name=='nt': kwargs['creationflags']=subprocess.CREATE_NO_WINDOW
        else: kwargs['start_new_session']=True
        if args.preview:
            command=[str(venv),'-m','uvicorn','backend.app.preview:create_preview_app','--factory','--host','127.0.0.1','--port','8000','--no-access-log']
        else:
            command=[str(venv),'-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port','8000','--no-access-log']
        child=subprocess.Popen(command,**kwargs)
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            if ready(): break
            if child.poll() is not None: break
            time.sleep(.2)
        status=server_status()
        record_managed_server(status,instance_id,child.pid)
    if not ready(): sys.exit('서버 실행 실패: data/runtime/server.stderr.log를 확인하세요.')
    status=server_status()
    if status.get('runtime')!='fastapi' or status.get('uses_project_venv') is not True or status.get('collection_enabled') is not (not args.preview):
        sys.exit('서버 실행 후 .venv/FastAPI/collection_enabled 검증 실패. 실행 성공으로 처리하지 않습니다.')
    print(('미리보기 실행(API 수집 꺼짐): ' if args.preview else 'FastAPI 실행(API 수집 켜짐): ')+URL)
    if not args.no_browser: webbrowser.open(URL,new=2)

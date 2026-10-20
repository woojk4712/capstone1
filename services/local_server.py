"""Dependency-free local edition, same API service as FastAPI. Bind loopback only."""
import argparse,json,mimetypes,urllib.parse,socket
from http.server import HTTPServer,BaseHTTPRequestHandler
from .config import ROOT
from .api import Service,ApiError
from backend.app.core import ExternalService,InternalError,error_response
import threading
service=Service()
external=ExternalService()
external.runtime='stdlib_fallback'
service.external=external
class LocalHTTPServer(HTTPServer):
    allow_reuse_address=False
    def server_bind(self):
        if hasattr(socket,'SO_EXCLUSIVEADDRUSE'): self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        super().server_bind()
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def send(self,status,payload,ctype='application/json; charset=utf-8'):
        raw=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode() if not isinstance(payload,bytes) else payload
        self.send_response(status); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(raw))); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Cache-Control','no-store' if ctype.startswith('application/json') else 'no-cache'); self.end_headers(); self.wfile.write(raw)
    def handle_request(self):
        u=urllib.parse.urlsplit(self.path); path=urllib.parse.unquote(u.path)
        if path.startswith('/api/'):
            try:
                if not path.startswith('/api/v1/'):
                    if self.command!='GET': self.send(405,dict(detail='Method not allowed')); return
                    self.send(200,external.dispatch(path,dict(urllib.parse.parse_qsl(u.query)))); return
                size=int(self.headers.get('Content-Length','0'))
                if size>100000: raise ApiError(413,'요청이 너무 큽니다.')
                body=json.loads(self.rfile.read(size)) if size else {}
                if not isinstance(body,dict): raise ApiError(422,'JSON 객체가 필요합니다.')
                result=service.dispatch(self.command,path,dict(urllib.parse.parse_qsl(u.query)),body,{k.lower():v for k,v in self.headers.items()}); self.send(200,result)
            except InternalError as e: self.send(e.status,error_response(e))
            except ApiError as e: self.send(e.status,dict(detail=e.message))
            except (ValueError,TypeError): self.send(422,dict(detail='잘못된 입력입니다.'))
            except Exception: self.send(500,dict(detail='서버 처리 오류 · 로컬 데이터를 확인하세요.'))
            return
        if self.command!='GET': self.send(405,dict(detail='Method not allowed')); return
        # Explicit public file allowlist: never serve .env, raw XLSX, database, or reports.
        if path=='/': relative='apps/web/offline.html'
        elif path=='/live': relative='apps/web/live.html'
        elif path=='/analysis': relative='apps/web/analysis.html'
        elif path in ('/apps/web/src/live-api.js','/apps/web/src/live-api.css','/apps/web/vendor/leaflet.js','/apps/web/vendor/leaflet.css'): relative=path.lstrip('/')
        elif path in ('/apps/web/src/dashboard.js','/apps/web/src/style.css','/apps/web/src/dashboard-model.js','/apps/web/src/district-bounds.js','/apps/web/src/station-map.js','/apps/web/src/leaflet-map.js'): relative=path.lstrip('/')
        else: self.send(404,dict(detail='Not found')); return
        file=ROOT/relative
        if not file.exists(): self.send(404,dict(detail='Not found')); return
        self.send(200,file.read_bytes(),(mimetypes.guess_type(str(file))[0] or 'application/octet-stream')+'; charset=utf-8')
    do_GET=handle_request
    do_POST=handle_request
    do_PATCH=handle_request
if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--port',type=int,default=8000); p.add_argument('--no-collect',action='store_true'); args=p.parse_args()
    print(f'Local dashboard: http://127.0.0.1:{args.port}',flush=True)
    def collect_loop():
        import time
        while True:
            external.refresh()
            time.sleep(900)
    if not args.no_collect: threading.Thread(target=collect_loop,daemon=True).start()
    else:
        from backend.app.storage import Storage
        external=ExternalService(storage=Storage(ROOT/'data/runtime/preview-api.sqlite'))
        external.runtime='stdlib_preview_no_external_calls'
        external.collection_enabled=False
        service.external=external
    LocalHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()

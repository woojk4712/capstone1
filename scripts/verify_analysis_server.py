"""Read-only actual-data verification app. No external collection, no mock data.

Run on a separate loopback port to test new routes without replacing the user's
working Windows collector. The production external SQLite database is read-only.
"""
import sqlite3
from contextlib import contextmanager
from backend.app.settings import ROOT,Settings
from backend.app.storage import Storage
from backend.app.core import ExternalService
from backend.app.main import create_app

class ReadOnlyStorage(Storage):
    def __init__(self):self.path=str(ROOT/'data/runtime/external-api.sqlite')

    @contextmanager
    def connection(self):
        db=sqlite3.connect('file:'+self.path.replace('\\','/')+'?mode=ro',uri=True,timeout=15)
        try:yield db
        finally:db.close()

def create_verification_app():
    def no_external_calls(*args,**kwargs):raise RuntimeError('Verification app forbids external requests')
    service=ExternalService(Settings.load(),ReadOnlyStorage(),no_external_calls)
    service.reset_runtime=lambda:None  # Preserve the live collector's state; never write it.
    app=create_app(service,collect=False)
    @app.middleware('http')
    async def read_only(request,call_next):
        if request.method not in ('GET','HEAD') and not (request.method=='POST' and request.url.path in ('/api/analysis/simulate','/api/operations/simulate')):
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=405,content={'error_type':'read_only_verification'})
        return await call_next(request)
    return app

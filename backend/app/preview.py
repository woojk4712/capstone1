"""FastAPI browser preview only. Never calls external providers."""
def create_preview_app():
    from .main import create_app
    from .core import ExternalService
    from .storage import Storage
    from .settings import ROOT
    service=ExternalService(storage=Storage(ROOT/'data/runtime/preview-api.sqlite'))
    return create_app(service,collect=False)

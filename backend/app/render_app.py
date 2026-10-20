"""Render-specific environment, recoverable static research inputs, public API."""
import logging
import os
from .core import ExternalService
from .deployment_seed import SeedResearchService
from .main import create_app


class RenderExternalService(ExternalService):
    analysis = None
    prepared_observation = None
    phase = 'awaiting_collection'

    def refresh(self):
        super().refresh()
        state = self.storage.state('ME')
        if self.analysis is not None and state.get('connected') and state.get('last_success_at') != self.prepared_observation:
            self.phase = 'preparing_matches'
            try:
                self.analysis.prepare_all()
                self.prepared_observation = state['last_success_at']
                self.phase = 'ready'
                logging.getLogger(__name__).info('Render research preparation complete')
            except Exception as error:
                self.phase = 'analysis_preparation_failed'
                # Never print exception text, URL, request parameters, or secrets.
                logging.getLogger(__name__).error('Render preparation failed type=%s', type(error).__name__)


def create_render_app(service=None, collect=True, seed_dir=None):
    if service is None and os.environ.get('CHARGEOPS_DEPLOYMENT') != 'render':
        raise RuntimeError('Render entry point requires CHARGEOPS_DEPLOYMENT=render')
    external = service or RenderExternalService()
    def factory(external, path):
        return SeedResearchService(external, path, **({'seed_dir': seed_dir} if seed_dir else {}))
    app = create_app(external, collect=collect, public=True,
                     public_origin=(os.environ.get('PUBLIC_ORIGIN') or os.environ.get('RENDER_EXTERNAL_URL') or '').rstrip('/') or None,
                     analysis_factory=factory)
    external.analysis = app.state.analysis

    @app.get('/api/deployment/status')
    def deployment_status():
        return {'seedReady': bool(external.analysis.meta('deployment_seed')),
                'phase': external.phase, 'preparedObservationAt': external.prepared_observation,
                'matching': external.analysis.match_summary(), 'd2Ready': bool(external.analysis.meta('d2').get('available'))}
    return app


app = create_render_app() if os.environ.get('CHARGEOPS_DEPLOYMENT') == 'render' else None

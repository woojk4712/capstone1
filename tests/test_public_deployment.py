import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.app.core import ExternalService
from backend.app.main import create_app
from backend.app.settings import Settings
from backend.app.storage import Storage


class PublicDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        service = ExternalService(Settings({}), Storage(Path(self.temp.name) / 'external.sqlite'))
        app = create_app(service, collect=False, public=True, public_origin='https://charge.example')
        async def remote(scope, receive, send):
            scope = dict(scope, client=('198.51.100.10', 1234))
            await app(scope, receive, send)
        self.client = TestClient(remote, base_url='http://internal-proxy')

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def test_public_dashboard_assets_and_health(self):
        for path in ('/', '/apps/web/src/dashboard.js', '/apps/web/vendor/leaflet.js', '/api/v1/health'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_public_cannot_trigger_collection_or_change_matches(self):
        for path in ('/api/admin/collect/me', '/api/analysis/matches/review', '/api/v1/admin/matches/S', '/api/v1/simulations'):
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path, json={}).status_code, 403)
        self.assertEqual(self.client.get('/api/v1/admin/matches').status_code, 403)

    def test_remote_calculation_requires_same_origin(self):
        with patch('backend.app.operational_view.OperationalView.simulate', return_value={'calculated': True}) as calculation:
            for headers in ({}, {'origin': 'https://attacker.example'}):
                self.assertEqual(self.client.post('/api/operations/simulate', json={}, headers=headers).status_code, 403)
            calculation.assert_not_called()
            response = self.client.post('/api/operations/simulate', json={}, headers={'origin': 'https://charge.example'})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()['calculated'])

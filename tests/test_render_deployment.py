import gzip
import hashlib
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.app.core import ExternalService
from backend.app.deployment_seed import SEED_DIR, SeedResearchService, check_seed
from backend.app.render_app import RenderExternalService, create_render_app
from backend.app.research import ResearchService
from backend.app.settings import Settings, runtime_directory
from backend.app.storage import Storage, now


class RenderDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def external(self):
        return RenderExternalService(Settings({}), Storage(self.folder / 'runtime/external-api.sqlite'))

    def test_seed_counts_and_persistence_without_originals_or_observations(self):
        external = self.external()
        service = SeedResearchService(external, self.folder / 'runtime/analysis.sqlite')
        expected = check_seed()['counts']
        with service.db() as db:
            for kind, table in (('demand', 'd1_demand'), ('facility', 'bridge_facilities'), ('session', 'd2_sessions')):
                self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0], expected[kind])
            self.assertEqual(db.execute('SELECT COUNT(*) FROM station_match').fetchone()[0], 0)
            name = db.execute('SELECT d1_station_name FROM d1_demand LIMIT 1').fetchone()[0]
            db.execute('INSERT INTO station_match VALUES (?,?,?,?,?,?,?,?,?,?)', (name, name, 'MANUAL', 'fixture', 'fixture', 'confirmed_manual', 'manual_documented', 1, 'independent fixture evidence', now()))
        again = SeedResearchService(external, service.path)
        self.assertEqual(again.match_summary()['confirmed_manual'], 1)
        self.assertEqual(external.storage.charger_count(), 0)

    def test_fresh_cloud_without_key_serves_health_ui_assets_and_static_research(self):
        external = self.external()
        app = create_render_app(external, collect=False)
        with TestClient(app) as client:
            self.assertEqual(client.get('/health').json(), {'status': 'ok'})
            for path in ('/', '/analysis', '/live', '/apps/web/src/dashboard.js', '/apps/web/src/research-tabs.js',
                         '/apps/web/vendor/leaflet.js', '/apps/web/vendor/leaflet.css', '/apps/web/src/style.css',
                         '/api/system/status', '/api/analysis/stations', '/api/deployment/status'):
                self.assertEqual(client.get(path).status_code, 200, path)
            self.assertTrue(client.get('/api/deployment/status').json()['seedReady'])
            self.assertEqual(client.get('/api/chargers').status_code, 503)
            self.assertFalse(client.get('/api/system/status').json()['providers']['ME']['connected'])

    def test_render_environment_is_opt_in_and_legacy_loader_preserves_it(self):
        from backend.app.settings import read_env
        with patch.dict(os.environ, {'CHARGEOPS_DEPLOYMENT': 'render', 'ME_SERVICE_KEY': 'IN_MEMORY_TEST_VALUE',
                                     'ME_URL': 'https://apis.data.go.kr/test', 'CHARGEOPS_RUNTIME_DIR': str(self.folder)}):
            with patch('backend.app.settings.read_env', return_value={}):
                self.assertEqual(Settings.load().get('ME_SERVICE_KEY'), 'IN_MEMORY_TEST_VALUE')
                from services.config import load_env
                load_env()
                self.assertEqual(os.environ['ME_SERVICE_KEY'], 'IN_MEMORY_TEST_VALUE')
            self.assertEqual(runtime_directory(), self.folder)
        with patch.dict(os.environ, {'CHARGEOPS_DEPLOYMENT': '', 'ME_SERVICE_KEY': 'IN_MEMORY_TEST_VALUE'}):
            with patch('backend.app.settings.read_env', return_value={}):
                self.assertEqual(Settings.load().get('ME_SERVICE_KEY'), '')

    def test_live_collection_triggers_existing_matching_and_maintenance_algorithm(self):
        external = self.external()
        service = SeedResearchService(external, self.folder / 'runtime/analysis.sqlite')
        external.analysis = service
        facilities, _ = service.read_bridge()
        with service.db() as db:
            demand_names = {r[0] for r in db.execute('SELECT normalized_station_name FROM d1_demand')}
        # A real registry record with synthetic operating observation; no real API.
        target = next(f for f in facilities.values() if f['normalized_name'] in demand_names and len(f['rows']) == 1
                      and sum(v['normalized_name'] == f['normalized_name'] for v in facilities.values()) == 1
                      and service.meta('d1_types').get(f['normalized_name']) == ['급속']
                      and all('급속' in r['CHARG_TYPE']+' '+r['CHARG_CPCT'] for r in f['rows']))
        rows = [dict(statId='ISOLATED_SEED_TEST', chgerId=r['CHARG_ID'], statNm=target['name'], addr=target['address'],
                     lat='37.5', lng='127.0', output=re.search(r'(\d+(?:\.\d+)?)\s*kW', r['CHARG_CPCT'], re.I).group(1), stat='4', chgerType='04', delYn='N', limitYn='N', useTime='24시간') for r in target['rows']]
        external.settings = Settings({'ME_MAPPING_VERIFIED': 'true', 'ME_STATUS_MAP': '{"4":"STOPPED"}', 'ME_FAST_TYPES': '["04"]'})
        def collect(instance):
            instance.storage.save_me(rows, now(), 200)
        with patch.object(ExternalService, 'refresh', collect):
            external.refresh()
        self.assertEqual(external.phase, 'ready')
        # The deployment adapter delegates to the identical algorithm methods.
        self.assertIs(SeedResearchService.maintenance, ResearchService.maintenance)
        self.assertIs(SeedResearchService.overview, ResearchService.overview)
        self.assertIs(SeedResearchService.simulate, ResearchService.simulate)
        self.assertGreaterEqual(service.match_summary()['confirmed'], 1)
        self.assertTrue(service.meta('d2')['available'])
        station = service.stations()['items'][0]
        self.assertTrue(station['analysis_ready'])
        self.assertEqual(service.maintenance(station['statId'])['status'], 'READY')
        self.assertTrue(service.maintenance(station['statId'])['oneHour'])
        priorities = service.overview()['priorities']
        self.assertTrue(priorities)
        simulation = service.simulate([priorities[0]['charger_id']])
        self.assertGreater(simulation['recoveredKw'], 0)
        self.assertAlmostEqual(simulation['after']['normalKw']-simulation['before']['normalKw'], simulation['recoveredKw'])

    def test_corrupt_seed_fails_validation(self):
        folder = self.folder / 'seed'
        folder.mkdir()
        (folder/'manifest.json').write_text((SEED_DIR/'manifest.json').read_text(encoding='utf-8'), encoding='utf-8')
        (folder/'research.jsonl.gz').write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            check_seed(folder)

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import start_local

class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.file=Path(self.tmp.name)/'process.json'
        self.file.write_text(json.dumps({'pid':12345,'instance_id':'owned-instance'}),encoding='utf-8')

    def test_never_stop_unowned_server(self):
        for status in ({'process_id':99999,'instance_id':'owned-instance'}, {'process_id':12345,'instance_id':'different-instance'}):
            with patch.object(start_local,'PROCESS_FILE',self.file),patch.object(start_local.os,'kill') as kill:
                self.assertFalse(start_local.stop_managed_server(status));kill.assert_not_called()

    def test_restart_only_matching_managed_preview(self):
        with patch.object(start_local,'PROCESS_FILE',self.file),patch.object(start_local.os,'kill') as kill,patch.object(start_local,'ready',return_value=False):
            self.assertTrue(start_local.stop_managed_server({'process_id':12345,'instance_id':'owned-instance'}))
            kill.assert_called_once_with(12345,start_local.signal.SIGTERM)

    def test_missing_record_does_not_stop_process(self):
        with patch.object(start_local,'PROCESS_FILE',self.file.with_name('missing.json')),patch.object(start_local.os,'kill') as kill:
            self.assertFalse(start_local.stop_managed_server({'process_id':12345,'instance_id':'owned-instance'}));kill.assert_not_called()

    def test_windows_venv_redirector_pid_can_differ(self):
        with patch.object(start_local,'PROCESS_FILE',self.file):
            self.assertTrue(start_local.record_managed_server({'process_id':12345,'instance_id':'child-token'},'child-token',67890))
            record=json.loads(self.file.read_text())
            self.assertEqual(record['pid'],12345);self.assertEqual(record['launcher_pid'],67890)

    def test_record_rejects_unrelated_server(self):
        with patch.object(start_local,'PROCESS_FILE',self.file):
            self.assertFalse(start_local.record_managed_server({'process_id':12345,'instance_id':'other-token'},'child-token',67890))

    def test_permission_restricted_collector_is_replaced_by_local_launch(self):
        status={'runtime':'fastapi','uses_project_venv':True,'collection_enabled':True,
                'collection_revision':2,'recent_errors':{'ME':'network_permission_denied'}}
        self.assertTrue(start_local.needs_restart(status))
        status['recent_errors']['ME']=None
        self.assertFalse(start_local.needs_restart(status))
        status['recent_errors']['ME']='api_authentication_error'
        self.assertFalse(start_local.needs_restart(status))

    def test_old_collection_implementation_is_restarted(self):
        self.assertTrue(start_local.needs_restart({'runtime':'fastapi','uses_project_venv':True,
                                                   'collection_enabled':True,'recent_errors':{'ME':None}}))

    def test_explicit_preview_is_reused_only_in_preview_mode(self):
        status={'runtime':'fastapi','uses_project_venv':True,'collection_enabled':False,
                'recent_errors':{'ME':'network_permission_denied'}}
        self.assertFalse(start_local.needs_restart(status,preview=True))
        self.assertTrue(start_local.needs_restart(status))

if __name__=='__main__':unittest.main()

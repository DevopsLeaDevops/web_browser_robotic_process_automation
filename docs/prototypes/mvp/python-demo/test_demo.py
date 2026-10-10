"""執行：python -m unittest -v test_demo；全部使用本機測試頁。"""
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from run_demo import execute_scene
from target.server import create_server


class DemoRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = create_server()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_real_browser_chain_and_independent_assertion(self):
        from scenes.assertion import verify
        with tempfile.TemporaryDirectory() as directory:
            params = {'title': '繁體中文鏈路驗證', 'quantity': 23}
            first, folder = execute_scene('BA-001', params, self.url, directory)
            self.assertEqual(first['status'], 'passed', first.get('error'))
            self.assertTrue((folder/'screenshot.png').is_file())
            self.assertTrue((folder/'output.json').is_file())
            facts = json.loads((folder/'facts.json').read_text())
            # 單改畫面事實，獨立斷言必須失敗。
            facts['quantity'] = 99
            with self.assertRaises(AssertionError):
                verify('BA-001', params, facts)
            second, _ = execute_scene('BA-002', {'recordId': first['output']['recordId']}, self.url, directory)
            self.assertEqual(second['status'], 'passed', second.get('error'))
            self.assertEqual(first['output'], second['output'])

    def test_runner_assertion_failure_never_publishes_output(self):
        from run_demo import run_process
        def tamper_before_assertion(command, log_path, deadline):
            if log_path.name == 'assertion.log':
                facts_path = log_path.with_name('facts.json')
                facts = json.loads(facts_path.read_text())
                facts['quantity'] = 99
                facts_path.write_text(json.dumps(facts))
            return run_process(command, log_path, deadline)
        with tempfile.TemporaryDirectory() as directory, patch('run_demo.run_process', side_effect=tamper_before_assertion):
            result, folder = execute_scene('BA-001', {'title': '斷言失敗驗證', 'quantity': 12}, self.url, directory)
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(result['steps'][-1]['name'], '獨立斷言')
            self.assertFalse((folder/'output.json').exists())
            self.assertIsNone(result['output'])
            self.assertTrue((folder/'screenshot.png').exists())

    def test_invalid_input_never_starts_browser(self):
        with tempfile.TemporaryDirectory() as directory, patch('run_demo.run_process') as worker:
            result, folder = execute_scene('BA-001', {'quantity': 100}, self.url, directory)
            self.assertEqual(result['status'], 'failed')
            worker.assert_not_called()
            self.assertFalse((folder/'output.json').exists())
            self.assertTrue((folder/'report.html').exists())

    def test_deadline_stops_worker_and_never_publishes_output(self):
        with tempfile.TemporaryDirectory() as directory:
            started = time.monotonic()
            result, folder = execute_scene('BA-001', {'title': '超時範例', 'quantity': 10}, self.url, directory, timeout=0.001)
            self.assertEqual(result['status'], 'timed_out')
            self.assertLess(time.monotonic()-started, 5)
            self.assertFalse((folder/'output.json').exists())
            self.assertTrue((folder/'report.html').exists())

    def test_unknown_record_failure_has_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            # 頁面查詢失敗後等不到詳情；外層總期限也必須生效。
            result, folder = execute_scene('BA-002', {'recordId': 'DEMO-MISSING'}, self.url, directory, timeout=4)
            self.assertIn(result['status'], ('failed', 'timed_out'))
            self.assertIsNone(result['output'])
            self.assertTrue((folder/'report.html').exists())


if __name__ == '__main__':
    unittest.main()

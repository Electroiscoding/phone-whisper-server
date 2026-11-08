import unittest
import threading
import time
import json
import urllib.request
import os
import sys

from gateway import MultiModalGatewayHandler, ThreadedHTTPServer

TEST_PORT = 8925

class TestQwenExperimenter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadedHTTPServer(('127.0.0.1', TEST_PORT), MultiModalGatewayHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(1.0)
        cls.base_url = f"http://127.0.0.1:{TEST_PORT}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_01_qwen_html_served(self):
        req = urllib.request.Request(f"{self.base_url}/qwen")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            ct = resp.headers.get("Content-Type", "")
            self.assertIn("text/html", ct)
            content = resp.read().decode("utf-8")
            self.assertIn("QWEN 2.5 SOVEREIGN EXPERIMENTER", content)
            self.assertIn("#000000", content)
            self.assertIn("Nir Eyal", content)

    def test_02_qwen_experiments_get(self):
        req = urllib.request.Request(f"{self.base_url}/v1/qwen/experiments")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("model_biodata", data)
            self.assertIn("optimal_config", data)
            self.assertIn("total_cycles", data)
            self.assertGreaterEqual(data["total_cycles"], 1)

    def test_03_qwen_logs_get(self):
        req = urllib.request.Request(f"{self.base_url}/v1/qwen/logs")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            ct = resp.headers.get("Content-Type", "")
            self.assertIn("text/plain", ct)
            log_text = resp.read().decode("utf-8")
            self.assertIn("[EXPERIMENT", log_text)
            self.assertIn("[HYPOTHESIS]", log_text)
            self.assertIn("[CONCLUSION]", log_text)

    def test_04_qwen_experiment_trigger(self):
        req = urllib.request.Request(
            f"{self.base_url}/v1/qwen/experiment/trigger",
            data=b"{}",
            headers={"Content-Type": "application/json"}
        )
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=60) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "ok")
            rec = data.get("record", {})
            self.assertIn("cycle", rec)
            self.assertIn("hypothesis", rec)
            self.assertIn("conclusion", rec)
            self.assertIn("metrics", rec)
            print(f"[+] Cycle #{rec['cycle']} triggered via API in {round(time.time() - t0, 1)}s. Verdict: {rec['verdict']}")

if __name__ == "__main__":
    unittest.main()

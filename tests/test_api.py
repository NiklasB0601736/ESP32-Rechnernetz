import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.service import Lab


class ApiTests(unittest.TestCase):
    def test_dashboard_validation_websocket_and_origin(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            with TestClient(create_app(lab=Lab(Path(tmp)))) as client:
                self.assertEqual(client.get("/").status_code,200)
                self.assertEqual(client.get("/vendor/chart.umd.js").status_code,200)
                self.assertEqual(client.get("/api/state").json()["mode"],"disconnected")
                self.assertEqual(client.post("/api/tests",json={"source":1,"destination":1}).status_code,422)
                self.assertEqual(client.post("/api/configure",json={"powers":{"1":44}},headers={"Origin":"https://example.com"}).status_code,403)
                with client.websocket_connect("/ws") as ws:
                    event=ws.receive_json()
                    self.assertEqual(event["type"],"state")
                    self.assertEqual(event["data"]["nodes"],[])

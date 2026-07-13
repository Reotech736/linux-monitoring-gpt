import json
import importlib.util
import pathlib
import unittest


STATUS_APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "status_api" / "app.py"
STATUS_APP_SPEC = importlib.util.spec_from_file_location("status_api_app", STATUS_APP_PATH)
app = importlib.util.module_from_spec(STATUS_APP_SPEC)
assert STATUS_APP_SPEC.loader is not None
STATUS_APP_SPEC.loader.exec_module(app)


class FakeAmpClient:
    def __init__(self, values):
        self.values = values

    def query(self, expression):
        for name, value in self.values.items():
            if name in expression:
                if value is None:
                    return {"status": "success", "data": {"result": []}}
                return {
                    "status": "success",
                    "data": {"result": [{"value": [1783872000, str(value)]}]},
                }
        raise AssertionError(f"unexpected query: {expression}")


class StatusApiTests(unittest.TestCase):
    def setUp(self):
        self.values = {
            "up": 1,
            "node_cpu_seconds_total": 42.5,
            "node_memory_MemAvailable_bytes": 60.0,
            "node_filesystem_avail_bytes": 70.0,
            "node_load5": 1.24,
            "node_boot_time_seconds": 18.4,
        }
        self.authorized_event = {
            "pathParameters": {"host_id": "home-server"},
            "requestContext": {
                "authorizer": {
                    "jwt": {"claims": {"cognito:groups": "monitoring-viewer-home-server"}}
                }
            },
        }

    def test_returns_reachable_host_without_alerts(self):
        response = app.lambda_handler(
            self.authorized_event, None, FakeAmpClient(self.values)
        )

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertTrue(body["reachable"])
        self.assertEqual(body["alerts"], [])
        self.assertEqual(body["cpu_usage_percent"], 42.5)

    def test_adds_threshold_and_missing_metric_alerts(self):
        values = {**self.values, "node_cpu_seconds_total": 95, "node_filesystem_avail_bytes": None}
        response = app.lambda_handler(
            self.authorized_event, None, FakeAmpClient(values)
        )

        body = json.loads(response["body"])
        self.assertIn("cpu_usage_high", body["alerts"])
        self.assertIn("metrics_unavailable", body["alerts"])
        self.assertIsNone(body["disk_usage_percent"])

    def test_rejects_unknown_host_without_querying_amp(self):
        response = app.lambda_handler(
            {"pathParameters": {"host_id": "other-host"}}, None, FakeAmpClient(self.values)
        )

        self.assertEqual(response["statusCode"], 404)
        self.assertEqual(json.loads(response["body"]), {"code": "host_not_found"})

    def test_rejects_user_outside_the_authorized_group(self):
        response = app.lambda_handler(
            {"pathParameters": {"host_id": "home-server"}}, None, FakeAmpClient(self.values)
        )

        self.assertEqual(response["statusCode"], 403)
        self.assertEqual(json.loads(response["body"]), {"code": "forbidden"})

    def test_accepts_group_claim_encoded_as_a_json_array(self):
        event = {
            "pathParameters": {"host_id": "home-server"},
            "requestContext": {
                "authorizer": {
                    "jwt": {"claims": {"cognito:groups": '["monitoring-viewer-home-server"]'}}
                }
            },
        }

        response = app.lambda_handler(event, None, FakeAmpClient(self.values))

        self.assertEqual(response["statusCode"], 200)

    def test_accepts_group_claim_encoded_as_an_unquoted_array(self):
        event = {
            "pathParameters": {"host_id": "home-server"},
            "requestContext": {
                "authorizer": {
                    "jwt": {"claims": {"cognito:groups": "[monitoring-viewer-home-server]"}}
                }
            },
        }

        response = app.lambda_handler(event, None, FakeAmpClient(self.values))

        self.assertEqual(response["statusCode"], 200)

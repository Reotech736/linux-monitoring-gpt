import json
import pathlib
import sys
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.testclient import TestClient

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from mcp_api.server import CognitoVerifier, GROUP, Settings, create_server
from mcp_api.handler import lambda_handler


class FakeAmp:
    def __init__(self):
        self.calls = []
        self.fail = False
        self.missing = False

    def query(self, expression):
        self.calls.append(expression)
        if self.fail:
            raise RuntimeError("SECRET_INTERNAL_DETAIL")
        return {"data": {"result": [] if self.missing else [{"value": [1783872000, "1"]}]}}


class McpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        self.settings = Settings("https://issuer.example/pool", "mcp-client", "https://monitor.example/mcp", "https://amp.example/workspaces/test", "https://login.example")
        self.verifier = CognitoVerifier(self.settings)
        self.key_patch = patch.object(self.verifier.jwks, "get_signing_key_from_jwt", return_value=SimpleNamespace(key=self.key.public_key()))
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)
        self.amp = FakeAmp()
        self.claims = {
            "iss": self.settings.issuer, "aud": self.settings.resource,
            "iat": int(time.time()) - 1, "exp": int(time.time()) + 300,
            "sub": "test-user", "client_id": "mcp-client", "token_use": "access",
            "scope": self.settings.scope, "cognito:groups": [GROUP],
        }

    def token(self, **overrides):
        return jwt.encode({**self.claims, **overrides}, self.key, algorithm="RS256")

    def server(self):
        return create_server(self.settings, verifier=self.verifier, query_client=self.amp)

    def headers(self, token=None):
        return {"Authorization": f"Bearer {token or self.token()}", "Accept": "application/json, text/event-stream"}

    def call(self, client, method, params=None, token=None):
        return client.post("/mcp", headers=self.headers(token), json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})

    def test_discovery_and_unauthenticated_challenge(self):
        with TestClient(self.server().streamable_http_app(), base_url="https://monitor.example") as client:
            response = client.post("/mcp", json={})
            self.assertEqual(response.status_code, 401)
            self.assertIn("resource_metadata=", response.headers["www-authenticate"])
            metadata = client.get("/.well-known/oauth-protected-resource/mcp").json()
            self.assertEqual(metadata["resource"], self.settings.resource)
            self.assertEqual(metadata["authorization_servers"], [self.settings.metadata_issuer])
            oauth = client.get("/.well-known/oauth-authorization-server").json()
            self.assertEqual(oauth["issuer"], self.settings.metadata_issuer)
            self.assertEqual(oauth["code_challenge_methods_supported"], ["S256"])
            self.assertEqual(oauth["authorization_endpoint"], "https://login.example/oauth2/authorize")
            self.assertEqual(oauth["scopes_supported"], [self.settings.scope])
            self.assertNotIn("registration_endpoint", oauth)
        self.assertEqual(self.amp.calls, [])

    def test_initialize_list_and_read(self):
        with TestClient(self.server().streamable_http_app(), base_url="https://monitor.example") as client:
            response = self.call(client, "initialize", {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}})
            self.assertIn("serverInfo", response.json()["result"])
            tools = self.call(client, "tools/list").json()["result"]["tools"]
            self.assertEqual([tool["name"] for tool in tools], ["getHostStatus"])
            self.assertTrue(tools[0]["annotations"]["readOnlyHint"])
            self.assertIn("outputSchema", tools[0])
            self.assertEqual(tools[0]["securitySchemes"], [{"type": "oauth2", "scopes": [self.settings.scope]}])
            response = self.call(client, "tools/call", {"name": "getHostStatus", "arguments": {"host_id": "home-server"}})
            result = response.json()["result"]
            self.assertFalse(result.get("isError", False))
            self.assertEqual(result["structuredContent"]["host"], "home-server")
            self.assertEqual(len(self.amp.calls), 6)

    def test_invalid_tokens_cannot_query_amp(self):
        variants = [{"aud": "https://other.example/mcp"}, {"iss": "https://other.example"}, {"exp": 1}, {"client_id": "legacy-client"}, {"token_use": "id"}, {"scope": "openid"}, {"scope": "linux-monitoring/status.read"}, {"cognito:groups": []}, {"cognito:groups": GROUP}]
        with TestClient(self.server().streamable_http_app(), base_url="https://monitor.example") as client:
            for variant in variants:
                with self.subTest(variant=variant):
                    response = self.call(client, "tools/call", {"name": "getHostStatus", "arguments": {"host_id": "home-server"}}, self.token(**variant))
                    self.assertEqual(response.status_code, 401)
            wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            token = jwt.encode(self.claims, wrong_key, algorithm="RS256")
            self.assertEqual(self.call(client, "tools/list", token=token).status_code, 401)
        self.assertEqual(self.amp.calls, [])

    def test_invalid_host_and_unknown_tool_cannot_query_amp(self):
        with TestClient(self.server().streamable_http_app(), base_url="https://monitor.example") as client:
            for name, host in [("getHostStatus", "other-host"), ("runShell", "home-server")]:
                response = self.call(client, "tools/call", {"name": name, "arguments": {"host_id": host}})
                self.assertTrue(response.json()["result"]["isError"])
        self.assertEqual(self.amp.calls, [])

    def test_extra_arguments_cannot_query_amp(self):
        with TestClient(self.server().streamable_http_app(), base_url="https://monitor.example") as client:
            response = self.call(client, "tools/call", {"name": "getHostStatus", "arguments": {"host_id": "home-server", "promql": "up"}})
            result = response.json()
            self.assertTrue("error" in result or result.get("result", {}).get("isError"))
        self.assertEqual(self.amp.calls, [])

    def test_missing_metrics_and_sanitized_error(self):
        with TestClient(self.server().streamable_http_app(), base_url="https://monitor.example") as client:
            params = {"name": "getHostStatus", "arguments": {"host_id": "home-server"}}
            self.amp.missing = True
            status = self.call(client, "tools/call", params).json()["result"]["structuredContent"]
            self.assertIsNone(status["cpu_usage_percent"])
            self.assertIn("metrics_unavailable", status["alerts"])
            self.amp.fail = True
            response = self.call(client, "tools/call", params)
            self.assertTrue(response.json()["result"]["isError"])
            self.assertNotIn("SECRET_INTERNAL_DETAIL", response.text)

    def test_origin_rejected(self):
        with TestClient(self.server().streamable_http_app(), base_url="https://monitor.example") as client:
            response = client.post("/mcp", headers={**self.headers(), "Origin": "https://evil.example"}, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            self.assertEqual(response.status_code, 403)

    def test_repeated_lambda_invocations(self):
        event = {
            "version": "2.0", "routeKey": "POST /mcp", "rawPath": "/mcp", "rawQueryString": "",
            "headers": {"host": "monitor.example", "content-type": "application/json", **{k.lower(): v for k, v in self.headers().items()}},
            "requestContext": {"http": {"method": "POST", "path": "/mcp", "sourceIp": "127.0.0.1", "protocol": "HTTP/1.1"}},
            "body": json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}), "isBase64Encoded": False,
        }
        with patch("mcp_api.handler.Settings.from_env", return_value=self.settings), patch("mcp_api.handler.create_server", side_effect=lambda _: self.server()):
            for _ in range(2):
                response = lambda_handler(event, None)
                self.assertEqual(response["statusCode"], 200)
                self.assertEqual(json.loads(response["body"])["result"]["tools"][0]["name"], "getHostStatus")

    def test_lambda_get_does_not_open_an_sse_connection(self):
        response = lambda_handler({"rawPath": "/mcp", "requestContext": {"http": {"method": "GET"}}}, None)
        self.assertEqual(response["statusCode"], 405)
        self.assertEqual(response["headers"]["allow"], "POST")

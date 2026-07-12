import importlib.util
import os
import pathlib
import unittest


AUTHORIZER_APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "authorizer" / "app.py"
AUTHORIZER_APP_SPEC = importlib.util.spec_from_file_location("authorizer_app", AUTHORIZER_APP_PATH)
authorizer = importlib.util.module_from_spec(AUTHORIZER_APP_SPEC)
assert AUTHORIZER_APP_SPEC.loader is not None
AUTHORIZER_APP_SPEC.loader.exec_module(authorizer)


class FakeParameterClient:
    def get_parameter(self, *, Name, WithDecryption):
        self.name = Name
        self.with_decryption = WithDecryption
        return {"Parameter": {"Value": "correct-secret"}}


class AuthorizerTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeParameterClient()
        os.environ["API_KEY_PARAMETER_NAME"] = "/linux-monitoring-gpt/poc/api-key"

    def test_allows_matching_header_case_insensitively(self):
        response = authorizer.lambda_handler(
            {"headers": {"X-Api-Key": "correct-secret"}}, None, self.client
        )

        self.assertEqual(response, {"isAuthorized": True})

    def test_rejects_missing_or_invalid_header(self):
        self.assertEqual(authorizer.lambda_handler({"headers": {}}, None, self.client), {"isAuthorized": False})
        self.assertEqual(
            authorizer.lambda_handler(
                {"headers": {"x-api-key": "incorrect-secret"}}, None, self.client
            ),
            {"isAuthorized": False},
        )

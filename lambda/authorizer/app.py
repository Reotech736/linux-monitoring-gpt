"""HTTP API Lambda Authorizer for the Phase 4 shared secret."""

from __future__ import annotations

import hmac
import os
from typing import Any, Protocol


class ParameterClient(Protocol):
    def get_parameter(self, *, Name: str, WithDecryption: bool) -> dict[str, Any]:
        """Read the configured API shared secret."""


def _header_value(event: dict[str, Any], name: str) -> str | None:
    headers = event.get("headers") or {}
    for header_name, value in headers.items():
        if header_name.lower() == name.lower() and isinstance(value, str):
            return value
    return None


def lambda_handler(
    event: dict[str, Any], _context: Any, client: ParameterClient | None = None
) -> dict[str, bool]:
    supplied_secret = _header_value(event, "x-api-key")
    if not supplied_secret:
        return {"isAuthorized": False}

    try:
        if client is None:
            import boto3
            from botocore.config import Config

            client = boto3.client(
                "ssm",
                config=Config(connect_timeout=2, read_timeout=3, retries={"max_attempts": 2}),
            )
        expected_secret = client.get_parameter(
            Name=os.environ["API_KEY_PARAMETER_NAME"], WithDecryption=True
        )["Parameter"]["Value"]
    except (KeyError, RuntimeError):
        return {"isAuthorized": False}
    except Exception:
        # Do not return or log SSM details from an authorization path.
        return {"isAuthorized": False}

    return {"isAuthorized": hmac.compare_digest(supplied_secret, expected_secret)}

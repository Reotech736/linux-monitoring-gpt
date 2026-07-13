"""Read-only status endpoint backed by fixed AMP PromQL queries."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from typing import Any, Protocol
from urllib.parse import urlencode


CPU_WARNING_PERCENT = 90.0
MEMORY_WARNING_PERCENT = 90.0
DISK_WARNING_PERCENT = 85.0
LOGGER = logging.getLogger()


class AmpQueryError(RuntimeError):
    """Raised when AMP cannot return a valid Prometheus API response."""


class QueryClient(Protocol):
    def query(self, expression: str) -> dict[str, Any]:
        """Evaluate one fixed PromQL instant query."""


class AmpQueryClient:
    """Small SigV4 client for AMP's Prometheus-compatible Query API."""

    def __init__(self, endpoint: str, region: str):
        self.endpoint = endpoint.rstrip("/")
        self.region = region

    def query(self, expression: str) -> dict[str, Any]:
        # Import inside the runtime path so pure response-formatting tests do not
        # need AWS SDK packages installed on the developer workstation.
        from botocore.auth import SigV4Auth
        from botocore.awsrequest import AWSRequest
        from botocore.session import get_session
        import urllib3

        session = get_session()
        credentials = session.get_credentials()
        if credentials is None:
            raise AmpQueryError("AWS credentials are unavailable")

        request = AWSRequest(
            method="POST",
            url=f"{self.endpoint}/api/v1/query",
            data=urlencode({"query": expression}),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        SigV4Auth(credentials.get_frozen_credentials(), "aps", self.region).add_auth(request)

        response = urllib3.PoolManager().request(
            "POST",
            request.url,
            headers=dict(request.headers.items()),
            body=request.body,
            timeout=urllib3.Timeout(connect=2.0, read=5.0),
            retries=False,
        )
        if response.status != 200:
            raise AmpQueryError(f"AMP query returned HTTP {response.status}")

        try:
            payload = json.loads(response.data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AmpQueryError("AMP query returned invalid JSON") from error

        if payload.get("status") != "success":
            raise AmpQueryError("AMP query did not succeed")
        return payload


def _queries(host_id: str) -> dict[str, str]:
    labels = f'host_id="{host_id}"'
    return {
        "up": f'up{{{labels},job="node-exporter"}}',
        "cpu_usage_percent": (
            "100 - (avg(rate(node_cpu_seconds_total"
            f"{{{labels},mode=\"idle\"}}[5m])) * 100)"
        ),
        "memory_usage_percent": (
            "100 * (1 - (node_memory_MemAvailable_bytes"
            f"{{{labels}}} / node_memory_MemTotal_bytes{{{labels}}}))"
        ),
        "disk_usage_percent": (
            "max(100 * (1 - (node_filesystem_avail_bytes"
            f"{{{labels},fstype!~\"tmpfs|overlay|squashfs\"}} / "
            "node_filesystem_size_bytes"
            f"{{{labels},fstype!~\"tmpfs|overlay|squashfs\"}})))"
        ),
        "load_average_5m": f"node_load5{{{labels}}}",
        "uptime_days": f"((time() - node_boot_time_seconds{{{labels}}}) / 86400)",
    }


def _first_sample(payload: dict[str, Any]) -> tuple[float | None, float | None]:
    try:
        result = payload["data"]["result"]
        value = result[0]["value"]
        return float(value[1]), float(value[0])
    except (IndexError, KeyError, TypeError, ValueError):
        return None, None


def _observed_at(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _claim_groups(event: dict[str, Any]) -> set[str]:
    """Return Cognito group names from the HTTP API JWT authorizer context."""
    claims = ((event.get("requestContext") or {}).get("authorizer") or {}).get("jwt", {}).get("claims")
    if not isinstance(claims, dict):
        return set()
    groups = claims.get("cognito:groups")
    if isinstance(groups, str):
        if groups.startswith("["):
            try:
                parsed_groups = json.loads(groups)
            except json.JSONDecodeError:
                # HTTP API may serialize an array without quoting each string
                # value (for example, [monitoring-viewer-home-server]).
                parsed_groups = [
                    group.strip().strip('"\'')
                    for group in groups.removeprefix("[").removesuffix("]").split(",")
                    if group.strip().strip('"\'')
                ]
            if isinstance(parsed_groups, list):
                return {group for group in parsed_groups if isinstance(group, str)}
        return {group.strip() for group in groups.split(",") if group.strip()}
    if isinstance(groups, list):
        return {group for group in groups if isinstance(group, str)}
    return set()


def _is_allowed_viewer(event: dict[str, Any]) -> bool:
    required_group = os.environ.get("ALLOWED_COGNITO_GROUP", "monitoring-viewer-home-server")
    groups = _claim_groups(event)
    allowed = required_group in groups
    if not allowed:
        LOGGER.warning("Cognito viewer group was not present in the JWT claims: %s", sorted(groups))
    return allowed


def build_status(host_id: str, client: QueryClient) -> dict[str, Any]:
    """Run fixed queries and turn their vector results into the public response."""
    values: dict[str, float | None] = {}
    timestamps: dict[str, float | None] = {}
    for name, expression in _queries(host_id).items():
        values[name], timestamps[name] = _first_sample(client.query(expression))

    up_value = values["up"]
    reachable = up_value == 1.0
    metrics = {name: values[name] for name in _queries(host_id) if name != "up"}
    alerts: list[str] = []
    if not reachable:
        alerts.append("host_unreachable")
    if any(value is None for value in metrics.values()):
        alerts.append("metrics_unavailable")
    if metrics["cpu_usage_percent"] is not None and metrics["cpu_usage_percent"] >= CPU_WARNING_PERCENT:
        alerts.append("cpu_usage_high")
    if metrics["memory_usage_percent"] is not None and metrics["memory_usage_percent"] >= MEMORY_WARNING_PERCENT:
        alerts.append("memory_usage_high")
    if metrics["disk_usage_percent"] is not None and metrics["disk_usage_percent"] >= DISK_WARNING_PERCENT:
        alerts.append("disk_usage_high")

    return {
        "host": host_id,
        "observed_at": _observed_at(timestamps["up"]),
        "reachable": reachable,
        **metrics,
        "alerts": alerts,
    }


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body, separators=(",", ":")),
    }


def lambda_handler(event: dict[str, Any], _context: Any, client: QueryClient | None = None) -> dict[str, Any]:
    host_id = (event.get("pathParameters") or {}).get("host_id")
    allowed_host_id = os.environ.get("ALLOWED_HOST_ID", "home-server")
    if host_id != allowed_host_id:
        return _response(404, {"code": "host_not_found"})
    if not _is_allowed_viewer(event):
        return _response(403, {"code": "forbidden"})

    try:
        query_client = client or AmpQueryClient(
            endpoint=os.environ["AMP_QUERY_ENDPOINT"],
            region=os.environ.get("AWS_REGION", "ap-northeast-1"),
        )
        return _response(200, build_status(host_id, query_client))
    except AmpQueryError as error:
        LOGGER.warning("AMP query failed: %s", error)
        return _response(502, {"code": "amp_query_failed"})
    except (KeyError, OSError):
        LOGGER.exception("Diagnostic Lambda configuration or transport failure")
        return _response(502, {"code": "amp_query_failed"})

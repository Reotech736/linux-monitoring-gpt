"""Cognito認証付きの読み取り専用MCP。既存の固定PromQL診断処理を共有する。"""

import asyncio
import os
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

import jwt
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict
from starlette.responses import JSONResponse

from status_api.app import AmpQueryClient, build_status

GROUP = "monitoring-viewer-home-server"


@dataclass(frozen=True)
class Settings:
    issuer: str
    client_id: str
    resource: str
    amp_endpoint: str
    cognito_domain: str
    region: str = "ap-northeast-1"

    @classmethod
    def from_env(cls):
        return cls(
            issuer=os.environ["COGNITO_ISSUER"],
            client_id=os.environ["COGNITO_CLIENT_ID"],
            resource=os.environ["MCP_RESOURCE_URL"],
            amp_endpoint=os.environ["AMP_QUERY_ENDPOINT"],
            cognito_domain=os.environ["COGNITO_DOMAIN_URL"],
            region=os.environ.get("AWS_REGION", "ap-northeast-1"),
        )

    def __post_init__(self):
        for value in (self.issuer, self.resource, self.amp_endpoint, self.cognito_domain):
            url = urlsplit(value)
            if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
                raise ValueError("接続先には認証情報・クエリを含まないHTTPS URLが必要です")
        if not self.resource.endswith("/mcp") or not self.client_id:
            raise ValueError("MCP URLは/mcpで終わり、専用client IDが必要です")

    @property
    def metadata_issuer(self):
        # OAuthメタデータの発行元。JWTのissは別途Cognitoの実issuerで検証する。
        return self.resource.removesuffix("mcp")

    @property
    def scope(self):
        # Cognito resource bindingではresource identifierとscopeのprefixが一致する必要がある。
        return self.resource + "/status.read"


class CognitoVerifier:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.jwks = jwt.PyJWKClient(
            settings.issuer.rstrip("/") + "/.well-known/jwks.json", timeout=5
        )

    def _verify(self, token: str) -> AccessToken | None:
        try:
            key = self.jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token, key, algorithms=["RS256"],
                issuer=self.settings.issuer, audience=self.settings.resource,
                options={"require": ["exp", "iat", "iss", "aud", "sub", "client_id", "token_use", "scope"]},
            )
            groups = claims.get("cognito:groups", [])
            scope = claims["scope"]
            if (
                claims["token_use"] != "access"
                or claims["client_id"] != self.settings.client_id
                or not isinstance(groups, list) or GROUP not in groups
                or not isinstance(scope, str) or self.settings.scope not in scope.split()
            ):
                return None
            return AccessToken(
                token=token, client_id=claims["client_id"], scopes=scope.split(),
                expires_at=claims["exp"], resource=self.settings.resource,
                subject=claims["sub"],
            )
        except (jwt.PyJWTError, ValueError, TypeError, KeyError, OSError):
            # JWTや例外本文をログに残さない。
            return None

    async def verify_token(self, token: str) -> AccessToken | None:
        return await asyncio.to_thread(self._verify, token)


class HostStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    host: Literal["home-server"]
    observed_at: str | None
    reachable: bool
    cpu_usage_percent: float | None
    memory_usage_percent: float | None
    disk_usage_percent: float | None
    load_average_5m: float | None
    uptime_days: float | None
    alerts: list[str]


class DiagnosticMCP(FastMCP):
    async def call_tool(self, name, arguments):
        if name == "getHostStatus" and set(arguments) != {"host_id"}:
            raise ToolError("入力はhost_idだけを指定してください。")
        return await super().call_tool(name, arguments)

    async def list_tools(self):
        tools = await super().list_tools()
        for tool in tools:
            tool.inputSchema["additionalProperties"] = False
        return [tool.model_copy(update={
            "securitySchemes": [{"type": "oauth2", "scopes": self.settings.auth.required_scopes}],
        }) for tool in tools]


def create_server(settings: Settings, *, verifier=None, query_client=None) -> FastMCP:
    host = urlsplit(settings.resource).netloc
    server = DiagnosticMCP(
        "Linux Server Diagnostic",
        instructions=(
            "home-serverの状態確認にはgetHostStatusを1回呼ぶ。日本語で到達状況、CPU・メモリ・"
            "最大ディスク使用率、5分ロード、稼働日数、alertsを説明する。"
            "nullは取得不能とし、監視上到達不能でもサーバ停止とは断定しない。"
            "API失敗時は状態を推測しない。警告がなくても完全正常と断定しない。"
            "別ホスト、任意クエリ、コマンド実行、サーバの変更には対応しない。"
        ),
        stateless_http=True, json_response=True,
        token_verifier=verifier or CognitoVerifier(settings),
        auth=AuthSettings(
            issuer_url=settings.metadata_issuer, resource_server_url=settings.resource,
            required_scopes=[settings.scope], validate_token_resource=True,
        ),
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[host], allowed_origins=[f"https://{host}", "https://chatgpt.com"],
        ),
    )
    client = query_client or AmpQueryClient(settings.amp_endpoint, settings.region)

    @server.custom_route("/.well-known/oauth-authorization-server", methods=["GET"])
    async def oauth_metadata(request):
        # Cognitoの実装済み機能だけを宣言する。OIDC・DCR・CIMD・RFC9207は宣言しない。
        # ログイン、コード交換、PKCE検証はCognitoが行い、本サービスは中継しない。
        domain = settings.cognito_domain.rstrip("/")
        return JSONResponse({
            "issuer": settings.metadata_issuer,
            "authorization_endpoint": domain + "/oauth2/authorize",
            "token_endpoint": domain + "/oauth2/token",
            "revocation_endpoint": domain + "/oauth2/revoke",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
            "scopes_supported": [settings.scope],
        })

    @server.tool(
        name="getHostStatus", title="Linuxサーバの状態確認",
        description="home-serverの到達状況、CPU・メモリ・ディスク使用率、5分ロード、稼働日数を取得する。変更操作は行わない。",
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
        meta={"securitySchemes": [{"type": "oauth2", "scopes": [settings.scope]}]},
    )
    async def get_host_status(host_id: Literal["home-server"]) -> HostStatus:
        try:
            result = await asyncio.to_thread(build_status, host_id, client)
            return HostStatus.model_validate(result)
        except Exception:
            # SDKに内部例外やAWS情報を返させない。
            raise ToolError("監視データを取得できません。サーバの状態は未確認です。") from None

    return server

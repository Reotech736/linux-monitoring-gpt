"""API Gateway HTTP APIからの呼び出しをASGIへ変換する。"""

from mangum import Mangum
from mcp_api.server import Settings, create_server


def lambda_handler(event, context):
    # ステートレスJSON応答のみ。SSE接続でLambdaを占有しない。
    if event.get("rawPath") == "/mcp" and event.get("requestContext", {}).get("http", {}).get("method") == "GET":
        return {"statusCode": 405, "headers": {"allow": "POST"}, "body": ""}
    # MCP session managerは再起動不可。Lambdaのwarm invocationごとに生成する。
    server = create_server(Settings.from_env())
    return Mangum(server.streamable_http_app(), lifespan="on")(event, context)

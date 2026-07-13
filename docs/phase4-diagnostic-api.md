# Phase 4: AMP診断REST API

## 目的

AMPへ任意のPromQLを渡さず、固定クエリだけを使う読み取り専用の診断APIを作成します。PoCで公開する経路は次の1つだけです。

```text
GET /hosts/home-server/status
```

API Gateway HTTP APIは`x-api-key`を読むLambda Authorizerで保護します。これはAPI Gateway標準のAPIキー機能ではなく、SSM Parameter Storeの`SecureString`と定数時間比較する共有シークレット認証です。

## レスポンス

正常時はHTTP 200と次のJSONを返します。`observed_at`はAMPが返した`up`サンプルのUTC時刻です。

```json
{
  "host": "home-server",
  "observed_at": "2026-07-13T00:00:00Z",
  "reachable": true,
  "cpu_usage_percent": 42.3,
  "memory_usage_percent": 71.5,
  "disk_usage_percent": 86.2,
  "load_average_5m": 1.24,
  "uptime_days": 18.4,
  "alerts": ["disk_usage_high"]
}
```

- CPUまたはメモリが90%以上なら`cpu_usage_high`または`memory_usage_high`を追加します。
- ディスク使用率が85%以上なら`disk_usage_high`を追加します。
- `up`が0または欠損なら`reachable`は`false`となり、`host_unreachable`を追加します。
- `up`以外の診断用メトリクスが欠損してもHTTP 200を返し、該当値を`null`、`alerts`に`metrics_unavailable`を含めます。
- 未許可ホストはHTTP 404と`{"code":"host_not_found"}`、AMP照会失敗はHTTP 502と`{"code":"amp_query_failed"}`を返します。

## デプロイ前の準備

次の操作は共有シークレットをAWSへ保存します。値をチャット、Git、シェル出力へ残さないでください。`put-parameter`は`--overwrite`を使わないため、同名パラメータが既にある場合は停止します。

```bash
read -rsp 'Phase 4 API shared secret: ' api_key
printf '\n'
aws ssm put-parameter \
  --name /linux-monitoring-gpt/poc/api-key \
  --type SecureString \
  --value "$api_key" \
  --tags \
    Key=Project,Value=linux-monitoring-gpt \
    Key=Environment,Value=poc \
    Key=ManagedBy,Value=manual \
    Key=Component,Value=diagnostic-api \
  --region ap-northeast-1 \
  --profile Reotech736
unset api_key
```

このパラメータはCloudFormation stackの外部リソースです。stack削除時には必要に応じて別途削除します。

## CloudFormation/SAMの変更対象

`infrastructure/diagnostic-api-template.yaml`は以下を作成します。

- HTTP APIとLambda Authorizer
- 診断Lambdaと、AMP workspaceの`aps:QueryMetrics`だけを許可する実行ロール
- Authorizer Lambdaと、指定SSMパラメータへの`ssm:GetParameter`だけを許可する実行ロール
- API・Lambda用の14日保持CloudWatch Logs

SSMパラメータはスタック外で手動作成するため、上記コマンドで`Project`、`Environment`、`ManagedBy`、`Component`タグを付けます。スタック名は`linux-monitoring-gpt-diagnostic-api`です。

既存のAMP stack、Prometheus Agent、ローカルPrometheus、Grafanaは変更しません。料金要因はHTTP APIリクエスト、Lambda実行、CloudWatch Logs、SSM Parameter Storeです。

## 検証・デプロイ

まずローカル検証を実行します。

```bash
python3 -m unittest discover -s lambda/tests -v
sam validate --lint --template-file infrastructure/diagnostic-api-template.yaml
sam build --template-file infrastructure/diagnostic-api-template.yaml --build-dir .aws-sam/diagnostic-api
```

AWSへ作成する前に、既存AMP stackから出力値を読み、変更セットだけを作成します。

```bash
amp_workspace_arn="$(aws cloudformation describe-stacks \
  --stack-name linux-monitoring-gpt-amp \
  --query 'Stacks[0].Outputs[?OutputKey==`WorkspaceArn`].OutputValue | [0]' \
  --output text --region ap-northeast-1 --profile Reotech736)"
amp_workspace_id="$(aws cloudformation describe-stacks \
  --stack-name linux-monitoring-gpt-amp \
  --query 'Stacks[0].Outputs[?OutputKey==`WorkspaceId`].OutputValue | [0]' \
  --output text --region ap-northeast-1 --profile Reotech736)"

sam deploy \
  --template-file .aws-sam/diagnostic-api/template.yaml \
  --stack-name linux-monitoring-gpt-diagnostic-api \
  --resolve-s3 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    "AmpWorkspaceArn=$amp_workspace_arn" \
    "AmpWorkspaceId=$amp_workspace_id" \
    'ApiKeyParameterName=/linux-monitoring-gpt/poc/api-key' \
  --region ap-northeast-1 \
  --profile Reotech736 \
  --no-execute-changeset
```

SAMの出力に表示される変更セットARNを変数へ設定し、内容を確認します。

```bash
change_set_arn='SAMの出力に表示された変更セットARN'
aws cloudformation describe-change-set \
  --change-set-name "$change_set_arn" \
  --region ap-northeast-1 \
  --profile Reotech736
```

HTTP API、Lambda 2個、IAMロール2個、CloudWatch Logs 3個、およびHTTP APIからLambdaを呼ぶためにSAMが生成するLambda権限だけが含まれることを確認してから実行します。

```bash
aws cloudformation execute-change-set \
  --change-set-name "$change_set_arn" \
  --region ap-northeast-1 \
  --profile Reotech736

aws cloudformation wait stack-create-complete \
  --stack-name linux-monitoring-gpt-diagnostic-api \
  --region ap-northeast-1 \
  --profile Reotech736
```

既存stackを更新した場合は、最後の待機コマンドを`stack-update-complete`へ読み替えます。

実行後は、stack出力の`StatusEndpoint`へ正しい`x-api-key`を指定して確認します。

```bash
status_endpoint="$(aws cloudformation describe-stacks \
  --stack-name linux-monitoring-gpt-diagnostic-api \
  --query 'Stacks[0].Outputs[?OutputKey==`StatusEndpoint`].OutputValue | [0]' \
  --output text --region ap-northeast-1 --profile Reotech736)"
read -rsp 'Phase 4 API shared secret: ' api_key
printf '\n'
curl --fail --silent --show-error \
  -H "x-api-key: $api_key" \
  "$status_endpoint"
unset api_key
```

認証ヘッダーなしではHTTP 401、`/hosts/other-host/status`ではHTTP 404になることも確認します。

## 削除

診断APIを停止する場合は、先にCustom GPTなどの利用側を無効化してから次を実行します。

```bash
aws cloudformation delete-stack \
  --stack-name linux-monitoring-gpt-diagnostic-api \
  --region ap-northeast-1 \
  --profile Reotech736
```

共有シークレットも不要になった場合だけ、SSMパラメータを削除します。既存のAMP stackは削除しません。

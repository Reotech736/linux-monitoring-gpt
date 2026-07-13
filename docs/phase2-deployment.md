# Phase 2: AMPへの転送

## 採用する構成

- AWSリージョン: `ap-northeast-1`（東京）
- AMP保持期間: 180日
- AWS Budgets: `aws-account-foundation`で作成した、アカウント全体を対象とする`aws-account-monthly-cost`（月額US$20）を利用
- 人用認証: `Reotech736`プロファイルの`aws login --remote`
- Agent認証: `linux-monitoring-gpt-agent` IAMユーザーのアクセスキー
- Agent権限: 作成したAMP workspaceへの`aps:RemoteWrite`だけ

`aws login --remote`は人がCLIでCloudFormationを実行するための一時認証です。セッションには期限があるため、常時稼働するPrometheus Agentには使いません。Agentには専用アクセスキーを使い、将来はIAM Roles Anywhereへの移行を検討します。

## 料金の前提

現在のNode Exporterでは全メトリクスを送ると約2.06億サンプル/月になります。`prometheus.amp.yml.example`の許可リストは約49時系列に絞り、30秒間隔で約423万サンプル/月を見込みます。

AWSの現行料金ページでは、AMPのFree Tierとして40Mサンプル、10GB保存、200B Query Samples Processedが案内されています。ただし、Free Tierやクレジットの適用可否はアカウント条件に依存するため、請求画面と[AMP料金ページ](https://aws.amazon.com/prometheus/pricing/)で確認してください。`aws-account-monthly-cost`は、実費50%・80%・100%および予測100%でメール通知します。このBudgetは特定プロジェクトだけでなくAWSアカウント全体を対象とし、通知のみで利用を自動停止しません。

## 1. 人用AWSプロファイルを作成する

次のコマンドは、既存の`default`プロファイルを変更せずに、人用の一時認証プロファイルを作成します。ブラウザでAWSへログインし、表示された認可コードを端末へ入力します。

```bash
aws login --remote --profile Reotech736 --region ap-northeast-1
aws sts get-caller-identity --profile Reotech736
```

`get-caller-identity`の出力で、意図したAWSアカウント・IAMユーザーまたはロールであることを確認します。rootユーザーを日常操作に使用しません。

## 2. CloudFormationを検証して作成する

この操作は、AMP workspaceとIAMユーザーを作成します。アカウント全体Budgetは`aws-account-foundation`で事前に作成します。料金要因はメトリクスの取り込み量、保存量、クエリ量です。削除時にはworkspace内の保存済みメトリクスが失われ、Agentの送信は失敗するため、先にAgentを停止または`remote_write`を外します。

まずテンプレートを検証します。

```bash
aws cloudformation validate-template \
  --template-body file://infrastructure/amp-stack.yaml \
  --region ap-northeast-1 \
  --profile Reotech736
```

次に名前付きchange setを作成します。

```bash
aws cloudformation create-change-set \
  --stack-name linux-monitoring-gpt-amp \
  --change-set-name initial-deploy \
  --change-set-type CREATE \
  --template-body file://infrastructure/amp-stack.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1 \
  --profile Reotech736

aws cloudformation wait change-set-create-complete \
  --stack-name linux-monitoring-gpt-amp \
  --change-set-name initial-deploy \
  --region ap-northeast-1 \
  --profile Reotech736

aws cloudformation describe-change-set \
  --stack-name linux-monitoring-gpt-amp \
  --change-set-name initial-deploy \
  --region ap-northeast-1 \
  --profile Reotech736
```

生成されたchange setに、`AWS::APS::Workspace`と`AWS::IAM::User`だけが含まれることを確認してから、次を実行します。

```bash
aws cloudformation execute-change-set \
  --stack-name linux-monitoring-gpt-amp \
  --change-set-name initial-deploy \
  --region ap-northeast-1 \
  --profile Reotech736

aws cloudformation wait stack-create-complete \
  --stack-name linux-monitoring-gpt-amp \
  --region ap-northeast-1 \
  --profile Reotech736
```

## 3. Agent用アクセスキーを保存する

CloudFormation出力の`AgentUserName`を確認し、AWSコンソールのIAM画面でそのユーザーのアクセスキーを1つだけ作成します。シークレットアクセスキーは表示された時点で、次の専用ファイルへ保存します。キーをターミナル、ログ、Git、`.env`に貼り付けません。人用プロファイルとAgent用プロファイルを分離するため、Agentのファイルだけを`~/.config/linux-monitoring-gpt/aws/`へ置きます。

```bash
install -d -m 700 "$HOME/.config/linux-monitoring-gpt/aws"
install -m 600 /dev/null "$HOME/.config/linux-monitoring-gpt/aws/credentials"
install -m 600 /dev/null "$HOME/.config/linux-monitoring-gpt/aws/config"
AWS_SHARED_CREDENTIALS_FILE="$HOME/.config/linux-monitoring-gpt/aws/credentials" \
AWS_CONFIG_FILE="$HOME/.config/linux-monitoring-gpt/aws/config" \
  aws configure --profile linux-monitoring-agent
```

`aws configure`の入力値には作成したアクセスキーを使います。リージョンは`ap-northeast-1`、出力形式は`json`を指定します。

人用の`~/.aws/config`と混在させないため、Agentプロファイルの確認にも同じ2つの環境変数を指定します。

```bash
AWS_SHARED_CREDENTIALS_FILE="$HOME/.config/linux-monitoring-gpt/aws/credentials" \
AWS_CONFIG_FILE="$HOME/.config/linux-monitoring-gpt/aws/config" \
  aws sts get-caller-identity \
    --profile linux-monitoring-agent \
    --region ap-northeast-1
```

出力のARNが`...:user/linux-monitoring-gpt-agent`なら正しい認証情報です。Agent用アクセスキーを`~/.aws/credentials`へ置いたり、人用の`Reotech736`プロファイルをAgentへ渡したりしません。

## 4. AgentをAMPへ接続する

CloudFormation出力の`WorkspaceId`を使い、次のように実行時設定を作成します。workspace IDは認証情報ではありませんが、環境固有のためGit管理しません。

```bash
cp home-agent/prometheus.amp.yml.example home-agent/prometheus.amp.yml
```

`home-agent/prometheus.amp.yml`の`REPLACE_WITH_WORKSPACE_ID`を、CloudFormation出力のworkspace IDへ置き換えます。

次に`home-agent/env.example`を`home-agent/.env`へコピーし、`AGENT_AWS_CREDENTIALS_FILE`中の`REPLACE_WITH_YOUR_USER`を実際のLinuxユーザー名へ置き換えます。

```bash
cp home-agent/env.example home-agent/.env
```

`AGENT_UID`と`AGENT_GID`には、`id -u`と`id -g`の出力を設定します。AgentはrootではなくこのUID/GIDで実行され、権限を`0600`に保った認証ファイルを読み取ります。

Agentを再作成し、ログとターゲットを確認します。

```bash
docker compose -f home-agent/compose.yaml up -d
docker compose -f home-agent/compose.yaml logs --tail=100 prometheus-agent
curl --fail --silent http://127.0.0.1:19090/api/v1/targets
```

Targets APIで`health`が`up`であり、ログに`remote write`、SigV4、認可のエラーがなければ、AgentからAMPへの転送を開始しています。

## 5. AMP上で確認する

Prometheus Agent modeはローカルPromQLクエリを提供しません。AMPのPrometheus互換APIをSigV4で呼び出し、次を確認します。

```promql
up{host_id="home-server"}
```

`awscurl`を一時実行できる`uvx`を使う場合は、次のコマンドで確認できます。人用の`Reotech736`プロファイルにはQuery APIの読み取り権限が必要です。初回の`uvx`実行時だけ、`awscurl`パッケージがローカルキャッシュへ取得されます。

```bash
workspace_id="$(aws cloudformation describe-stacks \
  --stack-name linux-monitoring-gpt-amp \
  --query 'Stacks[0].Outputs[?OutputKey==`WorkspaceId`].OutputValue | [0]' \
  --output text \
  --region ap-northeast-1 \
  --profile Reotech736)"

uvx --from awscurl awscurl \
  --service aps \
  --region ap-northeast-1 \
  --profile Reotech736 \
  -X POST \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'query=up%7Bhost_id%3D%22home-server%22%7D' \
  "https://aps-workspaces.ap-northeast-1.amazonaws.com/workspaces/${workspace_id}/api/v1/query"
```

レスポンス内の`"value":[...,"1"]`なら、最初のマイルストーンは達成です。今回のPoCでは`home-server`の`up=1`を確認済みです。コストの正確な請求額はCost Explorerを正とし、サービスを`Amazon Managed Service for Prometheus`で絞って確認します。取り込み量の傾向はAMPの`IngestionRate`も併せて確認します。

## 停止と削除

削除前にAgentをローカル収集設定へ戻すか停止します。続けてCloudFormation stackを削除し、Agent用アクセスキーを無効化・削除します。

```bash
docker compose -f home-agent/compose.yaml down
aws cloudformation delete-stack \
  --stack-name linux-monitoring-gpt-amp \
  --region ap-northeast-1 \
  --profile Reotech736
```

stack削除後、Agent用アクセスキーが不要になったことを確認します。既存のアカウント全体Budgetは削除しません。

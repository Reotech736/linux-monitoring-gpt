# Linux Server Monitoring GPT — Project Brief

## 目的

自宅Linuxサーバ1台の稼働状況をPrometheus形式で収集し、AWSへ安全に転送・保存するPoCです。

- 人間はローカルGrafanaで時系列を可視化する。
- Custom GPTは読み取り専用の診断APIを呼び出し、現在の状態を日本語で説明する。
- Prometheus、AWS IAM、IaC、Custom GPT Actionsを段階的に学ぶ。

Phaseごとの実装結果は[docs/progress-summary.md](docs/progress-summary.md)、導入・運用の詳細は`docs/phase*.md`を正とします。この文書は、目的・現行設計・継続して守る制約を示す基準書です。

## 現在の対象と到達点

- 監視対象は`home-server`だけです。
- Phase 6まで完了しています。招待済みユーザーがCognito OAuthで認証後、Custom GPTから対象ホストの確認とCPUを含む現在の診断結果を取得できることを確認済みです。
- 警告、監視停止、メトリクス欠損時のGPT応答は、安全な再現方法を決めてから検証します。
- 共有GPT向けの初期認可としてCognito OAuth、JWT Authorizer、`home-server`閲覧グループを運用します。複数ホスト・複数利用者のデータ分離は次段階の対象です。設計は[docs/phase6-public-access-design.md](docs/phase6-public-access-design.md)に記録しています。

## 現行構成

```text
home-server
  Node Exporter (systemd, 127.0.0.1:9100)
    ├─ Prometheus Agent (Docker Compose, 127.0.0.1:19090)
    │    └─ remote_write / SigV4 / HTTPS ──> AMP (ap-northeast-1)
    └─ Local Prometheus (Docker Compose, 172.30.0.1:19091)
         └─ Grafana (自宅LAN・Tailscaleだけに公開)

Custom GPT
  └─ Cognito OAuth
       └─ API Gateway HTTP API (JWT Authorizer)
            └─ Status Lambda (閲覧グループと固定PromQLだけを確認・実行) ──> AMP
```

## 決定済みの設計方針

| 項目 | 決定 |
| --- | --- |
| Linuxメトリクス収集 | Node Exporterをホストのsystemdサービスとして実行する |
| 転送 | Prometheus AgentをDocker Composeで実行し、30秒間隔でscrapeしてAMPへ`remote_write`する |
| AWSリージョン | `ap-northeast-1`（東京） |
| AMP保持期間 | 180日 |
| IaC | AMPとIAMユーザーはCloudFormation、診断APIはAWS SAM / CloudFormation |
| 人用AWS認証 | `Reotech736`プロファイルの一時認証 |
| Agent用AWS認証 | 専用IAMユーザー`linux-monitoring-gpt-agent`。対象AMP workspaceへの`aps:RemoteWrite`だけを許可 |
| 診断API | `GET /hosts/home-server/status`だけを公開し、Cognito OAuthのスコープと閲覧グループで認可する |
| GPT | [Linux Server Diagnostic GPT](https://chatgpt.com/g/g-6a53c4cf774481919948ee509a3e6cda-linux-server-diagnostic-gpt)をActionとして利用する |
| アカウント全体のコスト通知 | `aws-account-monthly-cost`、月額US$20。特定プロジェクトだけでなくAWSアカウント全体が対象 |

## セキュリティと運用上の制約

- Node Exporter、Prometheus Agent、Local Prometheusをインターネットへ公開しない。Grafanaは自宅LANとTailscaleだけで利用する。
- 自宅側からAWSへの通信は、Agentによる外向きHTTPSだけを使う。AWSから自宅サーバを直接scrapeしない。
- IAMは最小権限とし、Agentの書き込み権限と診断APIの読み取り権限を分離する。
- 診断APIは読み取り専用とする。任意のPromQL、シェルコマンド、任意のホスト名を外部入力として受け付けない。
- OAuth Client Secret、AWSアクセスキー、`.env`の実値、Prometheus実データ、ログをGitへコミットしない。
- AWSリソースを作成・変更・削除する前に、対象、料金要因、必要なIAM権限、削除方法を説明して確認を得る。
- GPTをリンク共有する場合はプライバシーポリシーを設定し、Cognitoで招待した利用者だけに共有する。

## 次の拡張候補

1. 異常・欠損時のCustom GPT応答を安全に検証する。
2. 複数ホスト・複数利用者を扱うための認可、データ分離、ホスト登録・失効を設計する。
3. Abuse対策、料金上限、公開可能なセットアップ手順を整備する。

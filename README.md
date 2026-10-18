# Linux Server Monitoring

自宅Linuxサーバの状態をPrometheus形式で収集し、AWSへ安全に転送・保存するPoCです。ChatGPTでは、読み取り専用MCPプラグインを通じてサーバ状態を日本語で説明します。

目的、現行設計、運用上の制約は [PROJECT_BRIEF.md](PROJECT_BRIEF.md) を参照してください。Phaseごとの実装結果と未検証項目は [docs/progress-summary.md](docs/progress-summary.md) にまとめています。

## 現在のステータス

2026-10-18追記：ブラウザ版ChatGPTに`Linux Server Monitoring`プラグインを登録し、
Cognito OAuth認証、MCPの初期化・ツール検出、`getHostStatus`によるAMP実データ取得まで確認しました。
旧登録`Linux Monitoring MCP`はアンインストール済みですが、ChatGPT側のHTTP 409不具合により削除待ちです。
設計・認証・公開手順は[プラグイン移行](docs/plugin-mcp-migration.md)を参照してください。
従来のCustom GPTは利用を終了し、AWS側の旧REST APIと専用OAuthリソースを削除しました。
共有Cognito基盤は現行MCPの認証に引き続き利用します。

Phase 6（共有GPT向けOAuth認可）まで完了しています。Node Exporterを`127.0.0.1:9100`でsystemdサービスとして実行し、Docker Compose上のPrometheus Agentが収集したメトリクスを、東京リージョンのAmazon Managed Service for Prometheus（AMP）へ転送しています。AMPのQuery APIで`up{host_id="home-server"}`が`1`になることを確認済みです。

NucBoxG5上の通常PrometheusとGrafanaを使い、Grafanaだけを自宅LANとTailscaleへ公開しています。Prometheus・Node Exporter・Prometheus Agentは公開しません。AMPを固定PromQLで照会する読み取り専用MCPは、Cognito OAuthのアクセストークン、専用スコープ、対象ユーザーを検証します。ChatGPTの`Linux Server Monitoring`から、`home-server`の到達状況、CPU・メモリ・ディスク使用率、ロード、稼働時間、アラートを日本語で取得できます。

公開文書の入口は [GitHub Pages](https://reotech736.com/linux-monitoring-gpt/) です。プラグインの公開・共有時には [プライバシーポリシー](https://reotech736.com/linux-monitoring-gpt/privacy-policy.html) を参照します。

最初のマイルストーンは、自宅LinuxサーバのNode ExporterをPrometheus Agentが収集し、Amazon Managed Service for Prometheus（AMP）上で `up` メトリクスを確認することです。

## 初期構成方針

```text
Linuxホスト（systemd）
  Node Exporter
    └─ 127.0.0.1:9100

Docker（host network）
  Prometheus Agent
    └─ Node Exporterをscrape
    └─ AMPへremote_write（SigV4署名）
```

- Node Exporterはホスト全体を自然に観測できるよう、systemdサービスとして実行します。
- Prometheus Agentは設定を再現しやすくするため、Docker Composeで実行します。
- Node Exporter、Prometheus、Grafanaのポートをインターネットへ公開しません。
- AWSリソースを作成する前に、対象、料金要因、IAM権限、削除方法を確認します。

## ディレクトリ

| パス | 用途 |
| --- | --- |
| `docs/` | 構成・セットアップ・運用ドキュメント |
| `home-agent/` | Prometheus AgentのCompose設定とPrometheus設定 |
| `local-observability/` | ローカルPrometheus・GrafanaのCompose、設定、ダッシュボード |
| `infrastructure/` | AWSリソースのIaC |
| `lambda/` | MCP Lambda、共有する診断整形処理、テスト |
| `lambda/mcp_api/` | プラグイン向け認証付きMCP Lambda |
| `grafana/dashboards/` | Grafanaダッシュボード定義 |

## Phase 1の設定

ローカル収集の構成と導入・検証手順は [docs/phase1-local-collection.md](docs/phase1-local-collection.md) を参照してください。Prometheus Agentの設定は `home-agent/` にあります。

## Phase 2の設計

AMPへの転送、IAM、料金、IaCの設計方針は [docs/phase2-amp-design.md](docs/phase2-amp-design.md) を参照してください。

Phase 2の具体的な認証、CloudFormation、Agent接続、削除手順は [docs/phase2-deployment.md](docs/phase2-deployment.md) を参照してください。AWSリソースを作成する前に、対象、料金要因、IAM権限、削除方法を確認します。

## Phase 3のローカル可視化

ローカルPrometheus・Grafanaの構成、LAN/Tailscale公開、起動・停止・検証手順は [docs/phase3-local-visualization.md](docs/phase3-local-visualization.md) を参照してください。

## MCPプラグイン

AMPを固定PromQLで読み取り、Cognito OAuthで保護されたMCPとしてChatGPTへ提供します。
構成、認証、デプロイ、接続手順は[プラグイン移行](docs/plugin-mcp-migration.md)を参照してください。
共有Cognito基盤は`infrastructure/shared-auth-template.yaml`、MCP本体は
`infrastructure/mcp-template.yaml`で管理します。

## 進め方

各段階で、概念の説明、設定変更、検証方法、費用・セキュリティ上の注意点をセットで確認します。AWSリソースの作成や削除、外部サービスの変更は、事前に内容を説明して確認を得てから行います。

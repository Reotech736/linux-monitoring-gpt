# Linux Server Monitoring GPT

自宅Linuxサーバの状態をPrometheus形式で収集し、AWSへ安全に転送・保存するPoCです。最終的には、診断用REST APIを経由してカスタムGPTがサーバ状態を日本語で説明できるようにします。

目的、現行設計、運用上の制約は [PROJECT_BRIEF.md](PROJECT_BRIEF.md) を参照してください。Phaseごとの実装結果と未検証項目は [docs/progress-summary.md](docs/progress-summary.md) にまとめています。

## 現在のステータス

Phase 6（共有GPT向けOAuth認可）まで完了しています。Node Exporterを`127.0.0.1:9100`でsystemdサービスとして実行し、Docker Compose上のPrometheus Agentが収集したメトリクスを、東京リージョンのAmazon Managed Service for Prometheus（AMP）へ転送しています。AMPのQuery APIで`up{host_id="home-server"}`が`1`になることを確認済みです。

NucBoxG5上の通常PrometheusとGrafanaを使い、Grafanaだけを自宅LANとTailscaleへ公開しています。Prometheus・Node Exporter・Prometheus Agentは公開しません。AMPを固定PromQLで照会する読み取り専用APIは、Cognito OAuthのアクセストークンとホスト閲覧グループを検証してからJSONの診断結果を返します。このAPIをActionとして登録した[Linux Server Diagnostic GPT](https://chatgpt.com/g/g-6a53c4cf774481919948ee509a3e6cda-linux-server-diagnostic-gpt)から、`home-server`の現在の状態とCPU使用率を日本語で取得できることを確認しました。

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
| `lambda/` | 診断用API Lambdaとテスト |
| `grafana/dashboards/` | Grafanaダッシュボード定義 |
| `custom-gpt/` | Actions用OpenAPIスキーマとInstructions |

## Phase 1の設定

ローカル収集の構成と導入・検証手順は [docs/phase1-local-collection.md](docs/phase1-local-collection.md) を参照してください。Prometheus Agentの設定は `home-agent/` にあります。

## Phase 2の設計

AMPへの転送、IAM、料金、IaCの設計方針は [docs/phase2-amp-design.md](docs/phase2-amp-design.md) を参照してください。

Phase 2の具体的な認証、CloudFormation、Agent接続、削除手順は [docs/phase2-deployment.md](docs/phase2-deployment.md) を参照してください。AWSリソースを作成する前に、対象、料金要因、IAM権限、削除方法を確認します。

## Phase 3のローカル可視化

ローカルPrometheus・Grafanaの構成、LAN/Tailscale公開、起動・停止・検証手順は [docs/phase3-local-visualization.md](docs/phase3-local-visualization.md) を参照してください。

## Phase 4の診断API

AMPを固定PromQLで読み取り、診断用JSONへ整形するAPIの設計・検証・デプロイ手順は [docs/phase4-diagnostic-api.md](docs/phase4-diagnostic-api.md) を参照してください。認証はPhase 6でCognito OAuthへ移行済みです。

## Phase 5のCustom GPT連携

Custom GPT Actions用のOpenAPIスキーマ、Instructions、ChatGPT画面での安全な設定・テスト手順は [docs/phase5-custom-gpt-actions.md](docs/phase5-custom-gpt-actions.md) を参照してください。

## Phase 6の共有GPT向け認可

リンク共有時に利用者ごとの認可へ移行する設計と、AWSリソースを作成する前に確認する内容は [docs/phase6-public-access-design.md](docs/phase6-public-access-design.md) を参照してください。

## 進め方

各段階で、概念の説明、設定変更、検証方法、費用・セキュリティ上の注意点をセットで確認します。AWSリソースの作成や削除、外部サービスの変更は、事前に内容を説明して確認を得てから行います。

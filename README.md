# Linux Server Monitoring GPT

自宅Linuxサーバの状態をPrometheus形式で収集し、AWSへ安全に転送・保存するPoCです。最終的には、診断用REST APIを経由してカスタムGPTがサーバ状態を日本語で説明できるようにします。

詳細な背景、設計方針、段階的な計画は [PROJECT_BRIEF.md](PROJECT_BRIEF.md) を参照してください。

## 現在のステータス

Phase 0（リポジトリ初期化）は完了しています。次はPhase 1として、自宅Linux上でNode ExporterとPrometheus Agentによるローカル収集を検証します。AWSリソース、認証情報、デプロイ済みコンポーネントはまだありません。

最初のマイルストーンは、自宅LinuxサーバのNode ExporterをPrometheus Agentが収集し、Amazon Managed Service for Prometheus（AMP）上で `up` メトリクスを確認することです。

## 初期構成方針

```text
Linuxホスト（systemd）
  Node Exporter
    └─ 127.0.0.1:9100

Docker（host network）
  Prometheus Agent
    └─ Node Exporterをscrape
    └─ 将来AMPへremote_write
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
| `infrastructure/` | AWSリソースのIaC |
| `lambda/` | 診断用API Lambdaとテスト |
| `grafana/dashboards/` | Grafanaダッシュボード定義 |
| `custom-gpt/` | Actions用OpenAPIスキーマとInstructions |

## 進め方

各段階で、概念の説明、設定変更、検証方法、費用・セキュリティ上の注意点をセットで確認します。AWSリソースの作成や削除、外部サービスの変更は、事前に内容を説明して確認を得てから行います。

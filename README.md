# Linux Server Monitoring GPT

自宅Linuxサーバの状態をPrometheus形式で収集し、AWSへ安全に転送・保存するPoCです。最終的には、診断用REST APIを経由してカスタムGPTがサーバ状態を日本語で説明できるようにします。

詳細な背景、設計方針、段階的な計画は [PROJECT_BRIEF.md](PROJECT_BRIEF.md) を参照してください。

## 現在のステータス

Phase 2（AMPへの転送）まで完了しています。Node Exporterを`127.0.0.1:9100`でsystemdサービスとして実行し、Docker Compose上のPrometheus Agentが収集したメトリクスを、東京リージョンのAmazon Managed Service for Prometheus（AMP）へ転送しています。AMPのQuery APIで`up{host_id="home-server"}`が`1`になることを確認済みです。

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
| `infrastructure/` | AWSリソースのIaC |
| `lambda/` | 診断用API Lambdaとテスト |
| `grafana/dashboards/` | Grafanaダッシュボード定義 |
| `custom-gpt/` | Actions用OpenAPIスキーマとInstructions |

## Phase 1の設定

ローカル収集の構成と導入・検証手順は [docs/phase1-local-collection.md](docs/phase1-local-collection.md) を参照してください。Prometheus Agentの設定は `home-agent/` にあります。

## Phase 2の設計

AMPへの転送、IAM、料金、IaCの設計方針は [docs/phase2-amp-design.md](docs/phase2-amp-design.md) を参照してください。

Phase 2の具体的な認証、CloudFormation、Agent接続、削除手順は [docs/phase2-deployment.md](docs/phase2-deployment.md) を参照してください。AWSリソースを作成する前に、対象、料金要因、IAM権限、削除方法を確認します。

## 進め方

各段階で、概念の説明、設定変更、検証方法、費用・セキュリティ上の注意点をセットで確認します。AWSリソースの作成や削除、外部サービスの変更は、事前に内容を説明して確認を得てから行います。

# 実装進捗サマリー

## 現在地

Phase 6まで完了しています。自宅LinuxホストのメトリクスをAWSへ転送・保存し、ローカルGrafanaと、Cognito OAuthで認証されたCustom GPTの両方から状態を確認できます。

```text
home-server
  Node Exporter (systemd, 127.0.0.1:9100)
    ├─ Prometheus Agent (Docker Compose) ──remote_write──> AMP (東京)
    └─ Prometheus (Docker Compose) ──> Grafana (LAN/Tailscaleのみ)

Custom GPT
  └─ Cognito OAuth ──> API Gateway JWT Authorizer + Lambda ──固定PromQL──> AMP
```

## Phase別の結果

| Phase | 内容 | 結果 |
| --- | --- | --- |
| 0 | リポジトリ、Git除外、基本ドキュメントの整備 | 完了 |
| 1 | Node Exporterをsystemdで、Prometheus AgentをDocker Composeで稼働 | 完了。Exporterは`127.0.0.1:9100`だけで待受 |
| 2 | AMP workspace、最小権限の書き込みIAM、remote write | 完了。`up{host_id="home-server"}`が`1`を確認 |
| 3 | ローカルPrometheusとGrafana | 完了。GrafanaのみLAN/Tailscaleから利用可能 |
| 4 | AMPを読む診断REST API | 完了。`GET /hosts/home-server/status`だけを公開し、共有シークレットで保護 |
| 5 | Custom GPT Action | 正常系を完了。`home-server`の対象確認とCPU状態の日本語回答を確認 |
| 6 | 共有GPT向けOAuth認可 | 完了。招待ユーザーのOAuthログイン後、Custom GPTから`home-server`の監視値を取得 |

## 実環境の確認記録

2026-07-14に、次の状態を確認しました。

- CloudFormation stack `linux-monitoring-gpt-amp`は`CREATE_COMPLETE`。
- SAM/CloudFormation stack `linux-monitoring-gpt-diagnostic-api`は`UPDATE_COMPLETE`。
- アカウント全体Budget `aws-account-monthly-cost`は月額US$20、`HEALTHY`。
- Prometheus Agent、ローカルPrometheus、Grafanaの各コンテナは稼働中。
- 診断API stackはCognito OAuthを有効化済み。未認証の`GET /hosts/home-server/status`がHTTP 401で拒否されることを確認。
- 招待済みの`monitoring-viewer-home-server`所属ユーザーでOAuthログインし、Custom GPTからHTTP 200の監視データを取得。確認時のCPU使用率は約6.6%だった。

この記録は確認時点のスナップショットです。日常の状態確認はGrafana、Custom GPT、AWSコンソールまたはAWS CLIで行います。

## セキュリティ上の整理

- Node Exporter、Prometheus、Prometheus Agentはインターネットへ公開しない。
- Grafanaは自宅LANとTailscaleだけで利用する。
- 診断APIはインターネットから到達可能だが、Cognito JWT Authorizerがアクセストークンと`linux-monitoring/status.read`スコープを検証する。Lambdaはさらに`monitoring-viewer-home-server`グループを確認する。
- APIは固定された`home-server`の固定PromQLだけを扱い、任意のホスト名、PromQL、シェルコマンドは受け付けない。
- OAuth Client SecretはChatGPTのAction認証設定だけで管理し、Gitには保存しない。旧共有シークレットはロールバック用として一時的にSSM Parameter Storeへ残している。

## 現在の利用方法

- 詳細な時系列やダッシュボードはローカルGrafanaで確認する。
- 簡潔な自然言語の状態確認は [Linux Server Diagnostic GPT](https://chatgpt.com/g/g-6a53c4cf774481919948ee509a3e6cda-linux-server-diagnostic-gpt) で行う。
- GPTをリンク共有する場合は、[プライバシーポリシー](privacy-policy.md)を登録済みにし、信頼できる人だけに共有する。

## 次に残る確認・拡張

- 警告、監視停止、メトリクス欠損時にGPTが推測せず適切に説明することを安全な再現方法で確認する。
- 旧Lambda AuthorizerとSSM共有シークレットを削除する前に、OAuth経由の正常系・拒否系を追加検証する。
- 複数利用者・複数ホストを扱う場合の認可、データ分離、料金上限、Abuse対策を設計する。

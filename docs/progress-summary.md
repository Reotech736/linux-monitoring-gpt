# 実装進捗サマリー

## 現在地

2026-10-18追記：ブラウザ版ChatGPTに`Linux Server Monitoring`をカスタムMCPサーバーとして登録し、
Cognito OAuth認証、MCP初期化、ツール検出、`getHostStatus`によるAMP実データ取得まで確認した。
旧登録はアンインストール済みだが、ChatGPT側のHTTP 409競合により削除待ち。
旧Custom GPTは2026年12月11日の退役後に消えたことを確認する。[移行作業](plugin-mcp-migration.md)を参照。

Phase 6とMCPプラグイン移行まで完了しています。自宅LinuxホストのメトリクスをAWSへ転送・保存し、ローカルGrafanaと、Cognito OAuthで認証されたChatGPTプラグインの両方から状態を確認できます。

```text
home-server
  Node Exporter (systemd, 127.0.0.1:9100)
    ├─ Prometheus Agent (Docker Compose) ──remote_write──> AMP (東京)
    └─ Prometheus (Docker Compose) ──> Grafana (LAN/Tailscaleのみ)

ChatGPT plugin
  └─ Cognito OAuth ──> API Gateway + MCP Lambda ──固定PromQL──> AMP
```

## Phase別の結果

| Phase | 内容 | 結果 |
| --- | --- | --- |
| 0 | リポジトリ、Git除外、基本ドキュメントの整備 | 完了 |
| 1 | Node Exporterをsystemdで、Prometheus AgentをDocker Composeで稼働 | 完了。Exporterは`127.0.0.1:9100`だけで待受 |
| 2 | AMP workspace、最小権限の書き込みIAM、remote write | 完了。`up{host_id="home-server"}`が`1`を確認 |
| 3 | ローカルPrometheusとGrafana | 完了。GrafanaのみLAN/Tailscaleから利用可能 |
| 4 | AMPを読む診断REST API | 完了。`GET /hosts/home-server/status`だけを公開する読み取り専用APIを実装。認証はPhase 6でOAuthへ移行済み |
| 5 | Custom GPT Action | 正常系を完了。`home-server`の対象確認とCPU状態の日本語回答を確認 |
| 6 | 共有GPT向けOAuth認可 | 完了。招待ユーザーのOAuthログイン後、Custom GPTから`home-server`の監視値を取得 |
| 移行 | ChatGPTプラグイン向けMCP | 完了。OAuth接続、ツール検出、実データ取得を確認 |

## 実環境の確認記録

2026-07-14に、次の状態を確認しました。

- CloudFormation stack `linux-monitoring-gpt-amp`は`CREATE_COMPLETE`。
- SAM/CloudFormation stack `linux-monitoring-gpt-diagnostic-api`は`UPDATE_COMPLETE`。
- アカウント全体Budget `aws-account-monthly-cost`は月額US$20、`HEALTHY`。
- Prometheus Agent、ローカルPrometheus、Grafanaの各コンテナは稼働中。
- 診断API stackはCognito OAuthを有効化済み。未認証の`GET /hosts/home-server/status`がHTTP 401で拒否されることを確認。
- 招待済みの`monitoring-viewer-home-server`所属ユーザーでOAuthログインし、Custom GPTからHTTP 200の監視データを取得。確認時のCPU使用率は約6.6%だった。

2026-10-18に、`Linux Server Monitoring`プラグインからCPU、メモリ、最大ディスク使用率、
5分ロード、稼働時間、アラートを取得できることを確認しました。

これらは確認時点のスナップショットです。日常の状態確認はGrafana、ChatGPTプラグイン、AWSコンソールまたはAWS CLIで行います。

## セキュリティ上の整理

- Node Exporter、Prometheus、Prometheus Agentはインターネットへ公開しない。
- Grafanaは自宅LANとTailscaleだけで利用する。
- MCPはインターネットから到達可能だが、Lambdaがアクセストークンの署名、issuer、audience、専用client ID、MCP専用scopeを検証する。Cognitoがグループクレームを省略する実環境では、設定した単一ユーザーの不変な`sub`も照合する。
- APIは固定された`home-server`の固定PromQLだけを扱い、任意のホスト名、PromQL、シェルコマンドは受け付けない。
- OAuth Client SecretはChatGPTのプラグイン認証設定だけで管理し、Gitには保存しない。

## 現在の利用方法

- 詳細な時系列やダッシュボードはローカルGrafanaで確認する。
- 簡潔な自然言語の状態確認はChatGPTの`Linux Server Monitoring`プラグインで行う。
- プラグインを共有する場合は、[プライバシーポリシー](privacy-policy.md)を登録済みにし、信頼できる人だけに共有する。

## 次に残る確認・拡張

- **Phase 7: 異常系の検証**。警告、監視停止、メトリクス欠損時にGrafanaとGPTが推測せず適切に説明することを、安全な再現方法で確認する。
- **Phase 8: メトリクスと可視化の拡張**。systemd、Docker、ディスクI/O、ネットワーク、温度などから必要な指標を選び、収集・Grafana・固定PromQL APIを段階的に拡張する。
- **Phase 9: 通知と運用**。到達不能、ディスク逼迫、高負荷の通知、料金と保持期間の定期確認を追加する。
- **Phase 10: 複数ホスト**。利用者・閲覧可能ホストの対応を設計してから、認可とデータ分離を保ったまま対象を増やす。

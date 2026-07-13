---
title: Linux Server Monitoring GPT
---

# Linux Server Monitoring GPT

自宅Linuxサーバのメトリクスを収集し、Amazon Managed Service for Prometheus（AMP）へ保存する個人運用のPoCです。ローカルGrafanaで時系列を確認し、招待済みCognitoユーザーはCustom GPTから現在の状態を確認できます。

## 現在の構成

- Node Exporter: `home-server`のsystemdサービス。`127.0.0.1:9100`だけで待受
- Prometheus Agent: Docker Composeで稼働し、AMP（東京リージョン）へ外向きHTTPSで転送
- Grafana: 自宅LANとTailscaleだけで公開
- Custom GPT: Cognito OAuth、JWTスコープ、ホスト閲覧グループで認可された読み取り専用APIを利用

## 公開文書

- [プライバシーポリシー](privacy-policy.html)
- [実装進捗サマリー](progress-summary.html)
- [プロジェクトリポジトリ](https://github.com/Reotech736/linux-monitoring-gpt)

## アクセス上の注意

診断APIはインターネットから到達可能ですが、管理者が招待したCognitoユーザーだけが利用できます。監視対象の状態を見せるべきでない人へ、Custom GPTや認証情報を共有しないでください。

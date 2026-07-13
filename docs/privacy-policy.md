---
title: Linux Server Diagnostic GPT プライバシーポリシー
---

# Linux Server Diagnostic GPT プライバシーポリシー

施行日: 2026-07-13

## 概要

Linux Server Diagnostic GPTは、個人運用の監視アシスタントです。読み取り専用の診断APIを通じて、自己管理するLinuxサーバ1台の現在の稼働状況を取得し、日本語で説明します。

## 処理するデータ

Actionを利用するとき、サービスは次のサーバ監視データを処理します。

- サーバ到達可否
- CPU、メモリ、ディスクの使用率
- ロードアベレージ、稼働時間、メトリクスの観測時刻
- サービスの運用と保護に必要なAPIリクエストのメタデータ

Actionはシェルアクセスを提供せず、サーバ上でコマンドを実行せず、サーバ設定を変更せず、任意のPromQLクエリも受け付けません。

## 利用目的と共有

データは監視対象サーバの現在の状態を取得・説明する目的だけに使用します。サービスはChatGPTからActionを呼び出し、AWSのAPI Gateway、Lambda、Amazon Managed Service for Prometheus、Systems Manager Parameter Store、CloudWatch Logsを用いて認証と処理を行います。

診断APIはCognito OAuthによる利用者ごとのアクセストークンで保護されています。OAuth Client SecretとアクセストークンはAPIレスポンス、ソースコード、アプリケーションログには含めません。

## 保持期間

- AMPの監視メトリクスは180日間保持します。
- 診断API用に作成するCloudWatch Logsは14日間保持します。
- 診断APIは、利用者プロフィール、アカウント識別子、利用者が入力した自由文を意図して収集しません。

## セキュリティとアクセス

APIは読み取り専用であり、固定された監視対象`home-server`だけを受け付けます。アクセスには管理者が招待したCognitoユーザーとしてのサインインと、対象ホストの閲覧権限が必要です。完全な安全を保証する手段はないため、監視対象サーバの状態を見せるべきでない人へGPTまたはそのアクセス資格情報を共有しないでください。

## 改定と問い合わせ先

このポリシーはサービス変更時に改定することがあります。最新版はこのURLで公開します。

このポリシーに関する質問や要望は、[linux-monitoring-gptリポジトリ](https://github.com/Reotech736/linux-monitoring-gpt/issues)のIssueで受け付けます。

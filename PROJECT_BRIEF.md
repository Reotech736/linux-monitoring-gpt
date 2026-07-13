# Linux Server Monitoring GPT — Project Brief

## 1. この資料の目的

この文書は、ChatGPTのブラウザ上で検討した内容をCodex CLIへ引き継ぐためのプロジェクト概要である。

Codex CLIは、作業開始前にこの文書を読み、目的・決定事項・制約・未決定事項を把握すること。未決定事項を勝手に確定せず、必要に応じて選択肢と推奨案を提示すること。

## 2. プロジェクト概要

自宅Linuxサーバの稼働状況をPrometheus形式で収集し、AWSへ安全に転送・保存する。人間はGrafanaで可視化し、カスタムGPTからはAWS上の診断用REST APIを呼び出して、Linuxサーバの状態を日本語で説明できるようにする。

学習目的も重視する。

- PrometheusとExporterの役割を理解する
- pull型収集と`remote_write`による転送を理解する
- AWSのマネージド監視サービス、IAM、Lambda、API Gatewayを学ぶ
- Infrastructure as Code（IaC）とGitによる構成管理を実践する
- カスタムGPT Actionsと外部API連携を学ぶ

## 3. 目標とする利用イメージ

利用者がカスタムGPTに次のように質問する。

> 自宅Linuxサーバの状態を確認して

カスタムGPTはAWS上の診断用REST APIへ問い合わせ、返されたJSONを基に次のような説明を返す。

> サーバは稼働しています。CPU負荷とメモリ使用率は正常範囲ですが、ディスク使用率が86%です。不要なDockerイメージやビルドキャッシュの確認を推奨します。

将来的にはカスタムGPTを公開し、利用時に診断対象ホストを選択できる仕組みも検討する。ホスト側に導入する収集構成はGitHubで公開可能な形を目指す。ただし、PoCではまず自分のLinuxサーバ1台を対象とする。

## 4. 現時点の基本構成

```text
自宅Linuxサーバ
  Node Exporter
      ↓ ローカルのPrometheus Agentがpull（scrape）
  Prometheus Agent
      ↓ remote_write（外向きHTTPS、AWS認証）

AWS
  Amazon Managed Service for Prometheus（AMP）
      └─ Lambda（PromQLで問い合わせ、診断用JSONを生成）
              ↑
         API Gateway（HTTPS、認証）
              ↑
         カスタムGPT Actions
              ↓
         LLMが日本語で状態を説明

自宅Linuxサーバ
  通常Prometheus（ローカル保存・PromQL検索）
      └─ Grafana（LAN/Tailscale経由の人間向け可視化）
```

### 通信方向に関する重要事項

- AWS上のPrometheusが自宅Linuxサーバを直接スクレイピングする構成ではない。
- 自宅Linuxサーバ上のPrometheus AgentがNode Exporterをローカルでスクレイピングする。
- Prometheus Agentが収集結果をAMPへ`remote_write`する。
- 自宅ルーターでNode Exporterの`9100`やPrometheusの`9090`をインターネット公開しない。
- 自宅側からAWSへの外向きHTTPS通信を利用する。
- Prometheus AgentはVPNやトンネルではなく、設定されたメトリクスを外向きに転送する収集コンポーネントである。

## 5. コンポーネントの役割

| 場所 | コンポーネント | 役割 |
| --- | --- | --- |
| 自宅Linux | Node Exporter | CPU、メモリ、ディスク、ロードアベレージ、稼働時間などを`/metrics`で公開 |
| 自宅Linux | Prometheus Agent | Exporterをpullし、ラベル付与・絞り込みを行ってAMPへ`remote_write` |
| AWS | AMP | メトリクスの保存、PromQLによる検索 |
| 自宅Linux | Local Prometheus | Node Exporterを保存・PromQL検索し、Grafanaへ提供 |
| 自宅Linux | Grafana | Local Prometheusをデータソースとしてダッシュボード表示。LAN/Tailscaleだけへ公開 |
| AWS | Lambda | AMPへ限定されたPromQLを実行し、診断用JSONへ整形 |
| AWS | API Gateway | カスタムGPTから呼び出せるHTTPS APIを提供 |
| ChatGPT | カスタムGPT Actions | OpenAPIスキーマに基づいて診断用APIを呼び出す |
| ChatGPT | LLM | APIレスポンスを日本語で説明し、必要に応じて対処案を提示 |

## 6. Prometheusの設計方針

### ExporterからAMPへ直接送信しない理由

Node Exporterなど一般的なExporterは、メトリクスを公開して待つ役割であり、通常は`remote_write`を担当しない。収集間隔、再送、キュー、認証、TLS、ラベル操作、不要メトリクスの除外は収集Agentへ集約する。

### 採用する方式

```text
Node Exporter --pull--> Prometheus Agent --remote_write--> AMP
```

### 最初に収集する候補

- 対象の生存状態
- CPU使用率
- メモリ使用率
- ディスク使用率・空き容量
- ロードアベレージ
- 稼働時間
- 必要に応じてネットワーク送受信量

PoCでは送信メトリクスとラベルを絞り、料金と情報漏えいリスクを抑える。ホスト名、内部IP、ユーザー名、ファイルパスなどが不要にラベルへ含まれないか確認する。

## 7. カスタムGPT連携方針

### AMPへ直接接続させない

カスタムGPTからAMPへ直接接続する構成は採用しない。AMPの問い合わせにはIAMやSigV4認証が関係し、自由なPromQLを外部から実行可能にするのも避けたい。

カスタムGPTは、API Gateway経由で読み取り専用の診断APIだけを呼び出す。

### API案

```http
GET /hosts/{host_id}/status
GET /hosts/{host_id}/history?range=1h
```

PoCでは`status`だけから開始してもよい。Lambda側でPromQLを固定または許可リスト化し、クライアントから任意のPromQLを受け付けない。

### レスポンス例

```json
{
  "host": "home-server",
  "observed_at": "2026-07-12T16:00:00+09:00",
  "reachable": true,
  "cpu_usage_percent": 42.3,
  "memory_usage_percent": 71.5,
  "disk_usage_percent": 86.2,
  "load_average_5m": 1.24,
  "uptime_days": 18.4,
  "alerts": [
    "disk_usage_high"
  ]
}
```

LLMに判断を完全依存させず、明確な閾値判定やアラートコードは可能な範囲でAPI側でも生成する。LLMは主に説明、要約、追加確認項目の提案を担当する。

## 8. セキュリティ方針

- Node Exporter、Prometheus、Grafanaのポートを自宅からインターネットへ直接公開しない。
- 自宅からAWSへの通信はHTTPSを使用する。
- AMPへの書き込み権限と読み取り権限を分離し、最小権限のIAMを適用する。
- LambdaにはAMPのクエリに必要な読み取り権限だけを付与する。
- カスタムGPT用APIには認証を設ける。
- 診断APIは読み取り専用とし、サーバ上でコマンドを実行する機能はPoCに含めない。
- 任意のPromQL、シェルコマンド、ホスト名を無制限に受け付けない。
- ログへ認証情報や機微なメトリクスを出力しない。
- カスタムGPTを公開する場合、共通APIキーだけで利用者ごとのホストへアクセスできる設計は避ける。公開範囲と認可方式は別途設計する。

## 9. Gitで管理するもの

- 自宅Linux側のDocker Composeまたはsystemd設定
- Prometheus Agentの設定
- AWSリソースのIaC
- Lambdaのソースコードとテスト
- API GatewayおよびOpenAPIスキーマ
- Grafanaダッシュボード定義
- カスタムGPT用のInstructions案
- 構成図、セットアップ手順、運用手順

Prometheusの実データはGitで管理しない。

### Gitへコミットしないもの

- AWSアクセスキー、シークレットキー、セッショントークン
- APIキー、OAuthクライアントシークレット
- `.env`の実値
- 秘密鍵、証明書の秘密鍵
- Prometheusの実データ
- Terraformを採用した場合のstateファイル
- 個人情報や社内限定情報を含むログ

秘密情報はIAMロール、AWS Secrets Manager、SSM Parameter Store、ローカルの権限制限された設定ファイルなどへ分離する。

## 10. 想定リポジトリ構成

これは初期案であり、採用ツール決定後にCodex CLIと調整する。

```text
linux-monitoring-gpt/
├── README.md
├── PROJECT_BRIEF.md
├── AGENTS.md
├── .gitignore
├── docs/
│   └── architecture.md
├── home-agent/
│   ├── compose.yaml
│   ├── prometheus.yml
│   └── env.example
├── infrastructure/
│   └── ...
├── lambda/
│   ├── ...
│   └── tests/
├── grafana/
│   └── dashboards/
└── custom-gpt/
    ├── openapi.yaml
    └── instructions.md
```

PoC段階ではモノレポとし、規模が大きくなってから分割を検討する。

## 11. IaC方針

AWSリソースは、可能な限りIaCで再現可能にする。

候補：

- AWS SAM / CloudFormation
- Terraform
- AWS CDK

Phase 4のLambda・API Gatewayには、CloudFormation拡張であるAWS SAMを採用する。AMP workspaceなど既存リソースはCloudFormationで管理し、SAMの変更もCloudFormation変更セットで確認してから実行する。

初期段階でCI/CDは必須としない。まずはローカルから手動で安全にデプロイし、構成が安定してからGitHub Actionsなどを検討する。

## 12. 未決定事項

Codex CLIは、実装前に以下を整理し、重要な選択についてユーザーへ確認すること。

1. IaCをAWS SAM / CloudFormation、Terraform、CDKのどれにするか（Phase 4まではAWS SAM / CloudFormationに決定）
2. 自宅側をDocker Composeで動かすか、systemdで直接動かすか
3. Prometheus Agentとして何を採用するか
4. AWSリージョン
5. AMPとローカル保存容量の料金・ディスク使用量の見積もりおよび予算上限
6. メトリクスの収集間隔と保持期間
7. 最初に送信するメトリクスとラベルの絞り込み
8. API Gatewayの認証方式
9. カスタムGPTを自分だけで使う段階と、公開する段階の認可方式
10. 複数ホスト対応時の`host_id`発行・所有者確認・データ分離方式
11. GrafanaをPoC第1段階に含めるか、AMPへの取り込み確認後に追加するか

## 13. 推奨する段階的な実装

### Phase 0: リポジトリ初期化

- Gitリポジトリを作成
- `PROJECT_BRIEF.md`を配置
- `.gitignore`を作成
- READMEに目的と現在のステータスを記載
- 採用技術とディレクトリ構成を決定
- 認証情報をコミットしない仕組みを先に用意

### Phase 1: ローカル収集

- 自宅LinuxサーバでNode Exporterを起動
- Prometheus Agentを起動
- AgentがNode Exporterをスクレイピングできることを確認
- まずローカルでメトリクス公開・収集を検証

### Phase 2: AMPへの転送

- AMP workspaceをIaCで作成
- 最小権限の書き込み用IAMを用意
- Prometheus Agentから`remote_write`
- AMP上で`up`などの基本メトリクスを確認
- 料金と取り込み量を確認

### Phase 3: ローカルGrafana可視化

- 通常Prometheusをローカルに追加し、Node Exporterを保存・PromQL検索できるようにする
- ローカルGrafanaを通常Prometheusへ接続する
- CPU、メモリ、ディスク、稼働状態の最小ダッシュボードを作成
- GrafanaだけをLAN/Tailscaleへ公開し、PrometheusとExporterは外部公開しない

### Phase 4: 診断用REST API

- LambdaからAMPへPromQLクエリ
- 複数クエリの結果を安定したJSONへ整形
- 単体テストを作成
- API Gatewayで読み取り専用APIとして公開
- `GET /hosts/home-server/status`だけを公開し、任意PromQL・任意ホストを受け付けない
- SSM Parameter Storeの共有シークレットを読むLambda Authorizerで認証する
- 入力検証、レート制限、14日保持のログ方針を設定

### Phase 5: カスタムGPT連携

- Actions用OpenAPIスキーマを作成し、`home-server`のstatus APIだけを公開
- API Key認証で`x-api-key`を設定
- カスタムGPT用Instructionsを作成
- 正常系として、診断可能なホストの照会とCPU使用率の照会をカスタムGPT画面から確認
- 警告、停止、データ欠損の各ケースは、意図的に条件を作ったうえで別途確認する

### Phase 6: 公開可能な構成へ拡張

- 利用者とホストの認可設計
- ホスト登録・失効方法
- 利用者ごとのデータ分離
- Abuse対策と料金上限
- GitHubで公開できるセットアップ手順とサンプル設定を整備

## 14. 最初の完了条件

最初のマイルストーンは、次の状態とする。

> 自宅LinuxサーバのNode ExporterをPrometheus Agentがスクレイピングし、AMPへ`remote_write`して、AMP上で対象ホストの`up`メトリクスを確認できる。

この段階では、Grafana、Lambda、API Gateway、カスタムGPTはまだ必須ではない。

## 15. Codex CLIへの最初の依頼文

新規リポジトリのルートでCodex CLIを起動し、次を依頼する。

```text
PROJECT_BRIEF.mdを読んで、このプロジェクトの目的、決定事項、制約、未決定事項を把握してください。

最初に以下を行ってください。
1. 内容を短く要約する
2. 構成上の矛盾や重大な見落としがあれば指摘する
3. 未決定事項のうち、Phase 0とPhase 1を始めるために今決める必要があるものだけを整理する
4. 推奨する初期リポジトリ構成と最初の作業計画を提示する

私が確認するまではAWSリソースの作成、外部サービスへの変更、秘密情報の生成、デプロイは行わないでください。
```

## 16. Codex CLIに期待する進め方

- まず既存ファイルとGitの状態を確認する。
- 小さな段階に分けて実装し、各段階で検証方法を提示する。
- AWSや主要ソフトウェアの現行仕様は公式ドキュメントで確認する。
- 実料金が発生するAWSリソースを作る前に、対象、料金要因、削除方法を説明して確認を取る。
- ユーザーの既存変更を勝手に削除・上書きしない。
- 秘密情報をコード、ログ、コミットへ含めない。
- 破壊的操作やAWSリソース削除は明示的な確認後に行う。
- 実装と同時にREADMEや構成資料を更新する。
- PoCでは過剰設計を避け、最初の完了条件を優先する。

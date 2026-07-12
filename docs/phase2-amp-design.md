# Phase 2: AMPへの転送設計

この段階の目的は、Prometheus AgentからAmazon Managed Service for Prometheus（AMP）へ`remote_write`する構成を、安全かつ費用を把握できる形で設計することです。この文書自体はAWSリソースを作成しません。

## 現在の前提

- 監視対象はUbuntu 24.04のLinuxホスト1台です。
- Node Exporterは`127.0.0.1:9100`だけで待ち受けています。
- Prometheus AgentはDocker Composeで動作し、30秒間隔でNode Exporterを収集しています。
- AWSリージョンは`ap-northeast-1`（東京）を使用します。人用のAWS CLIプロファイルは`Reotech736`です。
- AMP workspace `linux-monitoring-gpt-poc`、Agent専用IAMユーザー、アカウント全体US$20 Budgetを作成済みです。
- AgentのアクセスキーはGitの外にある`~/.config/linux-monitoring-gpt/aws/`へ分離して保存しています。

## この段階で学ぶこと

| 項目 | 内容 |
| --- | --- |
| AMP workspace | Prometheusメトリクスを論理的に分離して保存・検索する単位 |
| `remote_write` | Agentが収集済みメトリクスをHTTPSでAMPへ送信する仕組み |
| SigV4 | AWS APIリクエストに付与する署名方式 |
| IAM最小権限 | 自宅側は指定workspaceへの`aps:RemoteWrite`だけを許可する |
| CloudFormation | workspaceとIAMポリシーをコードで再現する方法 |
| コスト管理 | 取り込みサンプル数、保存量、クエリ量を観測・制御する方法 |

## 推奨するPoC構成

```text
Prometheus Agent
  ├─ Node Exporterを30秒間隔でscrape
  ├─ AWS認証情報でSigV4署名
  └─ HTTPS remote_write
          ↓
AMP workspace（ap-northeast-1候補）
```

自宅サーバからAWSへは外向きHTTPSだけを使います。VPC、VPN、PrivateLinkは、この1台の自宅サーバを対象とするPoCには追加しません。

## IaCの推奨

初期のIaCはCloudFormationを採用します。理由は、現在学習中のCloudFormationとAWS CLIをそのまま使え、AMP workspaceが`AWS::APS::Workspace`として定義できるためです。

Phase 2でコード管理する候補は次のとおりです。

- AMP workspace
- 自宅Agent専用のIAMポリシー
- CloudFormationの出力値（workspace ID、remote write endpointなど）

アクセスキー自体はCloudFormationの出力、テンプレート、Gitに含めません。

LambdaとAPI Gatewayを追加するPhase 4では、必要に応じてAWS SAMをCloudFormationの拡張として導入します。

## IAMと認証の方針

AMPの`remote_write`はSigV4署名を必要とします。Prometheusの`remote_write`設定では`sigv4`を指定します。

自宅サーバはAWS上のEC2ではないため、EC2 IAMロールを利用できません。PoCの候補は次のとおりです。

| 方式 | 評価 | PoCでの扱い |
| --- | --- | --- |
| 専用IAMユーザーのアクセスキー | 導入が最も分かりやすいが、長期認証情報の保管とローテーションが必要 | 推奨候補 |
| IAM Roles Anywhere | 短期認証情報を使えるが、証明書と信頼アンカーの設計が必要 | 公開・複数ホスト化の前に検討 |
| IAM Identity Centerの一時認証情報 | 人によるCLI操作には適するが、常時稼働Agentの認証としては追加検証が必要 | 今回は採用しない |

専用IAMユーザーを選ぶ場合でも、権限は指定したAMP workspaceへの`aps:RemoteWrite`だけに限定します。アクセスキーはホスト上の権限制限されたファイルへ置き、Dockerコンテナには読み取り専用で渡します。リポジトリ、`.env`、ログ、CloudFormation出力へ実値を置きません。

## 料金と送信量

AMPでは主に、取り込みメトリクス、保存量、クエリ処理量が課金要因です。データ転送の入力料金はAMPでは課金されませんが、料金はリージョンと最新の料金表で確認します。

概算の基礎となる式は次です。

```text
月間サンプル数 ≒ 送信するアクティブ時系列数 × 30日間の秒数 ÷ scrape_interval秒
```

30秒間隔では、1時系列あたり約86,400サンプル/月です。Node Exporterの全メトリクスを送ると、時系列数とラベル数が増えます。Phase 2では`write_relabel_configs`で送信対象を絞り、最初は`up`、CPU、メモリ、ディスク、ロードアベレージ、稼働時間に必要なメトリクスだけを許可します。

AMPの標準保持期間は150日です。PoCでは180日を明示的に設定します。アカウント全体Budget（US$20）は`aws-account-foundation`で管理し、Cost ExplorerとAMPの`IngestionRate`で想定外の取り込み量を検知する方針とします。

## 決定済みの項目

| 項目 | 推奨案 | 決定者 |
| --- | --- | --- |
| AWSリージョン | `ap-northeast-1` | 決定済み |
| 月額予算上限 | `aws-account-foundation`のアカウント全体US$20 Budgetを利用 | 決定済み |
| 保持期間 | 180日 | 決定済み |
| 自宅Agentの認証 | 専用IAMユーザー + `aps:RemoteWrite`限定 | 決定済み |
| IaC | CloudFormation | 決定済み |
| 初回送信メトリクス | 必要最小限の許可リスト | 決定済み |

## 実施済みの手順

1. 人用プロファイルの認証を確認した。
2. CloudFormationテンプレートを検証し、変更セットをレビューしてからAMP workspaceとAgent IAMユーザーを作成した。
3. Agent認証情報を専用ディレクトリへ保存し、Docker Composeへ読み取り専用で渡した。
4. AMPのQuery APIで`up{host_id="home-server"}`が`1`であることを確認した。

## 公式資料

- [AMP料金](https://aws.amazon.com/prometheus/pricing/)
- [AMP workspaceのCloudFormationリファレンス](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-aps-workspace.html)
- [Prometheusのremote writeによるAMP取り込み](https://docs.aws.amazon.com/prometheus/latest/userguide/AMP-onboard-ingest-metrics-remote-write-EC2.html)
- [AMPのIAM](https://docs.aws.amazon.com/prometheus/latest/userguide/AMP-and-IAM.html)
- [AMPのコスト管理](https://docs.aws.amazon.com/prometheus/latest/userguide/AMP-costs.html)

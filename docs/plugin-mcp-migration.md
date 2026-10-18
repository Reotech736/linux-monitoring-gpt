# Custom GPT Actionsからプラグインへの移行

## 現在地

2026-10-18時点で、ブラウザ版ChatGPTの`Linux Server Monitoring`から
Cognito OAuth認証、MCP初期化、ツール検出、`getHostStatus`によるAMP実データ取得まで成功した。
16件のテスト、依存関係の整合性、SAM lintとbuildは成功済み。

ChatGPT側の登録は作成時に取得した旧スコープ`linux-monitoring/status.read`を要求していた。
現在のOAuthメタデータが公開するMCP専用スコープは
`https://gcomsdpwrh.execute-api.ap-northeast-1.amazonaws.com/mcp/status.read`であり、両者が一致しない。
旧登録はアンインストール済みだが、削除時にHTTP 409
`Remove this app from the published plugin before deleting it.`が返る既知の不具合があり、
OpenAI側の修復または削除対応を待つ。現行の`Linux Server Monitoring`は別登録で正常稼働している。

共有Cognito基盤は`infrastructure/shared-auth-template.yaml`で、MCP本体は
`infrastructure/mcp-template.yaml`で管理する。旧Custom GPT専用の設定ファイルと手順書は、
AWSリソースの退役に合わせてリポジトリから削除した。

デプロイ結果（2026-10-17）：

- `linux-monitoring-gpt-mcp`: `UPDATE_COMPLETE`。
- MCP URL: `https://gcomsdpwrh.execute-api.ap-northeast-1.amazonaws.com/mcp`
- 両方のOAuthメタデータURLはHTTP 200。resourceとissuer、S256宣言を確認。
- 未認証のPOST /mcpはHTTP 401とresource_metadata付きchallengeを返す。
- GET /mcpはHTTP 405。
- 利用者から指定されたcallback URLを登録し、専用Cognito clientとbrandingを作成済み。
- client名: `linux-monitoring-gpt-mcp-chatgpt`。Secretはチャット・ファイルへ表示／保存せず、利用者の環境で取得してChatGPTへ設定する。
- MCP専用Resource Serverとスコープを追加済み。resource・S256 PKCE付き認可、コード交換、接続完了を確認。
- SAM成果物は既存のSAM管理バケットの`linux-monitoring-gpt-mcp/`に配置。
- 2026-10-18の再確認でスタックは`UPDATE_COMPLETE`。認証後のinitialize、tools/list、tools/callはHTTP 200、初期化通知はHTTP 202。
- Cognitoの実アクセストークンで`cognito:groups`が省略されたため、署名・issuer・audience・client ID・scopeに加え、設定した単一ユーザーの不変な`sub`を検証する代替認可を追加した。
- 旧Custom GPTは今後利用しない方針とし、2026-10-18に旧REST API、Lambda、OAuth client、
  Resource Server、Managed Login BrandingをAWSから削除した。共有User Pool、ドメイン、
  閲覧グループは現行MCPの認証基盤として保持している。

## 構成

```text
ChatGPTのプラグイン
  ├─ 認証情報の検出 → MCP側のOAuthメタデータ
  ├─ ログイン・コード交換 → 既存Cognito（専用アプリクライアント）
  └─ POST /mcp → 新しいHTTP API → MCP Lambda → 既存AMP
                                      └─ 既存build_statusを共有
```

- 新規スタック名は`linux-monitoring-gpt-mcp`、リージョンは`ap-northeast-1`。
- MCP Python SDKでStreamable HTTPを提供する。LambdaではステートレスなJSON応答を使い、GET /mcpは405とする。
- ツールは`getHostStatus(host_id="home-server")`だけ。入力ホストはLiteral型で制限する。
- 既存REST APIのトークンを転送するプロキシではない。既存の固定PromQL・診断整形処理をコードとして再利用する。
- MCP Lambdaは専用IAMロールでAMPを読む。認証済みリクエスト以外からは問い合わせない。
- 既存のAMP、Agent、Grafana、共有Cognito基盤は変更しない。旧REST APIとGPT用OAuth
  クライアントは移行完了後に削除した。

## 認証

### Cognitoのメタデータ補完

確認したCognitoのOIDC discoveryには`code_challenge_methods_supported`がなかった。
OpenAIのMCP認証仕様は`S256`の宣言を要求する。一方、Cognito自体はS256 PKCEを実装している。

MCP側でRFC 8414のOAuthメタデータを公開し、ログイン・token・revocationの各URLを
既存Cognitoへ向ける。認証コードやClient SecretをこのLambdaへ送る設計ではない。
OAuthメタデータのissuerはMCP origin（末尾`/`付き）、JWT検証のissuerは
実際のCognito User Pool URLと明確に分離する。両方ともサーバ設定で固定する。
これは独自のメタデータ補完実装であり、ChatGPTとの実接続まで検証済み。

- `/.well-known/oauth-protected-resource/mcp`：resource、認可サーバー、scope。
- `/.well-known/oauth-authorization-server`：Cognitoのエンドポイント、S256、認証方式。
- OIDC、CIMD、DCR、RFC 9207の対応は宣言しない。事前登録したOAuthクライアントを使う。
- 要求スコープは`<MCP URL>/status.read`のみ。ID tokenや個人情報は要求しない。
- 認可は専用client ID、resource、scopeに加え、`cognito:groups`または設定した単一ユーザーの
  不変な`sub`を検証する。Cognitoがグループクレームを省略した場合も対象ユーザー以外は許可しない。
- コールバックはChatGPTの管理画面に表示された正確な`https://chatgpt.com/connector/oauth/...`を登録する。
  古いGPT Action用URLや推測したcallback IDは使わない。

### 検証項目

Lambda内でRS256署名、Cognito issuer、有効期限、発行時刻、MCP URL宛ての`aud`、
専用`client_id`、`token_use=access`、scope、`monitoring-viewer-home-server`グループまたは設定済み単一ユーザーの`sub`を検証する。
署名鍵は設定済みCognitoのJWKSだけから取得する。任意URLをクライアント入力から受け取らない。

`resource`指定でCognitoがMCP URLを`aud`に含めたaccess tokenだけを受け付ける。
実環境の認可エンドポイントで、従来の`linux-monitoring/status.read`はresource binding時に
`invalid_request`となることを確認した。MCP URL専用のResource Serverとスコープを追加し、
旧REST APIのスコープとは分離する。
旧GPT用トークンやID tokenへのフォールバックは行わない。グループ変更・失効の反映には
発行済みJWTの有効期間が影響するため、access tokenは1時間に設定する。

## ローカル検証

Python 3.12の仮想環境にMCP用依存を入れ、既存APIを含めてテストする。

```bash
python3 -m venv /tmp/linux-monitoring-mcp-venv
/tmp/linux-monitoring-mcp-venv/bin/pip install -r lambda/requirements.txt
/tmp/linux-monitoring-mcp-venv/bin/python -m unittest discover -s lambda/tests -v
sam validate --lint --template-file infrastructure/mcp-template.yaml --region ap-northeast-1
PATH=/tmp/linux-monitoring-mcp-venv/bin:$PATH sam build \
  --template-file infrastructure/mcp-template.yaml \
  --build-dir .aws-sam/mcp-build
```

テストは署名付きのテスト用JWTでHTTP経由のinitialize、tools/list、tools/call、認証challenge、
メタデータ、欠損、内部エラーの秘匿、別ホスト・不正トークン・不正Originの拒否、
Lambdaの繰り返し呼び出しを確認する。実際のCognitoログインの代替ではない。

## AWS変更前の確認事項

この段階の実行には、リポジトリのAGENTS.mdに従って利用者の確認を得る。

| 項目 | 内容 |
| --- | --- |
| 追加 | HTTP API・stage・routes・integration、Lambda、呼び出し許可、IAMロール、14日保持のロググループ |
| OAuth | 既存User PoolにMCP URLをidentifierとするResource Server、専用client、Managed Login brandingを追加。ユーザー・グループは既存を利用 |
| Lambda実行権限 | 対象AMP workspaceの`aps:QueryMetrics`、専用ロググループの`logs:CreateLogStream`と`logs:PutLogEvents`のみ |
| デプロイ権限 | CloudFormation、API Gateway、Lambda、IAMロール・policy管理と`iam:PassRole`、Logs、Cognito Resource Server・client・branding管理、SAM成果物用S3の操作 |
| 料金要因 | APIリクエスト、Lambdaの回数・512MBでの実行時間、CloudWatch Logs、AMP照会サンプル数、Cognitoの利用者数、S3成果物保存 |
| 上限について | APIを2リクエスト/秒、burst 5に制限。これは月額料金の上限ではない。既存US$20 Budgetも通知であり強制停止ではない |
| 削除 | 新規MCPスタックだけを削除。AMP、既存User Pool、既存REST APIは残る。S3成果物は別途対象prefixを確認して削除 |

具体的な金額は利用回数・照会範囲・無料枠・東京リージョンの単価で変わるため、固定額とはしない。
デプロイ実行者への広いIAMポリシーを新規付与する作業はこの変更に含めない。

## 公開と接続の手順

1. 確認後、既存AMPスタックと診断APIスタックのOutputsから非秘密パラメータを取得する。
2. `PluginOAuthCallbackUrl`未指定で新規スタックを作成し、MCP URLを確定する。
   この段階ではOAuth clientは作成せず、ツールは認証で拒否される。メタデータだけ検証できる。
3. ChatGPTのプラグイン画面で「Add custom MCP server」を開き、MCP URLとOAuthを設定する。
   接続管理画面の正確なcallback URLを取得する。画面の順序や入力要件によって先へ進めない場合は、
   URLを推測せずその画面で止めて手順を確認する。
4. callback URLをパラメータに指定して同じスタックを更新し、専用clientとbrandingを作る。
5. Client IDとClient SecretをChatGPTのOAuth設定に登録する。
   コンソールの`ClientSecretId`は認証に使う値ではない。Secret一覧APIも値は返さない。
   今回の初期Secretは`DescribeUserPoolClient`の`ClientSecret`で取得できることを、
   値を出力せず確認した。利用者の環境で取得してクリップボードへ直接渡し、
   ChatGPTのSecret欄へ貼り付ける。チャット・リポジトリ・エージェントの出力に値を残さない。
6. 招待済みユーザーでログインし、`getHostStatus`の検出と`home-server`の実データを確認する。
7. 新しいチャットで`Linux Server Monitoring`を選択し、`home-server`の状態確認を依頼する。
   MCP側のserver instructionsにも基本の日本語説明指示を含めている。
8. トークン期限後の再認証、グループ未所属、別ホスト、欠損、API失敗を検証する。
   metadataやツールを変えたら接続をRefreshし、新しいチャットで再確認する。

削除する場合は、先にChatGPT側の接続を解除し、対象スタック名を確認する。
次のコマンドはMCP接続を停止し、このスタックで作成したリソースを削除するため、事前確認が必要。

```bash
aws cloudformation delete-stack \
  --stack-name linux-monitoring-gpt-mcp \
  --region ap-northeast-1 --profile Reotech736
```

## 参照

- [OpenAI: GPT移行](https://learn.chatgpt.com/docs/migrate-custom-gpts)
- [OpenAI: MCP認証](https://developers.openai.com/plugins/build/auth)
- [OpenAI: 接続とテスト](https://developers.openai.com/plugins/deploy/connect-chatgpt)
- [RFC 8414: OAuthメタデータ](https://www.rfc-editor.org/rfc/rfc8414.html)
- [AWS: Cognito認可エンドポイントとPKCE](https://docs.aws.amazon.com/cognito/latest/developerguide/authorization-endpoint.html)
- [AWS: resource binding](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-define-resource-servers.html)
- [Lambda料金](https://aws.amazon.com/lambda/pricing/)、[API Gateway料金](https://aws.amazon.com/api-gateway/pricing/)

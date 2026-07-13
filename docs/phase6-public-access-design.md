# Phase 6: 共有GPT向け認可設計

## 結論

リンクを知っている人にGPTを共有する段階では、現在の共通`x-api-key`認証を維持したまま共有範囲を広げません。Amazon Cognito User PoolをOAuth 2.0 / OpenID Connectの認可サーバーとして使い、利用者ごとのアクセストークンで診断APIを呼び出す構成へ移行します。

Custom GPT ActionsはAPI KeyとOAuthを選べ、OAuthでは利用者ごとにサインインできます。[OpenAIのGPT Action認証ガイド](https://developers.openai.com/api/docs/actions/authentication)に従い、OAuthを採用します。

## 現在の課題

現行のAPI KeyはGPTのAction設定に1つだけ保存されています。リンクを共有した利用者も同じActionを使うため、API側では「誰が呼び出したか」を識別できません。

| 項目 | 現行 | Phase 6 初期版 |
| --- | --- | --- |
| 利用者の識別 | できない | Cognitoの`sub`で識別 |
| API認証 | 共通`x-api-key` | OAuthアクセストークン |
| 利用開始 | GPTリンクを開くだけ | 招待済みCognitoユーザーがサインイン |
| 利用停止 | 共有キーの総入れ替え | 対象ユーザーを無効化 |
| ホスト認可 | `home-server`に固定 | Cognitoグループで`home-server`を許可 |

この初期版の対象は、信頼できる少人数へ共有するクローズドベータです。不特定多数の自己登録は対象にしません。

## 推奨アーキテクチャ

```text
利用者
  └─ ChatGPTのCustom GPT
       └─ OAuth Authorization Code Flow
            └─ Cognito managed login
                 └─ access token (scope: linux-monitoring/status.read)
                      └─ API Gateway HTTP API JWT Authorizer
                           └─ Status Lambda
                                ├─ Cognito groupを確認
                                └─ 固定PromQLでAMPを照会
```

API Gateway HTTP APIのJWT Authorizerは、CognitoのJWT署名、issuer、client ID、期限、スコープを検証できます。スコープをルートへ設定すると、アクセストークンに必要なスコープが含まれないリクエストをAPI Gatewayが拒否します。[AWSのJWT Authorizerガイド](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-jwt-authorizer.html)

## Cognitoの最小構成

IaCで次のリソースを作成します。

- Cognito User Pool: 自己登録を無効化し、管理者が招待したユーザーだけを作成する
- User Pool Domain: Cognito managed login用のドメイン
- User Pool Client: Authorization Code Grant、OAuth callback URL、1時間のアクセストークンを設定
- Resource Server / Scope: `linux-monitoring/status.read`
- Group: `monitoring-viewer-home-server`
- HTTP API JWT Authorizer: Cognito issuer、User Pool Client ID、上記スコープを検証

自己登録を有効にすると、アプリクライアントIDを知る人がアカウントを作成できるため、このPoCでは無効にします。[Cognitoの自己登録設定](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-admin-create-user-policy.html)

`StatusFunction`はAPI Gatewayが渡すJWT claimsの`cognito:groups`を確認し、`monitoring-viewer-home-server`に属するユーザーだけへ`home-server`を返します。グループ不一致はHTTP 403にします。JWT Authorizerだけではグループ単位のホスト対応表を表現しにくいため、ホスト認可はLambdaで明示的に確認します。

## Custom GPT側の設定

デプロイ後、GPT EditorのAuthenticationを**OAuth**へ切り替えます。設定値はCognito User Pool DomainとUser Pool Clientから取得します。

- Authorization URL: `https://<domain>/oauth2/authorize`
- Token URL: `https://<domain>/oauth2/token`
- Scope: `openid linux-monitoring/status.read`
- Redirect URL: GPT Editorが表示するcallback URLをCognito User Pool Clientのcallback URLへ登録する

OpenAIは`https://chat.openai.com/aip/<GPT_ID>/oauth/callback`と`https://chatgpt.com/aip/<GPT_ID>/oauth/callback`の両方をcallback URLとして登録するよう案内しています。GPT IDは現在のGPT URLから確認します。Cognito User Pool ClientのsecretはGit・CloudFormation出力・会話へ保存せず、所有者が取得してGPT Editorだけへ設定します。

## 移行と削除

1. 現行stackを更新してCognito、JWT Authorizer、グループ検証を追加する。
2. 招待ユーザーを作成し、グループへ追加する。
3. OAuthトークンで`GET /hosts/home-server/status`が成功することを確認する。
4. GPT EditorをOAuth設定へ切り替え、招待ユーザーで正常系を確認する。
5. 旧Lambda Authorizer、旧共有シークレット、SSMパラメータを削除する。

削除前にOAuth経由の正常系と拒否系を確認します。旧共有シークレットを先に削除すると、ロールバック時の復旧手段が失われます。

## 料金・運用への影響

- 新たな料金要因は主にCognito User Poolの月間アクティブユーザー（MAU）です。料金とFree Tierの適用可否は作成時点で[Amazon Cognito料金](https://aws.amazon.com/cognito/pricing/)を確認します。
- API Gateway、Lambda、AMPの既存の料金要因は継続します。
- Cognito managed loginのドメインはインターネットから到達可能になりますが、監視APIそのものはJWT認証とグループ認可を通過した呼び出しだけを処理します。
- ユーザーを失効する場合は、Cognitoでユーザーを無効化し、必要に応じてグローバルサインアウトを行います。すでに発行済みのアクセストークンを考慮し、アクセストークン有効期限は1時間にします。

## 検証条件

- 未サインインの利用者はAction呼び出し時にサインインを求められる。
- 招待済みかつ`monitoring-viewer-home-server`所属の利用者だけがHTTP 200を得る。
- 招待済みでもグループに属さない利用者はHTTP 403になる。
- 無効化した利用者は再認証できず、既存トークンの失効後は利用できない。
- `home-server`以外、任意PromQL、書き込み操作は引き続き受け付けない。

## 次段階: 複数ホスト

複数ホスト化が必要になった時点で、Cognitoグループだけでなく`principal_sub`と`host_id`の対応を持つDynamoDBテーブルを追加します。今回の1ホストPoCで先にDynamoDBを導入すると、データ分離の効果を検証できないまま運用対象だけが増えるため、初期版では導入しません。

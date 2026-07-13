# Phase 5: Custom GPT Actions連携

## 目的

Phase 4の読み取り専用診断APIをCustom GPT Actionとして登録し、利用者の質問に対してサーバ状態を日本語で説明できるようにします。

このPoCは、現時点では`home-server`だけを診断対象とします。GPTを公開・共有すると、登録済みのActionを利用できる範囲も広がるため、Phase 6で利用者ごとの認可を設計するまでは、共有する場合も信頼できる人に限定します。

## Git管理する成果物

- `custom-gpt/openapi.yaml`: Actionに貼り付けるOpenAPI 3.1スキーマ
- `custom-gpt/instructions.md`: GPT BuilderのInstructions欄に貼り付ける指示

スキーマの`servers.url`は現在のAPI Gateway URLです。診断API stackを削除・再作成してURLが変わった場合は、stack出力の`ApiUrl`へ更新してからActionを再インポートします。

## GPT Builderでの設定

1. ChatGPTでGPTを作成または編集し、**Configure**を開きます。
2. **Actions**でActionを追加し、`custom-gpt/openapi.yaml`の内容をインポートします。
3. Authenticationで**API Key**を選び、認証ヘッダー名を`x-api-key`に設定します。
4. Phase 4でパスワードマネージャへ保存した共有シークレットを入力します。値はGit、Instructions、スキーマ、会話へ貼り付けません。
5. `custom-gpt/instructions.md`の内容をInstructions欄へ貼り付けます。
6. GPTの共有範囲を設定します。リンク共有を使う場合は、下記のプライバシーポリシーを登録し、共有対象を信頼できる人に限定します。

OpenAI公式ガイドでは、ActionにOpenAPIスキーマを登録し、認証方式を設定したうえで、Action名と入出力に対応したInstructionsを記述することを案内しています。

## リンク共有時のプライバシーポリシー

GPTを「リンクを知っている人」に公開する前に、`docs/privacy-policy.md`の公開GitHub URLをGPT EditorのPrivacy policy URLへ設定します。

```text
https://github.com/Reotech736/linux-monitoring-gpt/blob/main/docs/privacy-policy.md
```

このURLには、Actionが返すサーバメトリクス、AWSとChatGPTを介した処理、ログ・メトリクスの保持期間、問い合わせ先を記載します。GitHub Pagesも有効化済みですが、既存カスタムドメインの設定が404を返すため、現時点ではこのGitHub URLを正とします。共有範囲を広げると、共有シークレットを設定したAction経由でサーバ状態を確認できる利用者が増えます。利用者ごとの認可を実装するPhase 6までは、共有対象を信頼できる人だけに限定します。

## Actionテスト

Actions画面の`getHostStatus`にある**Test**を使い、次を確認します。

```json
{
  "host_id": "home-server"
}
```

成功時はHTTP 200と`reachable`、CPU、メモリ、ディスク、ロード、稼働日数、`alerts`が返ります。401の場合は`x-api-key`と共有シークレットを、502の場合はPhase 4のCloudWatch Logsを確認します。

その後、GPTとの会話で少なくとも次を確認します。

- 「自宅Linuxサーバの状態を確認して」: Actionを1回呼び、状態を日本語で要約する
- 「ディスク使用率は？」: Actionを呼び、ディスク使用率とアラートを説明する
- 「別のホストを確認して」: このPoCでは未対応であることを説明する
- Action失敗時: 状態を推測せず、監視APIの失敗として説明する

## 実施済みの正常系確認

カスタムGPT [Linux Server Diagnostic GPT](https://chatgpt.com/g/g-6a53c4cf774481919948ee509a3e6cda-linux-server-diagnostic-gpt) を作成し、ChatGPT画面で次を確認しました。

- 「今診断することができるホストは何があるか教えて」に対し、`home-server`だけが対象であると回答すること
- 「CPU稼働状況を教えて」に対し、Action経由で取得したCPU使用率、5分ロードアベレージ、稼働日数、アラートの有無を日本語で回答すること

警告・停止・データ欠損は、監視対象を不用意に停止させないよう、再現方法を決めてから別途検証します。現時点では正常系だけを確認済みです。

## セキュリティと削除

- API URLは公開到達可能ですが、`x-api-key`が一致しなければHTTP 401で拒否されます。
- 共有シークレットはChatGPTのAction認証設定とSSM Parameter Storeだけで管理します。Git、ログ、会話、OpenAPIスキーマに保存しません。
- Actionを不要にする場合は、先にGPTからActionと共有シークレットを削除し、その後Phase 4のCloudFormation stackとSSMパラメータを削除します。

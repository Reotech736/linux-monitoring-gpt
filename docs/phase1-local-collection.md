# Phase 1: ローカル収集

この段階ではAWSへデータを送信しません。Linuxホスト上のNode ExporterをPrometheus Agentが収集できることを確認します。

## この構成で学ぶこと

Node Exporterは、CPU、メモリ、ディスク、ロードアベレージなどのホストメトリクスを`/metrics`で公開するExporterです。Exporter自身は通常、保存やAWSへの転送を行いません。

Prometheus Agentは、30秒ごとにNode Exporterをpullで収集します。Agent modeでは長期保存用のPrometheus TSDBを持たず、Phase 2で追加する`remote_write`でAMPへ転送するための一時的なWALだけを使用します。

```text
Node Exporter (127.0.0.1:9100)
          ↓ scrape /metrics
Prometheus Agent (127.0.0.1:19090)
```

`19090`を使う理由は、このホストの`9090`が既存のDockerコンテナにより利用されているためです。どちらのポートもループバックアドレスだけで待ち受けるため、LANやインターネットへは公開されません。

## Node Exporterの導入

Ubuntu 24.04では、まずディストリビューション提供の`prometheus-node-exporter`パッケージを使います。候補バージョンは`1.7.0-1ubuntu0.3`です。最新の上流版ではありませんが、最初の収集対象には十分で、APTによる更新管理とsystemdサービス管理を学べます。

次のコマンドはシステムへパッケージとsystemdサービスを追加します。実行にはsudo権限が必要です。

```bash
sudo apt update
sudo apt install prometheus-node-exporter
```

インストール後、まずパッケージが作成したサービス定義を確認します。設定ファイルの場所や起動引数を確認してから、待受先を`127.0.0.1:9100`へ制限します。

```bash
systemctl cat prometheus-node-exporter
systemctl status prometheus-node-exporter --no-pager
```

Ubuntuパッケージでは`/etc/default/prometheus-node-exporter`が起動引数の設定場所です。この環境では`ARGS=""`であり、Node Exporterは既定の`*:9100`（全インターフェース）で待ち受けています。`sudoedit`で設定ファイルを開き、`ARGS`をループバック待受に変更します。

```bash
sudoedit /etc/default/prometheus-node-exporter
```

ファイル中の次の1行だけを置き換えます。

```text
ARGS=""
```

置き換え後:

```text
ARGS="--web.listen-address=127.0.0.1:9100"
```

保存後、次のコマンドでNode Exporterを一時的に再起動します。

```bash
sudo systemctl restart prometheus-node-exporter
sudo systemctl enable prometheus-node-exporter
curl --fail --silent http://127.0.0.1:9100/metrics | sed -n '1,12p'
ss -ltnH | rg ':9100\\b'
```

`ss`の出力が`127.0.0.1:9100`であることを確認します。`0.0.0.0:9100`または`[::]:9100`なら、待受制限が反映されていないため、Prometheus Agentを起動せず設定を見直します。

## Prometheus Agentの起動

`home-agent/compose.yaml`はLinuxのhost networkを使います。これにより、コンテナ内の`127.0.0.1:9100`はLinuxホストのNode Exporterを指します。Dockerの`ports:`は使わず、AgentのWeb UIも`127.0.0.1:19090`へ限定します。

設定を確認してから起動します。初回起動時は約100 MBの公式コンテナイメージをDocker Hubから取得します。Composeは最初に`init-prometheus-data`を実行し、Agentが非rootユーザーでWALを書き込めるよう`data/`の所有者だけを設定します。この初期化コンテナが`Exited (0)`になることは正常です。

```bash
cd home-agent
docker compose config
docker compose up -d
docker compose ps -a
docker compose logs --tail=100 prometheus-agent
```

## 完了条件の確認

Agentのターゲット状態を確認します。Prometheus Agent modeはローカルのPromQLクエリを提供しないため、`/api/v1/query`で`up`を確認するのではなく、Targets APIの`health`を確認します。

```bash
curl --fail http://127.0.0.1:19090/api/v1/targets
```

初回scrape後に、レスポンス中の`health`が`up`であればローカル収集は成功です。Phase 2では同じメトリクスをAMPへ`remote_write`し、AMP上で`up`の値が`1`であることをPromQLで確認します。

## 停止と削除

Prometheus Agentだけを停止する場合は、次を実行します。`data/`はローカルの一時データでGit管理されず、残したまま再開できます。

```bash
cd home-agent
docker compose down
```

Node Exporterを削除する場合は、監視機能が停止することを理解したうえで、次を実行します。

```bash
sudo apt remove prometheus-node-exporter
```

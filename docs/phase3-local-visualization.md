# Phase 3: ローカルPrometheus・Grafana可視化

## 構成

既存のPrometheus AgentはAMPへの`remote_write`を継続します。Phase 3で追加する通常Prometheusは同じNode Exporterを別途scrapeし、ローカルTSDBへ保存します。

```text
Node Exporter (127.0.0.1:9100)
  ├─ Prometheus Agent → AMP
  └─ Local Prometheus → ローカルTSDB (90日または10GB)
                              ↑
                   Grafana (LAN/Tailscaleのみ公開)
```

- Node Exporter、Prometheus Agent、Local PrometheusはLANへ公開しません。
- Grafanaは`LAN_BIND_IP:3000`と`TAILSCALE_BIND_IP:3000`だけで待ち受けます。
- PrometheusはGrafana専用Docker bridgeのgatewayである`172.30.0.1:19091`で待ち受け、Grafanaコンテナだけが参照します。
- Grafanaの初期管理者パスワードはGit管理外の`.env`に置きます。匿名アクセスと自己サインアップは無効です。

## 起動

次のコマンドは、実行時設定を作成します。`GRAFANA_ADMIN_PASSWORD`には十分に長く、他サービスで使っていない値を設定してください。

```bash
cd local-observability
cp env.example .env
chmod 600 .env
```

`LAN_BIND_IP`と`TAILSCALE_BIND_IP`が現在のIPと一致することを確認してから、設定を検証して起動します。

UFWを有効化しているホストでは、Grafana専用bridgeからPrometheusへのTCP通信だけを許可します。次の操作はホストファイアウォールを変更しますが、送信元を`172.30.0.0/24`、宛先をbridge gatewayの`172.30.0.1:19091`に限定します。LANやTailscaleからPrometheusへ接続できるようにはなりません。

```bash
sudo ufw allow in on br-monitoring from 172.30.0.0/24 to 172.30.0.1 port 19091 proto tcp
sudo ufw status numbered
```

```bash
docker compose config --quiet
docker compose up -d
docker compose logs --tail=100 prometheus grafana
```

初回のみ、Docker HubからPrometheusとGrafanaの公式イメージを取得します。ローカル保存データは`prometheus-data/`と`grafana-data/`に作成され、Git管理されません。

## 確認

PrometheusのターゲットとGrafanaコンテナからのデータソース到達性を確認します。

```bash
curl --fail --silent http://172.30.0.1:19091/api/v1/targets
docker compose exec grafana wget -qO- http://172.30.0.1:19091/-/ready
```

ブラウザで次へアクセスし、`.env`に設定した管理者アカウントでログインします。

```text
http://${LAN_BIND_IP}:3000
http://${TAILSCALE_BIND_IP}:3000
```

`Linux Monitoring / Home Server Overview`ダッシュボードに、稼働状態、CPU、メモリ、ディスク、ロードアベレージが表示されれば成功です。

## 停止と削除

GrafanaとLocal Prometheusだけを停止します。既存のNode Exporter、Prometheus Agent、AMP workspaceは影響を受けません。

```bash
cd local-observability
docker compose down
```

保存済みのローカル可視化データも削除する場合は、コンテナ停止後に`prometheus-data/`と`grafana-data/`を削除します。この操作でローカル履歴とGrafana設定は失われます。

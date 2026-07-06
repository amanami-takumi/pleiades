# Pleiades API 使用マニュアル

このマニュアルは、家庭内LANまたはVPN内の別サービスから Pleiades の保存済み投資情報を取得するための簡易手順です。

## ベースURL

Docker Compose の標準設定では、バックエンドAPIは次のURLで待ち受けます。

```bash
http://localhost:5050
```

別端末や別サービスからアクセスする場合は、`localhost` を Pleiades が動いているサーバーのIPアドレスまたはホスト名に置き換えてください。

```bash
http://192.168.x.x:5050
```

## 認証

`EXTERNAL_API_KEY` を設定していない場合、外部連携APIは認証なしで利用できます。

`.env` などで `EXTERNAL_API_KEY` を設定した場合は、リクエストヘッダーに `X-Pleiades-Api-Key` を付けてください。

```bash
X-Pleiades-Api-Key: your-key
```

例:

```bash
curl -H "X-Pleiades-Api-Key: your-key" http://localhost:5050/api/external/market/symbols
```

家庭内LAN内だけで使う場合でも、他サービスから自動取得させるなら `EXTERNAL_API_KEY` の設定を推奨します。

## ヘルスチェック

APIサーバーが起動しているか確認します。

```bash
curl http://localhost:5050/api/health
```

正常な応答例:

```json
{
  "status": "ok",
  "time": "2026-07-06T00:00:00.000000+00:00"
}
```

## 登録銘柄一覧を取得する

登録済みの銘柄、最新終値、最新日付、PER/PBR/ROEなどの主要指標を取得します。

```bash
curl http://localhost:5050/api/external/market/symbols
```

APIキーを使う場合:

```bash
curl -H "X-Pleiades-Api-Key: your-key" http://localhost:5050/api/external/market/symbols
```

主なレスポンス項目:

- `symbols`: 銘柄一覧
- `symbols[].ticker`: ティッカー
- `symbols[].name`: 銘柄名
- `symbols[].latest_close`: 最新終値
- `symbols[].latest_date`: 最新日付
- `symbols[].change_1d_percent`: 前日比率
- `symbols[].per`: PER
- `symbols[].pbr`: PBR
- `symbols[].roe`: ROE
- `symbols[].dividend_yield`: 配当利回り
- `generated_at`: API応答生成日時

## 日足データを取得する

指定したティッカーの日足 OHLCV を取得します。

```bash
curl "http://localhost:5050/api/external/market/daily-prices/7203.T"
```

日付範囲を指定する場合:

```bash
curl "http://localhost:5050/api/external/market/daily-prices/7203.T?from=2026-01-01&to=2026-06-30"
```

APIキーを使う場合:

```bash
curl -H "X-Pleiades-Api-Key: your-key" "http://localhost:5050/api/external/market/daily-prices/7203.T?from=2026-01-01&to=2026-06-30"
```

主なレスポンス項目:

- `symbol`: 対象銘柄の情報
- `points`: 日足データ一覧
- `points[].date`: 日付
- `points[].open`: 始値
- `points[].high`: 高値
- `points[].low`: 安値
- `points[].close`: 終値
- `points[].adj_close`: 調整後終値
- `points[].volume`: 出来高
- `points[].return_percent`: 取得範囲の初回終値を基準にした騰落率
- `from_date`: 指定した開始日
- `to_date`: 指定した終了日
- `generated_at`: API応答生成日時

## エラー例

存在しないティッカーを指定した場合:

```json
{
  "detail": "Symbol not found"
}
```

APIキーが間違っている場合:

```json
{
  "detail": "Invalid external API key"
}
```

`from` が `to` より後の日付の場合:

```json
{
  "detail": "from must be earlier than or equal to to"
}
```

## 利用時の注意

- このAPIは保存済みデータを読み取るためのAPIです。Yahoo Finance など外部データソースへ直接問い合わせるAPIではありません。
- 最新データが必要な場合は、Pleiades 側で市場データ更新が完了していることを確認してください。
- 家庭内サービスから定期取得する場合、毎分などの高頻度取得は避け、必要な間隔にしてください。
- 投資判断に使う場合は、終値、日付、出来高、指標の更新日を必ず確認してください。

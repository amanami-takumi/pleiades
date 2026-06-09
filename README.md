# Pleiades

自宅 VPN 内で使う汎用ツールアプリです。現時点では投資情報システムを実装しています。

## 起動

```bash
docker compose up --build
```

- フロントエンド: http://localhost:3050
- バックエンド: http://localhost:5050
- SQLite: `data/pleiades.sqlite3`

ポートを変える場合は `.env` に `APP_PORT` と `BACKEND_PORT` を指定してください。

## 市場データ取得間隔

Yahoo Finance 側のレート制限を避けるため、バックエンドは取得間隔とリトライ間隔を環境変数で調整できます。

```bash
MARKET_REQUEST_INTERVAL_SECONDS=2
MARKET_SYMBOL_INTERVAL_SECONDS=5
MARKET_RETRY_COUNT=2
MARKET_RATE_LIMIT_BACKOFF_SECONDS=60
```

## 実装済み

- 左側の縦タブとスマホ右下メニュー
- Yahoo Finance レスポンスの直接取得による指数・銘柄の保存
- SQLite への価格履歴と指標保存
- 週・月・年・3年・5年のチャート表示
- PER、PBR、ROE、時価総額、配当利回りの表示
- 手動更新と約1日ごとの自動更新
- 非上場投資信託は Yahoo!ファイナンスの投信時系列 BFF から5年分の基準価額を取得
# pleiades

# PROGRESS.md

このプロジェクトには `CLAUDE.md` によるプロジェクト固有の記載規約が存在しないため、
本ファイルは今回のテスト導入に伴い新規作成した。以後の更新もここに追記する。

## テスト状況

**テスト状況：72件中72件 PASS**(2026-08-25 時点、`python -m pytest` で実行・APIキー不要・ネットワーク呼び出しなし)

| ファイル | 件数 | 対応する VISION.md の設計思想 |
|---|---|---|
| `tests/test_naming.py` | 16 | ファイル名無害化 / 法人格除去 / smart_split |
| `tests/test_trim.py` | 8 | トリミング(bbox・余白・長辺上限) |
| `tests/test_downloader.py` | 7 | 候補スコアリング・除外形式・透過判定 |
| `tests/test_net.py` | 4 | 秘密情報マスク |
| `tests/test_config.py` | 6 | 不足キーの明示 |
| `tests/test_report.py` | 5 | 1社失敗で全体を止めない(出力側) |
| `tests/test_bg_remove.py` | 6 | 402(クレジット)/429(レート制限)の区別 |
| `tests/test_serpapi.py` | 3 | 通信例外の秘密情報マスク(SerpAPI固有) |
| `tests/test_pptx_export.py` | 5 | PPTXレイアウト計算 |
| `tests/test_pipeline.py` | 8 | キャッシュでAPI無消費・やり直しの候補位置・クエリ生成 |
| `tests/test_ci_fetch.py` | 4 | GitHub版: 画像ハッシュ付与・取得日の保持 |
| **合計** | **72** | |

実行方法: [README.md#開発者向け](README.md#開発者向け) を参照。

## スコープ外(意図的に未カバー)

VISION.md で `[qcheck]` または `[philosophy]` に分類した項目は対象外。具体的には:

- Tkinter GUI の実際の描画・操作(表示系、目視確認が必要)
- Flask版(`src/webapp/server.py`)のHTTPエンドポイント(手動+ブラウザでの多角レビュー済み)
- クリップボードのOS実連携・実PowerPointへの貼り付け(COM自動化スクリプトで別途検証済み)
- `docs/index.html` のJSロジック(ビューワー・ブラウザ内PPTX生成) — Python向けpytestの対象外
- GitHub Actions ワークフロー(`.github/workflows/fetch-logos.yml`)自体の実行(Actions上でのE2E実行で別途検証済み)

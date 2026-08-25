# PROGRESS.md

このプロジェクトには `CLAUDE.md` によるプロジェクト固有の記載規約が存在しないため、
本ファイルは今回のテスト導入に伴い新規作成した。以後の更新もここに追記する。

## テスト状況

**テスト状況：74件中74件 PASS**(2026-08-25 時点、`python -m pytest` で実行・APIキー不要・ネットワーク呼び出しなし)

| ファイル | 件数 | 対応する VISION.md の設計思想 |
|---|---|---|
| `tests/test_naming.py` | 16 | ファイル名無害化 / 法人格除去 / smart_split |
| `tests/test_trim.py` | 8 | トリミング(bbox・余白・長辺上限) |
| `tests/test_downloader.py` | 9 | 候補スコアリング・除外形式・透過判定・remove.bg向け形式変換 |
| `tests/test_net.py` | 4 | 秘密情報マスク |
| `tests/test_config.py` | 6 | 不足キーの明示 |
| `tests/test_report.py` | 5 | 1社失敗で全体を止めない(出力側) |
| `tests/test_bg_remove.py` | 6 | 402(クレジット)/429(レート制限)の区別 |
| `tests/test_serpapi.py` | 3 | 通信例外の秘密情報マスク(SerpAPI固有) |
| `tests/test_pptx_export.py` | 5 | PPTXレイアウト計算 |
| `tests/test_pipeline.py` | 8 | キャッシュでAPI無消費・やり直しの候補位置・クエリ生成 |
| `tests/test_ci_fetch.py` | 4 | GitHub版: 画像ハッシュ付与・取得日の保持 |
| **合計** | **74** | |

実行方法: [README.md#開発者向け](README.md#開発者向け) を参照。

## qcheck状況(見た目・UX)

VISION.md の `[qcheck]` タグは全4件、対応する qcheck テストを作成・実施し **全件 PASS**(2026-08-25)。

| ファイル | 対象 | 件数 |
|---|---|---|
| [tests/ui.qcheck.md](tests/ui.qcheck.md) | 見た目(レイアウト・配色・レスポンシブ・PPTX実開封・クリップボード形式) | 9項目(うち2件は発見即修正: ボタン配色統一、favicon追加) |
| [tests/ux.qcheck.md](tests/ux.qcheck.md) | 操作フロー・文言(確認ダイアログ・エラー処理・run_id突合) | 11項目(うち1件は環境制約により一部未実施、過去の実機検証で代替担保) |

実トークンでの実際の取得実行(Actions E2E)は管理者による手動確認が必要なため未実施。
詳細は各ファイル末尾を参照。

## スコープ外(意図的に未カバー)

VISION.md で `[qcheck]` または `[philosophy]` に分類した項目は対象外。具体的には:

- Tkinter GUI の実際の描画・操作(表示系、目視確認が必要)
- Flask版(`src/webapp/server.py`)のHTTPエンドポイント(手動+ブラウザでの多角レビュー済み)
- クリップボードのOS実連携・実PowerPointへの貼り付け(COM自動化スクリプトで別途検証済み)
- `docs/index.html` のJSロジック(ビューワー・ブラウザ内PPTX生成) — Python向けpytestの対象外
- GitHub Actions ワークフロー(`.github/workflows/fetch-logos.yml`)自体の実行(Actions上でのE2E実行で別途検証済み)

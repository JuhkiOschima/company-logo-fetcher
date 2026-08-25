# VISION.md — 企業ロゴ自動取得・背景削除ツール

作成日: 2026-08-25 / 最終更新: 2026-08-25 / ステータス: 稼働中(GitHub版が主経路)

---

## Why

企業名のリストを渡すだけで、ロゴ画像の取得・背景透過・トリミングを自動化し、**PowerPoint にロゴが貼られた状態**まで最短距離で到達させる。単発の個人ツールではなく、常時稼働のサーバーを持たないチームでも、GitHub のアカウントさえあれば誰でも取得を実行でき、結果が共有ストックとして蓄積・検索・再利用できる状態を最終形とする。

---

## 設計思想

タグの意味:
- `[unit test]` — pytest で自動検証できる(値・分岐・境界条件など決定的なロジック)。実行: `python -m pytest`
- `[qcheck]` — 見た目・文章・UX など、unit test では評価できない品質。[tests/ui.qcheck.md](tests/ui.qcheck.md) / [tests/ux.qcheck.md](tests/ux.qcheck.md) に手順と実施結果を記録
- `[philosophy]` — いずれの自動テストでも検証できない、方針・トレードオフ判断

### 全体ルール

- **ゴールは「PNGを作ること」ではなく「PPTに貼られた状態」** — ダウンロード→保存→挿入の手間まで含めて省く設計にする `[philosophy]`
- **1社の失敗で全体を止めない** — 最後まで走り切り、末尾に成否サマリを出す `[unit test]`
- **1回の処理規模は少数(〜20社)を前提にする** — 並列化・大量処理向けの最適化はせず、逐次処理でシンプルに保つ `[philosophy]`
- **キーが未設定なら「足りないキー名」だけを提示して終了する**。値は一切表示・ログ出力しない `[unit test]`
- **APIキーは設定ファイル/環境変数からのみ読み込み、配布物・リポジトリ・チャット・ログに一切含めない** `[unit test]`(マスク処理)+ `[philosophy]`(運用方針)
- **1ファイル1責務、300〜500行を目安にする** — 超えそうな場合は分割案を提示し了承を得てから分割する `[philosophy]`

### 機能横断ルール

- **キャッシュがあればAPIを呼ばない** — 検索結果・背景透過済み画像を単位ごとにキャッシュし、再実行時のAPI消費をゼロにする(検索・背景透過の両方に適用) `[unit test]`
- **書き込みは原子的に行う**(一時ファイル→置換)。配信中・強制終了中の中途半端なファイルを外部に見せない(ローカル/Web共有版/CI版すべてで共通) `[unit test]`
- **通信例外の文字列には秘密情報を含めない** — SerpAPI 等キーがURLクエリに乗る構成では、例外メッセージを外に出す前に必ずマスクする `[unit test]`
- **「やり直し」は前回使った候補の次から** — 単純なリトライ回数ではなく、実際に採用された候補位置(`used_rank`)を起点にする。同じ画像を再度処理してしまう不整合を避ける `[unit test]`
- **ファイル名・パスに使う外部入力は必ず無害化する** — パス区切り・`..`・Windows予約デバイス名を潰す(GUI/Web/GitHub版いずれも企業名は外部入力) `[unit test]`
- **クレジット不足(402)とレート制限(429)を区別する** — 前者は恒久停止、後者は時間を置けば回復するため区別して扱う `[unit test]`

### 機能別ルール

**検索(SerpAPI)**
- クエリは `<企業名> ロゴ` を基本形とし、法人格表記(株式会社等)は既定で除去してから検索する `[unit test]`
- プロバイダは差し替え可能なインターフェースにする(API提供終了・料金改定のリスク対策) `[philosophy]`

**候補スコアリング**
- 縦横比(横長を優遇)・解像度・ファイル形式(PNG/WebP優遇)・取得元ドメイン(自社ドメイン/Wikipedia等を優遇)の複合スコアで並べ替える `[unit test]`
- SVG/ICO/AVIF等、扱えない形式は候補から除外する `[unit test]`

**背景透過(remove.bg)**
- 取得画像が既に透過済みなら remove.bg を呼ばずスキップする(クレジット節約) `[unit test]`
- 新規取得ではAPI消費見込みを事前提示し、確認を取る `[qcheck]`(文言・UXの妥当性。QC-UX-01, [tests/ux.qcheck.md](tests/ux.qcheck.md))

**トリミング**
- アルファ値がしきい値を超える画素の外接矩形を求め、長辺比一定の余白を足して切り出す `[unit test]`
- 出力の長辺は上限を超える場合のみ縮小する(拡大はしない) `[unit test]`

**クリップボード連携(exe/GUI版)**
- PowerPoint への貼り付けは **PNG形式 + CF_HDROP(ファイル) + CF_DIB(白背景の保険)** の組み合わせを使う。**CF_DIBV5 は絶対に載せない**(PowerPointがそちらを優先しアルファを破棄・黒塗りになることを実機検証済み) `[qcheck]`(実機のPowerPoint COM自動化で検証、pytestの対象外。QC-UI-09, [tests/ui.qcheck.md](tests/ui.qcheck.md))

**PPTX生成(まとめ出力)**
- 全ロゴを1スライドにグリッド配置し、各ロゴの下に企業名を添える。列数は件数に応じて自動決定する `[unit test]`(レイアウト計算)+ `[qcheck]`(実際にPowerPointで開けること。QC-UI-08, [tests/ui.qcheck.md](tests/ui.qcheck.md))
- ブラウザ内生成(GitHub版)の場合、スライドの relationships には必ず slideLayout への関連付け(rId1)を含める。欠くとPowerPointが開けない `[philosophy]`(ロジックが `docs/index.html` のJSにあり、今回導入したpytestの対象外。実機のPowerPoint COM自動化で検証済み)

**GitHub版(取得エンジン・ストック・ビューワー)**
- 取得は GitHub Actions(workflow_dispatch)。APIキーは Secrets に1セットのみ(利用者側のキー設定は不要) `[philosophy]`
- push競合時は「マージ→PNG合併結果から index/pptx を再生成→積み増して再push」で解消する。競合によってAPI消費済みの取得結果を失わない `[unit test]`(rebuild-onlyの再生成ロジック)+ `[philosophy]`(方針)
- ビューワーは「自分が依頼した実行」を run_id で確定してから見守る。時刻の前後関係やクライアント時計には依存しない `[qcheck]`(JS、pytest対象外。QC-UX-09, [tests/ux.qcheck.md](tests/ux.qcheck.md))
- 画像URLには内容ハッシュ(`?v=`)を付与し、やり直し後もブラウザ/CDNキャッシュで古い画像が表示され続けないようにする `[unit test]`(ハッシュ生成側)

---

## 出力情報

### 出力ファイル

| ファイル | 内容 | 生成元 |
|---|---|---|
| `<企業名>.png` / `docs/logos/<企業名>.png` | 透過・トリミング済みロゴ | 全経路共通 |
| `logos.pptx` | 全ロゴを1スライドに並べたもの | ローカル(python-pptx)/ ブラウザ内生成(JS) |
| `report.csv` | 企業名・成否・取得元URL・remove.bg使用有無 | ローカル/CLI版 |
| `failed.txt` | 失敗した企業名のみ(再実行の入力に使える) | ローカル/CLI版 |
| `index.json` | 企業名・取得元ドメイン・取得日・画像ハッシュ | GitHub版 |
| `quota.json` | SerpAPI/remove.bg の残数 | GitHub版/Web共有版 |
| `last_run.json` | 直近の実行結果とrun_id | GitHub版 |

### 配布経路

| 経路 | 用途 | 状態 |
|---|---|---|
| **GitHub版(主経路)** | Actions=取得エンジン(Secretsにキー1セット)、リポジトリ=ストック、Pages=検索・コピー・PPTX出力UI。全員が使え、誰のPCにも依存しない | ✅稼働中(public / Pages公開済み) |
| exe(`LogoTool.exe` / `LogoToolCLI.exe`) | 個別・オフライン利用向け(各自のAPIキーが必要) | ✅完了(`dist/LogoTool_v0.7.1.zip`) |
| Web共有版(社内LAN) | 補助。所有者が在席中のみの即時利用 | ✅実装済み(任意起動) |
| OneDrive共有 / 単独GitHub(Pagesなし) | 検討の結果いずれも不採用 | — |

APIキーの扱い: exe/Web共有版は利用者(所有者)各自のキー、GitHub版は Secrets に管理者(大島)のキー1セット。いずれもリポジトリ・配布物にキーは含めない。

### ディレクトリ構成

```
背景削除/
├── VISION.md / README.md / PROGRESS.md
├── config.example.toml / requirements.txt / companies.txt
├── src/                        # ローカル版(CLI・GUI・Web共有版)のロジック本体
│   ├── main.py / config.py / pipeline.py / naming.py / trim.py
│   ├── downloader.py / bg_remove.py / clipboard.py / report.py / pptx_export.py
│   ├── search/                 # 検索プロバイダ(差し替え可能)
│   ├── gui/                    # Tkinter GUI
│   └── webapp/                 # 社内LAN共有版(Flask)
├── tools/                      # CIエントリ・検証スクリプト・配布ビルド
│   └── ci_fetch.py             # GitHub Actions から呼ばれる取得エンジン
├── docs/                       # GitHub版のストック+ビューワー(Pages公開対象)
│   ├── index.html              # 検索・コピー・PPTX出力UI
│   └── logos/                  # 蓄積されたロゴ画像
├── .github/workflows/          # Actions定義
├── tests/                      # pytest([unit test]) + ui/ux.qcheck.md([qcheck]の手順書)
└── ci-cache/                   # GitHub版の検索キャッシュ(永続)
```

### 未決定事項

1. 出力ファイル名:企業名そのまま(日本語ファイル名)でよいか、英数字に正規化するか(現状は日本語のまま。支障なし)
2. 候補スコアリングの調整・多様な企業リストでの精度検証は未着手。運用しながら気になるケースが出た都度、個別に対応する方針

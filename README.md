# AKB48 ビデオ自動要約システム

橋本陽菜（はるpyon）を中心とした AKB48 Team 8 の配信アーカイブを対象とした、日本語ビデオ高精度転写・AI 要約自動化パイプライン。

Oracle Cloud（ARM 無料枠）上での常時稼働を前提に設計されています。

---

## 目次

- [システム概要](#システム概要)
- [アーキテクチャ](#アーキテクチャ)
- [機能一覧](#機能一覧)
- [必要環境](#必要環境)
- [インストール](#インストール)
- [設定](#設定)
- [使い方](#使い方)
- [処理モード詳細](#処理モード詳細)
- [ビデオ最適化戦略](#ビデオ最適化戦略)
- [モデル降格ロジック](#モデル降格ロジック)
- [後処理パイプライン](#後処理パイプライン)
- [出力フォーマット](#出力フォーマット)
- [自動クリーンアップ](#自動クリーンアップ)
- [プロジェクト構造](#プロジェクト構造)

---

## システム概要

```
Oracle OCI バケット
       ↓  scripts/download_videos.py
videos/ ディレクトリ
       ↓  scripts/main.py  （または watch.py による監視）
       ├─ [Whisper モード]  転写 → AI 要約
       └─ [動画直送モード]  Gemini API に動画をアップロードして直接分析
              ↓
outputs/ ディレクトリ
       ├─ *_detailed.txt   詳細版 AI 要約
       ├─ *_youtube.txt    YouTube コメント用簡潔版
       ├─ *.json           構造化データ
       └─ *_invalid.txt    フォーマット検証失敗時の生 AI 出力（デバッグ用）
              ↓  後処理
       ├─ Oracle バケット内の処理済みビデオを削除
       ├─ YouTube 動画の概要欄を自動更新
       └─ GitHub Pages リポジトリに要約ファイルを push
```

---

## アーキテクチャ

```
akb48-summarizer/
├── config/
│   ├── config.yaml          # 全設定の中心ファイル
│   └── vocabulary.txt       # Whisper 用カスタム語彙 (~280 語)
├── core/
│   ├── processor.py         # 処理全体のオーケストレーター
│   ├── transcriber.py       # Whisper Large-v3 転写器
│   └── summarizer.py        # AI 出力の解析・検証
├── services/
│   └── gemini.py            # Gemini API クライアント（テキスト・動画）
├── models/
│   └── manager.py           # モデル選択・降格ロジック
├── utils/
│   ├── file.py              # 設定読み込み・ファイル I/O・処理ログ
│   ├── video.py             # ffprobe 情報取得・ffmpeg 加速・音声抽出
│   ├── video_optimizer.py   # 時長ベースの最適化戦略（5 段階）
│   └── format.py            # タイムライン生成・YouTube コメント生成
└── scripts/
    ├── main.py              # バッチ処理エントリーポイント
    ├── watch.py             # watchdog による自動監視デーモン
    ├── download_videos.py   # Oracle OCI からのビデオダウンロード
    ├── update_description.py # YouTube 概要欄の自動更新
    └── update_git.py        # GitHub Pages への要約ファイル push
```

---

## 機能一覧

| カテゴリ | 機能 |
|---|---|
| **転写** | Whisper Large-v3 + 280 語のカスタム語彙（メンバー名・公演名・ファン名等） |
| **AI 要約** | Gemini API による詳細版 + YouTube 用簡潔版の同時生成 |
| **動画直送** | Gemini Files API にビデオをアップロードして直接分析（Whisper 不要） |
| **最適化** | 動画時長に応じた 5 段階の前処理戦略（加速・fps 削減・音声抽出） |
| **モデル降格** | Gemini 3 Flash → 2.5 Flash → 2.5 Flash Lite → Ollama Qwen 14B |
| **バッチ処理** | 処理済みログによるスキップ、エラー時の継続処理 |
| **監視デーモン** | watchdog による `videos/` ディレクトリのリアルタイム監視 |
| **OCI 連携** | Oracle バケットからのダウンロードと処理済みビデオの自動削除 |
| **YouTube 連携** | OAuth2 で YouTube Data API v3 を呼び出して概要欄を自動更新 |
| **Git 連携** | 要約ファイルを GitHub Pages リポジトリに自動 commit & push |
| **クリーンアップ** | 月次アーカイブ・容量超過時の古いビデオ自動削除（bash スクリプト） |

---

## 必要環境

**システム依存**
- Python 3.10 以上
- ffmpeg / ffprobe
- Git（後処理を使う場合）

**Python パッケージ**

```
faster-whisper>=1.0.0
google-generativeai>=0.8.0
pyyaml>=6.0
watchdog>=3.0.0
requests>=2.31.0
oci                          # Oracle OCI SDK（download_videos.py 用）
google-auth-oauthlib         # YouTube 更新用
google-api-python-client     # YouTube 更新用
```

---

## インストール

```bash
# 1. リポジトリをクローン
git clone <repo_url>
cd akb48-summarizer

# 2. Python 依存をインストール
pip3 install --break-system-packages -r requirements.txt

# 3. システム依存をインストール（Ubuntu）
sudo apt-get install ffmpeg
```

---

## 設定

`config/config.yaml` を編集してください。最低限必要な設定は以下のとおりです。

```yaml
# Gemini API キーファイルのパス（ファイルに生キーを書く）
gemini_api_key_file: "/home/ubuntu/.gemini_api_key"

# 処理モードの選択
processing:
  use_video_direct_analysis: true  # true = 動画直送、false = Whisper 転写
  media_resolution: "LOW"          # LOW / MEDIUM / HIGH
  save_raw_on_fail: true           # フォーマット検証失敗時に生出力を保存

# 入力ビデオフォルダ
input:
  video_folder: "./videos"
  mode: "folder"                   # "folder" または "single"
```

Oracle OCI を使う場合は `config/bucket_credentials.key` に以下の 3 行を記述します。

```
<namespace>
<bucket_name>
<region>          # 例: ap-tokyo-1
```

---

## 使い方

### バッチ処理（単発実行）

```bash
python3 scripts/main.py
```

`videos/` 内のビデオを順番に処理し、`outputs/` に結果を保存します。処理済みビデオは `outputs/processed.json` に記録され、次回実行時にスキップされます。

### 監視デーモン（常時起動）

```bash
python3 scripts/watch.py
```

`videos/` ディレクトリを watchdog で監視し、新しいビデオが追加されると自動的に `main.py` を呼び出します。

### Oracle OCI からダウンロード

```bash
python3 scripts/download_videos.py
```

設定された OCI バケットからビデオを `videos/` にダウンロードします。

---

## 処理モード詳細

### モード 1: 動画直送（`use_video_direct_analysis: true`）

1. `VideoOptimizer` が時長に応じた前処理戦略を決定
2. 必要に応じて ffmpeg で加速・音声抽出
3. Gemini Files API にアップロード
4. プロンプトで **詳細版** と **YouTube 版** を同時生成
5. `Summarizer.parse_dual_summary()` で 2 バージョンに分割
6. `Summarizer.validate_youtube_format()` でフォーマット検証。失敗時はコードで生成

**出力**: 詳細版 `.txt` + YouTube 版 `.txt` + `.json`（転写テキストなし）

### モード 2: Whisper 転写（`use_video_direct_analysis: false`）

1. `Transcriber` が Whisper Large-v3 で日本語転写
2. `config/vocabulary.txt` のカスタム語彙を `initial_prompt` として注入
3. 転写テキストを `ModelManager.summarize_from_text()` で AI 要約
4. タイムライン生成・YouTube コメント生成

**出力**: 詳細版 `.txt` + YouTube 版 `.txt` + `.json`（完全転写テキスト付き）

---

## ビデオ最適化戦略

`VideoOptimizer` は ffprobe で取得した動画時長に基づき、Gemini の 250,000 トークン上限に収まるよう自動選択します（安全余裕 5%）。

| 段階 | 時長 | 処理 | fps | 推定レート |
|---|---|---|---|---|
| 第 1 档 | ≤ 40 分 | そのまま | 1.0 | 87 tokens/秒 |
| 第 2 档 | 40〜80 分 | 2倍速 | 1.0 | 87 tokens/秒 |
| 第 3 档 | 80〜120 分 | 2倍速 | 0.5 | 59.5 tokens/秒 |
| 第 4 档 | 120〜170 分 | 2倍速 | 0.25 | 45.75 tokens/秒 |
| 第 5 档 | 170〜240 分 | 2倍速 + 音声抽出 | — | 32 tokens/秒 |
| — | > 240 分 | ❌ 処理不可 | — | — |

---

## モデル降格ロジック

`ModelManager` は `config.yaml` の `summarization_models` リストを上から順に試みます。

```
1. gemini-3-flash-preview    （最高品質）
2. gemini-2.5-flash          （安定・品質良好）
3. gemini-2.5-flash-lite     （RPM 多め・最速）
4. qwen2.5:14b（Ollama）     （ローカル・無制限・要手動有効化）
```

動画直送モードでは Gemini モデルのみ使用します。Ollama は Whisper モードのテキスト要約時のみ有効です。

---

## 後処理パイプライン

`main.py` はビデオ処理完了後に以下を順番に実行します（各セクションは config で有効化）。

### 1. Oracle バケット自動削除

`oracle_download.auto_cleanup: true` の場合、処理済みビデオ（`outputs/` に対応する `.txt` が存在するもの）を OCI バケットから削除します。`.uploaded` マーカーファイルも同時に削除されます。

### 2. YouTube 概要欄の自動更新

`youtube_description_update.enabled: true` の場合、`videos/` 内の `*.mp4.uploaded` ファイルを走査します。各ファイルに書かれた YouTube 動画 ID を参照し、対応する `*_youtube.txt` の内容を既存の概要欄の先頭に追記します。

認証情報は `config/credentials/autoupsr/` 以下の OAuth2 トークンを使用します。

### 3. GitHub Pages への要約 push

`git_update.enabled: true` の場合、`*_detailed.txt` を `<git_repo_path>/summaries/<video_id>.txt` にコピーし、バッチ commit → 一括 push します。ローカルに未 push のコミットが残っている場合も自動検出して push します。

---

## 出力フォーマット

### `*_detailed.txt`

```
======================================================================
動画: <ファイル名>
生成時間: 2026-01-11 13:30:00
使用モデル: gemini-3-flash-preview
======================================================================

【AI要約（詳細版）】
----------------------------------------------------------------------
## 概要
...

## 主なトピック
...

【タイムライン】
----------------------------------------------------------------------
00:05 - ...
12:30 - ...

【完全な文字起こし】
----------------------------------------------------------------------
（Whisper モードのみ）
```

### `*_youtube.txt`

```
📝 はるpyonの配信まとめ

...

💡 この配信の見どころ：
- ...

ぜひご覧ください✨

※ この要約は自動生成されました
```

### `*.json`

```json
{
  "video": "filename.mp4",
  "summary": "...",
  "timeline": [{"time": "00:05", "seconds": 5, "text": "..."}],
  "transcript": "...",
  "youtube_comment": "...",
  "model": "gemini-3-flash-preview",
  "stats": {"char_count": 12345, "generated_at": "..."}
}
```

---

## 自動クリーンアップ

`auto_cleanup/` 以下の bash スクリプトを cron 等で定期実行することを推奨します。

### `cleanup_videos.sh`

`videos/` の合計サイズが `MAX_SIZE_GB`（デフォルト 10GB）を超えた場合、最も古い `.mp4` ファイルから削除して `TARGET_PERCENT`（80%）まで縮小します。

```bash
# crontab 例: 1時間ごとにチェック
0 * * * * /home/ubuntu/akb48-summarizer/auto_cleanup/cleanup_videos.sh >> /var/log/cleanup.log 2>&1
```

### `archive_outputs.sh`

前月分の `outputs/` ファイルを `archives/outputs_YYYY_MM.tar.gz` に圧縮・移動します。

```bash
# crontab 例: 毎月1日の深夜に実行
0 2 1 * * /home/ubuntu/akb48-summarizer/auto_cleanup/archive_outputs.sh >> /var/log/archive.log 2>&1
```

---

## カスタム語彙の追加

`config/vocabulary.txt` に 1 行 1 語で追記します。コメントは `#` で始めます。語彙は Whisper の `initial_prompt` として注入されるため、メンバー名・公演名・ファン名・口癖など専門語を追加することで転写精度が向上します。

```
# 新メンバーの追加例
山田花子
やまちゃん
```

---

## ライセンス

MIT License

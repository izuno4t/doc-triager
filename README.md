# doc-triager

ローカルに蓄積されたドキュメントを LLM で自動分類するバッチツール。

ドキュメントを **Evergreen**（恒久的に価値がある）と **Temporal**（時間とともに価値が低下する）に仕分けし、Evergreen ドキュメントを後続の検索基盤（[doc-searcher](../doc-searcher/)）に供給する。

```text
source/
├── tech/java/design_patterns.pdf      ─→  evergreen/tech/java/design_patterns.pdf
├── tech/java/spring-boot-3.2-news.pdf ─→  temporal/tech/java/spring-boot-3.2-news.pdf
├── ai/transformer_architecture.docx   ─→  evergreen/ai/transformer_architecture.docx
└── ai/ai-trends-2024.pptx            ─→  temporal/ai/ai-trends-2024.pptx
```

## 特徴

- **MarkItDown** によるユニバーサルなテキスト抽出（PDF, DOCX, PPTX, XLSX, HTML, 画像 等）
- **Evergreen / Temporal** の概念ベース分類で LLM の判定精度を最大化
- **litellm** によるマルチ LLM 対応（OpenAI, Anthropic, Ollama）
- チェックサムベースの重複排除・中断再開
- ドライランモードで安全に動作確認

## 必要要件

- Python 3.12+
- macOS
- LLM API キー（OpenAI / Anthropic）または Ollama

## インストール

```bash
git clone <repository-url>
cd doc-triager
pip install -e '.[all]'
```

## クイックスタート

### 1. 設定ファイルを作成

```bash
cp config/doc-triager.example.toml config/doc-triager.toml
```

```toml
[input]
directory = "/path/to/google-drive/documents"

[output]
directory = "/path/to/classified"

[llm]
provider = "openai"
model = "gpt-4o"
api_key_env = "OPENAI_API_KEY"

[database]
path = "./triage.db"
```

### 2. API キーを設定

```bash
export OPENAI_API_KEY="sk-..."
```

### 3. ドライランで確認

```bash
doc-triager run -s /path/to/documents -o /path/to/classified --dry-run
```

ファイル移動を行わず、分類結果だけを確認できる。

### 4. 実行

```bash
doc-triager run -s /path/to/documents -o /path/to/classified
```

## 使い方

### 分類の実行

```bash
# 基本実行
doc-triager run --source <source_dir> --output <output_dir>

# ドライラン（分類のみ、ファイル移動なし）
doc-triager run -s <source_dir> -o <output_dir> --dry-run

# 処理件数を制限してテスト
doc-triager run -s <source_dir> -o <output_dir> --limit 10

# 特定の拡張子のみ対象
doc-triager run -s <source_dir> -o <output_dir> --extensions pdf,docx

# 設定ファイルを指定
doc-triager run -c config/doc-triager.toml
```

### 結果の確認

```bash
# 全体サマリー
doc-triager status

# unknown に分類されたファイルの一覧
doc-triager status --triage unknown

# evergreen の一覧
doc-triager status --triage evergreen
```

### 再分類

```bash
# unknown のみ閾値を下げて再分類
doc-triager reclassify --threshold 0.5
```

### エクスポート

```bash
doc-triager db export --format json
doc-triager db export --format csv
```

## 分類の仕組み

### 分類カテゴリ

| ラベル | 意味 | 例 |
| --- | --- | --- |
| `evergreen` | 時間が経っても価値が持続する | 設計原則、アルゴリズム解説、プロトコル仕様 |
| `temporal` | 時間経過で価値が低下する | 年次レポート、バージョン固有の情報、ベンチマーク比較 |
| `unknown` | 判定不能 | テキスト不足、内容混在、確信度が閾値未満 |

### 処理フロー

```text
ファイル
  → SHA-256 チェックサム計算
  → DB照合（処理済みならスキップ）
  → MarkItDown でテキスト抽出（→ Markdown）
  → LLM に分類を依頼
  → confidence 閾値チェック
  → ファイルを分類先フォルダに移動
  → 結果を DB に記録
```

### 確信度と閾値

LLM は各分類に 0.0〜1.0 の確信度スコアを付与する。スコアが `confidence_threshold`（デフォルト: 0.7）未満の場合、自動的に `unknown` に分類される。

閾値を調整することで、`unknown` の量をコントロールできる:

- 閾値を上げる → 厳格。`unknown` が増える。精度重視。
- 閾値を下げる → 寛容。`unknown` が減る。カバレッジ重視。

## 出力

### ディレクトリ構成

```text
<output_base>/
├── temporal/                 # 一時的ドキュメント
│   └── (元の階層構造を保持)
├── evergreen/                # 恒久的ドキュメント
│   └── (元の階層構造を保持)
└── unknown/                  # 判定不能ドキュメント
    └── (元の階層構造を保持)
```

ファイルは**移動**される（コピーではない）。元のディレクトリ階層は保持される。

### triage.db

SQLite データベース。分類結果とメタデータが記録される。

```text
triage_results テーブル:
  source_path, destination_path, checksum, triage,
  confidence, reason, topics, llm_model, ...
```

このDBは [doc-searcher](../doc-searcher/) から参照される（トピックタグ等のメタデータ取得用）。

## 設定リファレンス

```toml
[input]
directory = "/path/to/google-drive/documents"
exclude_patterns = ["*.DS_Store", "*.gitkeep", "__MACOSX/**"]

[output]
directory = "/path/to/classified"

[triage]
confidence_threshold = 0.7        # 0.0-1.0, unknown 判定の閾値
max_input_tokens = 8000           # LLM に送るテキストの最大トークン数

[llm]
provider = "openai"               # openai / anthropic / ollama
model = "gpt-4o"
api_key_env = "OPENAI_API_KEY"    # 環境変数名（直書き禁止）
# base_url = "http://localhost:11434"  # Ollama 用

[llm.rate_limit]
requests_per_minute = 30
max_retries = 3
retry_delay_sec = 5               # 指数バックオフの初期値
request_timeout_sec = 120

[database]
path = "./triage.db"

[text_extraction]
min_text_length = 100             # これ未満はテキスト不足と判定
llm_description_enabled = false   # 画像のLLM描写（将来オプション）

[logging]
level = "INFO"                    # DEBUG / INFO / WARNING / ERROR
file = "./doc-triager.log"
```

## 中断と再開

処理はファイル単位で独立しているため、いつでも中断できる。再実行時はチェックサムベースで処理済みファイルを自動スキップし、未処理のファイルから再開する。

ファイルが変更されている場合（チェックサム不一致）は再分類される。

## doc-searcher との関係

```text
doc-triager                     doc-searcher
┌───────────────┐            ┌─────────────────────┐
│               │            │                     │
│  evergreen/   │──ファイル──→│  index → Qdrant     │
│               │            │           ↑         │
│  triage.db    │──メタデータ→│  search / serve     │
│               │  (topics,  │                     │
│               │   reason)  └─────────────────────┘
└───────────────┘
```

doc-triager は doc-searcher の存在を知らない。`evergreen/` フォルダと `triage.db` が契約のすべて。

## 技術スタック

| コンポーネント | 技術 |
| --- | --- |
| 言語 | Python 3.12+ |
| テキスト抽出 | markitdown |
| LLM 連携 | litellm |
| DB | SQLite |
| CLI | click or typer |
| 設定 | TOML |

## ライセンス

TBD

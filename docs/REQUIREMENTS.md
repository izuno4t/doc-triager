# ① doc-triager 要件定義書

## 1. 概要

### 1.1 目的

ローカルに蓄積された多数のドキュメントを自動的に分類し、恒久的（Evergreen）に価値のあるドキュメントと一時的（Temporal）なドキュメントを仕分けする。

### 1.2 スコープ

- ローカルファイルシステム上のドキュメントを対象とする
- LLM を用いてドキュメントの内容を分析し、分類を行う
- 分類結果に基づきファイルを所定のフォルダに移動する
- 処理結果をローカルDBに記録し、再実行時の重複処理を防止する

### 1.3 スコープ外

- ベクトルDB、RAG、検索基盤に関する一切の処理
- 本プロジェクトは Qdrant の存在を知らない

### 1.4 前提条件

- 実行環境: macOS
- ソースファイルはローカルファイルシステム上に存在する（Google Drive 同期済み）
- ソースフォルダはディレクトリ階層構造を持つ
- ファイル数は非常に多い（数千件以上を想定）

### 1.5 後続プロジェクトとの関係

```text
【① doc-triager（本プロジェクト）】
  ソースフォルダ → 分類 → evergreen/ に移動
  ここで責務完了。

【② doc-searcher（別プロジェクト）】
  evergreen/ → インデクシング → Qdrant ← MCP/CLI で検索
  ①の出力フォルダを入力として使用する。
```

①の出力（`evergreen/` フォルダ + `triage.db`）が②の入力となる。
ただし①は②の存在に依存しない。

---

## 2. 分類定義

### 2.1 分類カテゴリ

| カテゴリ | ラベル | 定義 | 例 |
| --------- | -------- | ------ | ----- |
| Temporal（一時的） | `temporal` | そのときのトレンド・時事に依存する内容。時間経過により情報価値が著しく低下するもの | 年次トレンドレポート、特定バージョンの新機能紹介、ベンチマーク比較、時事ニュース記事 |
| Evergreen（恒久的） | `evergreen` | 根本的・普遍的な内容。時間が経っても情報価値が持続するもの | 設計原則、アルゴリズム解説、理論的知見、言語仕様の根幹、プロトコル仕様 |
| Unknown（不明） | `unknown` | LLM が十分な確信を持って判定できなかったもの | テキスト抽出が不十分、内容が混在、判定基準に合致しない |

> **ラベル選定の意図:** 「Evergreen / Temporal」はコンテンツ管理の分野で広く使われる概念であり、LLM が分類判定する際に既存の知識と結びつきやすい。抽象的な A/B ラベルよりも判定精度の向上が期待できる。

### 2.2 分類判定ロジック

- LLM に対しドキュメント内容と分類基準を提示し、以下を返却させる:
  - `classification`: `temporal` / `evergreen` / `unknown`
  - `confidence`: 0.0〜1.0 の確信度スコア
  - `reason`: 判定理由（自然言語）
  - `topics`: ドキュメントのトピックタグ（配列）
- confidence が閾値未満の場合、分類を強制的に `unknown` に変更する

### 2.3 閾値設定

| パラメータ | デフォルト値 | 説明 |
| ----------- | ------------ | ------ |
| `confidence_threshold` | 0.7 | これ未満のconfidenceは `unknown` に分類 |

- 閾値は設定ファイルで変更可能とする
- 運用しながら閾値を調整し、`unknown` の量を適正化する

---

## 3. テキスト抽出

### 3.1 抽出エンジン

テキスト抽出には **MarkItDown**（[microsoft/markitdown](https://github.com/microsoft/markitdown)）を使用する。

MarkItDown はあらゆるファイル形式を **Markdown 形式に統一変換** するライブラリであり、個別のファイル形式ごとにライブラリを使い分ける必要がない。出力が Markdown であるため、LLM への入力として構造（見出し、リスト、テーブル等）が保持された状態で渡せる。

```python
from markitdown import MarkItDown

md = MarkItDown()
result = md.convert("document.pdf")
markdown_text = result.text_content
```

### 3.2 対象ファイル形式

MarkItDown がネイティブにサポートする形式すべてを対象とする。

| 形式 | 拡張子 | 備考 |
| ------ | -------- | ------ |
| PDF | `.pdf` | テキスト抽出。スキャンPDFはOCRオプションで対応可能 |
| Word | `.docx` | 見出し・リスト・テーブル構造を保持 |
| PowerPoint | `.pptx` | スライドごとにテキスト抽出 |
| Excel | `.xlsx` | テーブルとしてMarkdown変換 |
| 画像 | `.png`, `.jpg`, `.jpeg` | EXIF メタデータ抽出。OCR/LLM描写はオプション |
| HTML | `.html`, `.htm` | Markdown変換 |
| テキスト系 | `.csv`, `.json`, `.xml` | そのまま or 構造化して変換 |
| Markdown | `.md` | そのまま利用 |
| テキスト | `.txt` | そのまま利用 |
| ZIP | `.zip` | 内包ファイルを再帰的に処理 |

### 3.3 画像・スキャンPDFの高度な処理（オプション）

MarkItDown は `llm_client` を渡すことで、画像やPPTX内の図版に対して LLM ベースの内容説明を生成できる。

```python
from markitdown import MarkItDown
from openai import OpenAI

client = OpenAI()
md = MarkItDown(llm_client=client, llm_model="gpt-4o")
result = md.convert("slide_deck.pptx")
```

初期フェーズではこのオプションは無効とし、テキスト抽出のみで運用する。画像中心のドキュメントでテキストが不足する場合は `unknown` に分類する。

### 3.4 対象外（スキップ）

- 設定ファイルで除外拡張子・除外パターンを指定可能とする
- デフォルト除外: `.DS_Store`, `.gitkeep`, `.git/**`, `__MACOSX/**` etc.
- MarkItDown が対応していない形式のファイルは自動的にスキップし、ログに記録する

---

## 4. 処理フロー

### 4.1 メインフロー

```text
START
  │
  ▼
[1] ソースディレクトリを再帰的にスキャン
  │
  ▼
[2] 対象ファイルをフィルタリング（拡張子ベース）
  │
  ▼
[3] 各ファイルについてループ:
  │
  ├─[3.1] ファイルのチェックサム（SHA-256）を計算
  │
  ├─[3.2] ローカルDB照合
  │   ├─ 処理済み（同一チェックサム）→ スキップ
  │   └─ 未処理 or 変更あり → 続行
  │
  ├─[3.3] テキスト抽出（MarkItDown）
  │   ├─ 成功 → 続行
  │   └─ 失敗/テキスト不足 → unknown に分類、理由記録
  │
  ├─[3.4] LLM API 呼び出し（分類リクエスト）
  │   ├─ 成功 → 結果取得
  │   └─ 失敗（API エラー等）→ リトライ or スキップ
  │
  ├─[3.5] confidence 閾値チェック
  │   └─ 閾値未満 → unknown に変更
  │
  ├─[3.6] ファイルを分類先フォルダに移動
  │
  └─[3.7] 結果をローカルDB に記録
  │
  ▼
[4] 処理サマリーを出力
  │
  ▼
END
```

### 4.2 テキスト抽出の詳細

- MarkItDown の `convert()` メソッドでファイルを Markdown テキストに変換する
- 変換結果の `text_content` が空または文字数が閾値（例: 100文字）未満の場合:
  - スキャンPDF/画像主体のドキュメントとみなす
  - `unknown` に分類し、理由に「テキスト抽出不足」を記録する
- MarkItDown が例外を発生させた場合（未対応形式等）:
  - エラーをキャッチし、スキップしてログに記録する

### 4.3 LLM 入力の制御

- テキストが長い場合はトークン制限を考慮してトランケートする
- トランケート時は先頭と末尾を優先的に含める（中間を省略）
- トランケートした事実をLLMに伝える

---

## 5. ファイル操作

### 5.1 ディレクトリ構成

```text
<output_base>/
├── temporal/                 # 一時的ドキュメント
│   └── (元の階層構造を保持)
├── evergreen/                # 恒久的ドキュメント → ②doc-searcher の入力
│   └── (元の階層構造を保持)
└── unknown/                  # 判定不能ドキュメント
    └── (元の階層構造を保持)
```

### 5.2 移動ルール

- ファイルは元のフォルダから移動する（コピーではなく移動）
- 元のディレクトリ階層構造は出力先でも保持する
  - 例: `source/tech/java/design.pdf` → `evergreen/tech/java/design.pdf`
- 同名ファイルが出力先に既に存在する場合はファイル名にサフィックスを付与する

---

## 6. ローカルDB

### 6.1 データベースエンジン

SQLite を使用する。DBファイルは設定で指定したパスに配置する。

### 6.2 テーブル定義

#### `triage_results` テーブル

| カラム | 型 | 説明 |
| -------- | ----- | ------ |
| `id` | INTEGER PRIMARY KEY | 自動採番 |
| `source_path` | TEXT NOT NULL | 元のファイルパス |
| `destination_path` | TEXT | 移動先のファイルパス |
| `checksum` | TEXT NOT NULL | ファイルのSHA-256ハッシュ |
| `file_size` | INTEGER | ファイルサイズ（bytes） |
| `file_extension` | TEXT | 拡張子 |
| `triage` | TEXT NOT NULL | `temporal` / `evergreen` / `unknown` |
| `confidence` | REAL | 確信度スコア（0.0〜1.0） |
| `reason` | TEXT | 判定理由 |
| `topics` | TEXT | トピックタグ（JSON配列として格納） |
| `llm_provider` | TEXT | 使用したLLMプロバイダ |
| `llm_model` | TEXT | 使用したLLMモデル |
| `extracted_text_length` | INTEGER | 抽出テキストの文字数 |
| `truncated` | BOOLEAN | テキストをトランケートしたか |
| `error_message` | TEXT | エラーが発生した場合のメッセージ |
| `processed_at` | DATETIME NOT NULL | 処理日時 |
| `created_at` | DATETIME DEFAULT CURRENT_TIMESTAMP | レコード作成日時 |

#### インデックス

- `idx_checksum` ON `checksum` — 重複チェック用
- `idx_triage` ON `triage` — 分類別集計用
- `idx_source_path` ON `source_path` — パス検索用

> **Note:** このDBは②doc-searcher から参照される。②はここに格納された `topics` や `reason` をメタデータとして活用する。

---

## 7. LLM連携

### 7.1 プロバイダ対応

設定により以下のLLMプロバイダを切り替え可能とする:

- OpenAI（GPT-4o 等）
- Anthropic（Claude）
- ローカル（Ollama 経由）
- その他（設定で追加可能な構造とする）

### 7.2 分類プロンプト（テンプレート）

```text
You are a document classification expert.
Analyze the following document and classify it as either "evergreen" or "temporal" content.

## Classification Criteria

### evergreen (Timeless / Foundational)
Content that remains valuable regardless of when it is read.
Its relevance does NOT decay significantly over time.

Examples of evergreen content:
- Design principles and architectural patterns (e.g., SOLID, Clean Architecture)
- Algorithm explanations and data structure theory
- Protocol specifications and core language specifications
- Cognitive psychology theories, UX heuristics
- Mathematical or scientific foundations
- Best practices that are technology-agnostic

### temporal (Time-sensitive / Trending)
Content whose value is closely tied to a specific point in time.
Its relevance decays significantly as time passes.

Examples of temporal content:
- Annual trend reports (e.g., "AI Trends 2024")
- Release notes or new feature introductions for specific versions
- Benchmark comparisons tied to specific hardware/software versions
- Conference keynotes focused on current events
- News articles, market analyses with specific dates
- Technology comparisons that will be outdated within 1-2 years

### unknown
Use this when the content does not clearly fit either category,
or when there is insufficient text to make a reliable judgment.

## Document Information

- Filename: {filename}
- File type: {file_extension}
- Text was truncated: {truncated}

## Document Content

{extracted_text}

## Output Format

Respond ONLY with the following JSON. Do not include any other text.

{{
  "classification": "evergreen" | "temporal" | "unknown",
  "confidence": 0.0 to 1.0,
  "reason": "Brief explanation of your classification decision",
  "topics": ["topic1", "topic2", ...]
}}
```

> **プロンプト設計の方針:**
>
> - 英語プロンプトを使用する。LLM の分類精度は英語プロンプトの方が安定する傾向がある
> - "Evergreen" / "Temporal" はコンテンツマーケティングやナレッジマネジメントで確立された概念であり、LLM の事前学習データに多数含まれるため判定精度の向上が期待できる
> - 具体例を豊富に記載し、境界ケースの判断を支援する
> - `reason` と `topics` は日本語ドキュメントに対しては日本語で返却される想定

### 7.3 API呼び出し制御

| パラメータ | デフォルト値 | 説明 |
| ----------- | ------------ | ------ |
| `max_retries` | 3 | API呼び出し失敗時の最大リトライ回数 |
| `retry_delay_sec` | 5 | リトライ間隔（秒）。指数バックオフ適用 |
| `rate_limit_rpm` | 30 | 1分あたりの最大リクエスト数 |
| `request_timeout_sec` | 120 | 1リクエストあたりのタイムアウト |
| `max_input_tokens` | 8000 | LLMに送るテキストの最大トークン数 |

---

## 8. CLI インターフェース

### 8.1 コマンド体系

```bash
# 基本実行（設定ファイルに input / output を定義済みの場合）
doc-triager run

# CLI でディレクトリを指定（設定ファイルの値を上書き）
doc-triager run --source <source_dir> --output <output_dir>

# ドライラン（ファイル移動を実行しない）
doc-triager run --dry-run

# 処理結果の確認
doc-triager status                          # 全体サマリー
doc-triager status --triage unknown # 特定分類の一覧

# 再分類（unknownのみ対象、閾値変更後の再処理等）
doc-triager reclassify --threshold 0.5

# DB操作
doc-triager db export --format json         # 結果をJSONエクスポート
doc-triager db export --format csv          # 結果をCSVエクスポート
```

### 8.2 設定値の優先順位

設定値は以下の優先順位で解決する（上が優先）:

1. CLI オプション（`--source`, `--output`, `--extensions` 等）
2. 設定ファイル（`--config` で指定、またはデフォルトパス）
3. デフォルト値（定義されている場合）

CLI オプションと設定ファイルのいずれにも値が指定されていない必須項目がある場合、エラーメッセージを表示して終了する。

### 8.3 オプション

| オプション | 省略形 | 説明 |
| ----------- | -------- | ------ |
| `--source` | `-s` | 入力ディレクトリのパス（設定ファイル `[input] directory` で指定可） |
| `--output` | `-o` | 出力ディレクトリのパス（設定ファイル `[output] directory` で指定可） |
| `--config` | `-c` | 設定ファイルのパス |
| `--dry-run` | | 分類のみ実行し、ファイル移動を行わない |
| `--verbose` | `-v` | 詳細ログ出力 |
| `--limit` | `-l` | 処理件数の上限 |
| `--extensions` | | 対象拡張子の指定（カンマ区切り） |

---

## 9. 設定ファイル

TOML形式を採用する。

```toml
[input]
directory = "/path/to/google-drive/documents"
# 除外パターン（glob）
exclude_patterns = [
    "*.DS_Store",
    "*.gitkeep",
    "__MACOSX/**",
]

[output]
directory = "/path/to/classified"
# temporal, evergreen, unknown サブディレクトリは自動作成

[triage]
confidence_threshold = 0.7
max_input_tokens = 8000

[llm]
provider = "openai"           # openai / anthropic / ollama
model = "gpt-4o"
api_key_env = "OPENAI_API_KEY"  # 環境変数名を指定（直書き禁止）
# Ollama用
# base_url = "http://localhost:11434"

[llm.rate_limit]
requests_per_minute = 30
max_retries = 3
retry_delay_sec = 5
request_timeout_sec = 120

[database]
path = "./triage.db"

[text_extraction]
# テキスト抽出不足とみなす最小文字数
min_text_length = 100
# MarkItDown の LLM 連携（画像描写等）を有効にするか
llm_description_enabled = false
# llm_description_enabled = true の場合に使用するモデル
# llm_description_model = "gpt-4o"

[logging]
level = "INFO"                 # DEBUG / INFO / WARNING / ERROR
file = "./doc-triager.log"
```

---

## 10. エラーハンドリング

### 10.1 エラー種別と対応

| エラー種別 | 対応 | DBへの記録 |
| ----------- | ------ | ----------- |
| テキスト抽出失敗 | `unknown` に分類。`error_message` に詳細記録 | ○ |
| LLM API エラー（一時的） | リトライ（指数バックオフ） | リトライ超過時のみ |
| LLM API エラー（認証等） | 処理を停止しエラーメッセージ表示 | × |
| LLMレスポンス パース失敗 | `unknown` に分類。生レスポンスを記録 | ○ |
| ファイル移動失敗 | エラーログ出力、処理続行 | ○ |
| ディスク容量不足 | 処理を停止 | × |

### 10.2 中断・再開

- 処理はファイル単位で独立しており、途中で中断しても再開可能
- 再開時はチェックサムベースで処理済みファイルを自動スキップ
- ファイルが変更されている場合（チェックサム不一致）は再処理する

---

## 11. 非機能要件

### 11.1 パフォーマンス

- LLM API呼び出しがボトルネックとなるため、レート制限を遵守しつつ効率的に処理する
- 並列処理は初期バージョンでは実装しない（API レート制限との兼ね合い）

### 11.2 ログ

- 処理の進捗をログファイルとコンソールに出力
- 各ファイルの処理結果（分類、confidence、reason）をログに記録
- 処理完了時にサマリーを出力（処理件数、各分類の件数、エラー件数）

### 11.3 セキュリティ

- APIキーは環境変数から取得する（設定ファイルに直書きしない）
- ドキュメント内容は外部LLM APIに送信されるため、機密ドキュメントの扱いに注意

---

## 12. 技術スタック

| コンポーネント | 技術 |
| ------------- | ------ |
| 言語 | Python 3.13+ |
| テキスト抽出 | **markitdown**（`pip install 'markitdown[all]'`） |
| DB | SQLite（sqlite3 標準ライブラリ） |
| 設定ファイル | TOML（tomllib 標準ライブラリ） |
| CLI | click or typer |
| LLM 連携 | litellm（マルチプロバイダ対応） |
| ログ | logging 標準ライブラリ |

> **Note:** MarkItDown が内部で PDF・DOCX・PPTX・XLSX 等の個別ライブラリを依存として管理するため、
> 個別のテキスト抽出ライブラリ（pypdf, python-docx, python-pptx等）を直接管理する必要はない。

---

## 13. 将来拡張

- MarkItDown の LLM 連携有効化（画像描写、スキャンPDFのOCR向上）
- 並列処理（asyncio / マルチプロセス）
- 分類基準のカスタムルール追加（ドメイン特化の判定基準）
- 分類結果のWebUI（unknown のレビュー効率化）
- MarkItDown プラグインの活用（サードパーティ形式対応）

# ADR-0001: プロジェクトツールチェインの選定

## ステータス

Accepted

## コンテキスト

doc-triager の開発環境・ツールチェインを決定する必要がある。
要件定義（REQUIREMENTS.md）では以下が指定されている:

- Python 3.12+
- CLI フレームワーク: click or typer
- 設定ファイル: TOML（tomllib 標準ライブラリ）
- DB: SQLite（sqlite3 標準ライブラリ）
- LLM 連携: litellm
- テキスト抽出: markitdown

## 決定事項

### 1. パッケージマネージャ: uv

**採用理由:**

- Astral 社が開発する高速な Python パッケージマネージャ
- pyproject.toml ベースで標準規格（PEP 621）に準拠
- ロックファイル（uv.lock）による再現性の確保
- Python バージョン管理も統合されている

**不採用:**

- pip + venv: ロックファイルの標準機構がない
- poetry: uv と比較して低速。独自の依存解決形式

### 2. CLI フレームワーク: typer

**検討の経緯:**

要件定義では「click or typer」と記載されていたが、サブコマンドが4つ程度（`run`, `status`, `reclassify`, `db export`）の規模であるため、そもそもフレームワークが必要かを検討した。

| 方法                       | 月間DL数（2026年1月）   | 評価                                 |
| -------------------------- | ----------------------- | ------------------------------------ |
| argparse（標準ライブラリ） | - (計測不可)            | 依存ゼロだがサブコマンドの記述が冗長 |
| click                      | 約4.9億（間接依存含む） | 成熟しているが typer の下位レイヤー  |
| typer                      | 約1.2億                 | 新規プロジェクトでの採用が伸びている |

**採用理由:**

- プライベートプロジェクトであり、新しいフレームワークを試すリスクが低い
- FastAPI 作者（tiangolo）が開発しており、比較的新しいフレームワークながら人気が伸びている
- PyPI ダウンロード数のトレンドで新規プロジェクトへの採用が最も伸びている
- Python の型ヒントから CLI を自動生成するため、ボイラープレートが少ない
- click ベースで実績のあるエコシステムを継承している
- typer が合わなかった場合でも argparse にフォールバックできるため、選定リスクが小さい

### 3. ビルドバックエンド: hatchling

**採用理由:**

- uv のデフォルトビルドバックエンド
- src layout に対応
- シンプルな設定で十分な機能

### 4. プロジェクトレイアウト: src layout

```text
doc-triager/
├── pyproject.toml
├── uv.lock
├── .python-version
├── src/
│   └── doc_triager/
│       └── __init__.py
├── tests/
├── docs/
└── .devcontainer/
```

**採用理由:**

- 配布可能な CLI パッケージとして `uv init --package` 相当の構成が適切
- テストコードとソースコードが明確に分離される
- インポートの問題を早期に検出できる

### 5. 開発環境: devcontainer

**構成方針:**

- ベースイメージ: `mcr.microsoft.com/devcontainers/python:3.12`
- uv のインストール: devcontainer feature（`ghcr.io/va-h/devcontainers-features/uv`）
- 初期化: `postCreateCommand` で `uv sync`

## 影響

- 開発者は uv をローカルにインストールするか、devcontainer を使用して開発する
- CLI コマンド `doc-triager` は `[project.scripts]` で定義し、`uv run doc-triager` で実行可能
- uv.lock をリポジトリにコミットし、環境の再現性を担保する

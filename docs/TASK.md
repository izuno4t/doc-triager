# TASKS

## Task List

| ID | Status | Summary | DependsOn |
| --- | --- | --- | --- |
| TASK-001 | ✅ | 設定ファイル読み込みモジュールを実装する | - |
| TASK-002 | ✅ | SQLiteデータベース操作モジュールを実装する | - |
| TASK-003 | ✅ | ファイルスキャン・フィルタリングモジュールを実装する | TASK-001 |
| TASK-004 | ✅ | チェックサム計算と重複判定モジュールを実装する | TASK-002 |
| TASK-005 | ✅ | MarkItDownテキスト抽出モジュールを実装する | TASK-001 |
| TASK-006 | ✅ | LLM分類リクエストモジュールを実装する | TASK-001 |
| TASK-007 | ✅ | ファイル移動モジュールを実装する | - |
| TASK-008 | ✅ | ロギング設定モジュールを実装する | TASK-001 |
| TASK-009 | ✅ | メイン処理フロー（runコマンド）を実装する | TASK-001,TASK-002,TASK-003,TASK-004,TASK-005,TASK-006,TASK-007,TASK-008 |
| TASK-010 | ⏳ | statusコマンドを実装する | TASK-002 |
| TASK-011 | ⏳ | reclassifyコマンドを実装する | TASK-002,TASK-006,TASK-007 |
| TASK-012 | ⏳ | db exportコマンドを実装する | TASK-002 |
| TASK-013 | ⏳ | エラーハンドリングとリトライ機構を実装する | TASK-006,TASK-009 |
| TASK-014 | ⏳ | 単体テストを作成する（config, db, scanner） | TASK-001,TASK-002,TASK-003 |
| TASK-015 | ⏳ | 単体テストを作成する（extractor, classifier, mover） | TASK-005,TASK-006,TASK-007 |
| TASK-016 | ⏳ | 統合テストを作成する（runコマンドE2E） | TASK-009 |

## Task Details (only when clarification needed)

### TASK-001

- Note: TOML形式。tomllib標準ライブラリで読み込み。設定項目は要件定義書§9に準拠
- Caution: APIキーは環境変数名のみ設定ファイルに記載し、値は環境変数から取得する

### TASK-002

- Note: テーブル定義は要件定義書§6.2に準拠。インデックス3つ含む
- Caution: triage_resultsテーブルのみ。マイグレーション機構は不要

### TASK-003

- Note: ソースディレクトリの再帰スキャン、拡張子フィルタリング、除外パターン適用
- Caution: 対象拡張子は要件定義書§3.2のMarkItDown対応形式に基づく

### TASK-005

- Note: MarkItDownのconvert()を呼び出し、text_contentを返す。min_text_length未満は抽出不足扱い
- Caution: 初期フェーズではllm_clientオプションは無効（テキスト抽出のみ）

### TASK-006

- Note: litellmを使用。プロンプトテンプレートは要件定義書§7.2に準拠
- Caution: レスポンスはJSON形式でパース。トランケート処理含む（先頭+末尾優先）

### TASK-009

- Note: 要件定義書§4.1のメインフロー全体を統合。処理サマリー出力含む
- Caution: dry-runモード時はファイル移動をスキップ。--limitオプション対応

### TASK-013

- Note: リトライは指数バックオフ。エラー種別ごとの対応は要件定義書§10.1に準拠
- Caution: 認証エラー等の致命的エラーは処理停止。一時的エラーのみリトライ対象

### TASK-016

- Note: テスト用のダミーファイルとモックLLMを使った統合テスト
- Caution: 実際のLLM APIは呼び出さない

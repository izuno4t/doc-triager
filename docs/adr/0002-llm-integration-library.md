# ADR-0002: LLM連携ライブラリの選定

## ステータス

Accepted

## コンテキスト

doc-triager はドキュメントの内容をLLMに送信し、分類結果（JSON）を受け取る。
対応プロバイダとして OpenAI、Anthropic、Ollama（ローカル）を要件定義で指定している。

マルチプロバイダ対応を実現するライブラリとして、litellm と LangChain を比較検討した。

## 検討

### 比較

| 観点 | litellm | LangChain |
| --- | --- | --- |
| 目的 | マルチLLMプロバイダの統一APIラッパー | LLMアプリケーション構築フレームワーク |
| 対応プロバイダ | 100+ (OpenAI, Anthropic, Ollama等) | 同等 |
| API | `completion()` 1関数でプロバイダ切替 | ChatModel抽象クラス + 各プロバイダパッケージ |
| 依存サイズ | 軽量（LLM呼び出し特化） | 重い（langchain-core + langchain + 各プロバイダパッケージ） |
| リトライ/レート制限 | 組み込み済み | 自前実装 or tenacity等で追加 |
| チェーン/RAG/エージェント | なし | あり |

### 本プロジェクトで必要な機能

- プロンプトを送ってJSON応答を受け取る
- 設定でプロバイダを切り替える
- リトライ・レート制限

チェーン、エージェント、RAG、メモリ等の機能は不要。
RAG・ベクトルDBは要件定義§1.3で明示的にスコープ外としている。

### 呼び出しコードの比較

litellm はプロバイダ切替がモデル名の変更だけで完結する:

```python
from litellm import completion
response = completion(model="gpt-4o", messages=[...])
response = completion(model="claude-sonnet-4-20250514", messages=[...])
response = completion(model="ollama/llama3", messages=[...])
```

LangChain はプロバイダごとにパッケージとクラスが異なる:

```python
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
# プロバイダごとに初期化・呼び出し方法が異なる
```

## 決定事項

### LLM連携ライブラリ: litellm

**採用理由:**

- 本プロジェクトの要件は「プロンプト送信→JSON応答取得」のみであり、litellm の守備範囲と一致する
- モデル名の変更だけでプロバイダを切り替えられるため、設定ファイルとの統合がシンプル
- リトライ・レート制限が組み込まれており、要件定義§7.3の要件をライブラリ側で対応できる
- 依存が軽量で、プロジェクト規模に対して過不足がない

**不採用:**

- LangChain: マルチプロバイダ対応は可能だが、本プロジェクトで使わない機能（チェーン、RAG、エージェント等）への依存が大きい。プロバイダごとに別パッケージのインストールとクラスの使い分けが必要で、設定ファイルからの動的切替が煩雑になる

### 後続プロジェクト（doc-searcher）との技術スタック統一について

LangChain は MCP 連携やRAG構築の機能を持つため、後続プロジェクト（doc-searcher）と技術スタックを統一する目的での採用も検討された。

しかし、要件定義§1.3・§1.5により doc-triager は doc-searcher の存在に依存しない設計としている。doc-triager の技術選定に doc-searcher の都合を持ち込むと、この分離設計を崩すことになる。

- MCP連携は doc-searcher（②）側の責務であり、doc-triager（①）のスコープ外
- doc-triager に LangChain を入れると、使わない依存を抱えるだけでなく、doc-searcher の技術選定に暗黙の制約を与える
- LangChain / MCP の検討は doc-searcher のADRで行う

## 影響

- `litellm` を唯一のLLM連携ライブラリとして使用する
- LLMプロバイダの追加は設定ファイルのモデル名変更で対応可能
- 将来 LangChain 固有の機能（チェーン等）が必要になった場合は再検討する

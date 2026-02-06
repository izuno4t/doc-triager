"""Tests for triage module."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch


from doc_triager.triage import (
    SummaryResult,
    TriageResult,
    build_classify_prompt,
    classify_document,
    apply_threshold,
    summarize_text,
)


class TestClassifyDocument:
    """Tests for classify_document function."""

    def _mock_response(self, content: str) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = content
        return mock_resp

    @patch("doc_triager.llm.litellm.completion")
    def test_returns_triage_result(self, mock_completion: MagicMock) -> None:
        response_json = json.dumps(
            {
                "classification": "evergreen",
                "confidence": 0.9,
                "reason": "Foundational content",
                "topics": ["design", "architecture"],
            }
        )
        mock_completion.return_value = self._mock_response(response_json)

        result = classify_document(
            text="Some document text about design patterns.",
            filename="design.pdf",
            file_extension=".pdf",
            truncated=False,
            model="openai/gpt-4o",
        )

        assert result.triage == "evergreen"
        assert result.confidence == 0.9
        assert result.reason == "Foundational content"
        assert result.topics == ["design", "architecture"]
        assert result.error is None

    @patch("doc_triager.llm.litellm.completion")
    def test_temporal_triage(self, mock_completion: MagicMock) -> None:
        response_json = json.dumps(
            {
                "classification": "temporal",
                "confidence": 0.85,
                "reason": "Version-specific content",
                "topics": ["spring-boot", "release-notes"],
            }
        )
        mock_completion.return_value = self._mock_response(response_json)

        result = classify_document(
            text="Spring Boot 3.2 new features.",
            filename="spring-boot-3.2-news.pdf",
            file_extension=".pdf",
            truncated=False,
            model="openai/gpt-4o",
        )

        assert result.triage == "temporal"
        assert result.confidence == 0.85

    @patch("doc_triager.llm.litellm.completion")
    def test_json_parse_error_returns_error(self, mock_completion: MagicMock) -> None:
        mock_completion.return_value = self._mock_response("This is not JSON at all.")

        result = classify_document(
            text="Some text",
            filename="test.pdf",
            file_extension=".pdf",
            truncated=False,
            model="openai/gpt-4o",
        )

        assert result.triage == "unknown"
        assert result.error is not None
        assert result.raw_response == "This is not JSON at all."

    @patch("doc_triager.llm.litellm.completion")
    def test_json_with_markdown_fence(self, mock_completion: MagicMock) -> None:
        response_json = json.dumps(
            {
                "classification": "evergreen",
                "confidence": 0.8,
                "reason": "Good content",
                "topics": ["testing"],
            }
        )
        fenced = f"```json\n{response_json}\n```"
        mock_completion.return_value = self._mock_response(fenced)

        result = classify_document(
            text="Some text",
            filename="test.pdf",
            file_extension=".pdf",
            truncated=False,
            model="openai/gpt-4o",
        )

        assert result.triage == "evergreen"
        assert result.confidence == 0.8
        assert result.error is None

    @patch("doc_triager.llm.litellm.completion")
    def test_api_error_returns_error(self, mock_completion: MagicMock) -> None:
        mock_completion.side_effect = Exception("API connection failed")

        result = classify_document(
            text="Some text",
            filename="test.pdf",
            file_extension=".pdf",
            truncated=False,
            model="openai/gpt-4o",
        )

        assert result.triage == "unknown"
        assert result.error is not None
        assert "API connection failed" in result.error

    @patch("doc_triager.llm.litellm.completion")
    def test_passes_model_and_timeout(self, mock_completion: MagicMock) -> None:
        response_json = json.dumps(
            {
                "classification": "evergreen",
                "confidence": 0.9,
                "reason": "Test",
                "topics": [],
            }
        )
        mock_completion.return_value = self._mock_response(response_json)

        classify_document(
            text="text",
            filename="test.pdf",
            file_extension=".pdf",
            truncated=False,
            model="anthropic/claude-sonnet-4-20250514",
            timeout=60,
        )

        call_kwargs = mock_completion.call_args
        assert call_kwargs.kwargs["model"] == "anthropic/claude-sonnet-4-20250514"
        assert call_kwargs.kwargs["timeout"] == 60

    @patch("doc_triager.llm.litellm.completion")
    def test_prompt_contains_filename_and_text(
        self, mock_completion: MagicMock
    ) -> None:
        response_json = json.dumps(
            {
                "classification": "evergreen",
                "confidence": 0.9,
                "reason": "Test",
                "topics": [],
            }
        )
        mock_completion.return_value = self._mock_response(response_json)

        classify_document(
            text="Content about algorithms",
            filename="algorithms.pdf",
            file_extension=".pdf",
            truncated=True,
            model="openai/gpt-4o",
        )

        call_kwargs = mock_completion.call_args
        messages = call_kwargs.kwargs["messages"]
        user_content = messages[0]["content"]
        assert "algorithms.pdf" in user_content
        assert "Content about algorithms" in user_content
        assert "True" in user_content or "true" in user_content.lower()


class TestApplyThreshold:
    """Tests for apply_threshold function."""

    def test_above_threshold_unchanged(self) -> None:
        result = TriageResult(
            triage="evergreen",
            confidence=0.9,
            reason="Foundational",
            topics=["design"],
        )

        applied = apply_threshold(result, threshold=0.7)

        assert applied.triage == "evergreen"
        assert applied.confidence == 0.9

    def test_below_threshold_becomes_unknown(self) -> None:
        result = TriageResult(
            triage="evergreen",
            confidence=0.5,
            reason="Somewhat foundational",
            topics=["design"],
        )

        applied = apply_threshold(result, threshold=0.7)

        assert applied.triage == "unknown"
        assert applied.confidence == 0.5

    def test_exact_threshold_unchanged(self) -> None:
        result = TriageResult(
            triage="temporal",
            confidence=0.7,
            reason="Time-sensitive",
            topics=["news"],
        )

        applied = apply_threshold(result, threshold=0.7)

        assert applied.triage == "temporal"

    def test_already_unknown_stays_unknown(self) -> None:
        result = TriageResult(
            triage="unknown",
            confidence=0.3,
            reason="Unclear content",
            topics=[],
        )

        applied = apply_threshold(result, threshold=0.7)

        assert applied.triage == "unknown"

    def test_error_result_not_changed(self) -> None:
        result = TriageResult(
            triage="unknown",
            confidence=0.0,
            reason="",
            topics=[],
            error="Parse error",
        )

        applied = apply_threshold(result, threshold=0.7)

        assert applied.triage == "unknown"
        assert applied.error == "Parse error"


class TestClassifyViaCliMode:
    """Tests for CLI mode classification via classify_document."""

    def _success_response(self) -> str:
        return json.dumps(
            {
                "classification": "evergreen",
                "confidence": 0.9,
                "reason": "Foundational content",
                "topics": ["design"],
            }
        )

    @patch("doc_triager.llm.subprocess.run")
    def test_classify_via_claude_cli(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=self._success_response(),
            stderr="",
        )

        result = classify_document(
            text="Some text",
            filename="test.pdf",
            file_extension=".pdf",
            truncated=False,
            model="claude-sonnet-4-20250514",
            mode="cli",
            provider="claude",
        )

        assert result.triage == "evergreen"
        assert result.confidence == 0.9
        assert result.error is None

        call_args = mock_run.call_args
        cmd = call_args.kwargs["args"]
        # claude はプロンプトを -p の引数として渡す
        assert cmd[0] == "claude"
        assert cmd[1] == "-p"
        # cmd[2] はプロンプトテキスト
        assert isinstance(cmd[2], str)
        assert cmd[3:] == [
            "--output-format",
            "text",
            "--model",
            "claude-sonnet-4-20250514",
        ]

    @patch("doc_triager.llm.subprocess.run")
    def test_classify_via_codex_cli(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["codex"],
            returncode=0,
            stdout=self._success_response(),
            stderr="",
        )

        result = classify_document(
            text="Some text",
            filename="test.pdf",
            file_extension=".pdf",
            truncated=False,
            model="o3",
            mode="cli",
            provider="codex",
        )

        assert result.triage == "evergreen"
        assert result.confidence == 0.9
        assert result.error is None

        call_args = mock_run.call_args
        cmd = call_args.kwargs["args"]
        assert cmd == ["codex", "exec", "-", "-m", "o3"]

    @patch("doc_triager.llm.subprocess.run")
    def test_cli_mode_command_not_found(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = FileNotFoundError(
            "[Errno 2] No such file or directory: 'claude'"
        )

        result = classify_document(
            text="Some text",
            filename="test.pdf",
            file_extension=".pdf",
            truncated=False,
            model="",
            mode="cli",
            provider="claude",
        )

        assert result.triage == "unknown"
        assert result.error is not None
        assert "見つかりません" in result.error

    @patch("doc_triager.llm.subprocess.run")
    def test_cli_mode_timeout(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=120)

        result = classify_document(
            text="Some text",
            filename="test.pdf",
            file_extension=".pdf",
            truncated=False,
            model="",
            mode="cli",
            provider="claude",
        )

        assert result.triage == "unknown"
        assert result.error is not None
        assert "タイムアウト" in result.error

    @patch("doc_triager.llm.subprocess.run")
    def test_cli_mode_nonzero_exit(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=1,
            stdout="",
            stderr="Some error occurred",
        )

        result = classify_document(
            text="Some text",
            filename="test.pdf",
            file_extension=".pdf",
            truncated=False,
            model="",
            mode="cli",
            provider="claude",
        )

        assert result.triage == "unknown"
        assert result.error is not None
        assert "CLI実行失敗" in result.error
        assert "Some error occurred" in result.error

    @patch("doc_triager.llm.subprocess.run")
    def test_claude_cli_without_model(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=self._success_response(),
            stderr="",
        )

        classify_document(
            text="Some text",
            filename="test.pdf",
            file_extension=".pdf",
            truncated=False,
            model="",
            mode="cli",
            provider="claude",
        )

        cmd = mock_run.call_args.kwargs["args"]
        # claude はプロンプトを -p の引数として渡す
        assert cmd[0] == "claude"
        assert cmd[1] == "-p"
        assert isinstance(cmd[2], str)
        assert cmd[3:] == ["--output-format", "text"]

    def test_unsupported_cli_provider_returns_error(self) -> None:
        result = classify_document(
            text="Some text",
            filename="test.pdf",
            file_extension=".pdf",
            truncated=False,
            model="",
            mode="cli",
            provider="unknown_cli",
        )

        assert result.triage == "unknown"
        assert result.error is not None
        assert "unknown_cli" in result.error


class TestClassifyDocumentDispatch:
    """Tests for mode-based dispatch in classify_document."""

    @patch("doc_triager.triage.call_claude")
    def test_cli_mode_dispatches_to_claude(self, mock_cli: MagicMock) -> None:
        response_json = json.dumps(
            {
                "classification": "evergreen",
                "confidence": 0.9,
                "reason": "test",
                "topics": [],
            }
        )
        mock_cli.return_value = response_json

        result = classify_document(
            text="Some text",
            filename="test.pdf",
            file_extension=".pdf",
            truncated=False,
            model="claude-sonnet-4-20250514",
            mode="cli",
            provider="claude",
        )

        assert result.triage == "evergreen"
        mock_cli.assert_called_once()
        call_kwargs = mock_cli.call_args.kwargs
        assert call_kwargs["model"] == "claude-sonnet-4-20250514"

    @patch("doc_triager.triage.call_codex")
    def test_cli_mode_dispatches_to_codex(self, mock_codex: MagicMock) -> None:
        response_json = json.dumps(
            {
                "classification": "temporal",
                "confidence": 0.85,
                "reason": "test",
                "topics": [],
            }
        )
        mock_codex.return_value = response_json

        result = classify_document(
            text="Some text",
            filename="test.pdf",
            file_extension=".pdf",
            truncated=False,
            model="o3",
            mode="cli",
            provider="codex",
        )

        assert result.triage == "temporal"
        mock_codex.assert_called_once()

    @patch("doc_triager.triage.call_api")
    def test_api_mode_uses_call_api(self, mock_api: MagicMock) -> None:
        response_json = json.dumps(
            {
                "classification": "evergreen",
                "confidence": 0.9,
                "reason": "Test",
                "topics": [],
            }
        )
        mock_api.return_value = response_json

        result = classify_document(
            text="Some text",
            filename="test.pdf",
            file_extension=".pdf",
            truncated=False,
            model="openai/gpt-4o",
            mode="api",
        )

        assert result.triage == "evergreen"
        mock_api.assert_called_once()


class TestSummarizeText:
    """Tests for summarize_text function."""

    def _mock_response(self, content: str) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = content
        return mock_resp

    @patch("doc_triager.llm.litellm.completion")
    def test_returns_summary_result(self, mock_completion: MagicMock) -> None:
        mock_completion.return_value = self._mock_response(
            "This document covers design patterns."
        )

        result = summarize_text(
            text="Long document about design patterns " * 100,
            filename="design.pdf",
            model="openai/gpt-4o",
        )

        assert isinstance(result, SummaryResult)
        assert result.summary == "This document covers design patterns."
        assert result.error is None

    @patch("doc_triager.llm.litellm.completion")
    def test_api_error_falls_back_to_original(self, mock_completion: MagicMock) -> None:
        mock_completion.side_effect = Exception("API connection failed")
        original = "Original document text"

        result = summarize_text(
            text=original,
            filename="test.pdf",
            model="openai/gpt-4o",
        )

        assert result.summary == original
        assert result.error is not None
        assert "API connection failed" in result.error

    @patch("doc_triager.llm.litellm.completion")
    def test_empty_response_falls_back(self, mock_completion: MagicMock) -> None:
        mock_completion.return_value = self._mock_response("")
        original = "Original document text"

        result = summarize_text(
            text=original,
            filename="test.pdf",
            model="openai/gpt-4o",
        )

        assert result.summary == original
        assert result.error is not None

    @patch("doc_triager.llm.litellm.completion")
    def test_prompt_contains_filename(self, mock_completion: MagicMock) -> None:
        mock_completion.return_value = self._mock_response("Summary content")

        summarize_text(
            text="Content about algorithms",
            filename="algorithms.pdf",
            model="openai/gpt-4o",
        )

        call_kwargs = mock_completion.call_args
        messages = call_kwargs.kwargs["messages"]
        user_content = messages[0]["content"]
        assert "algorithms.pdf" in user_content
        assert "Content about algorithms" in user_content

    @patch("doc_triager.triage.call_claude")
    def test_cli_mode_claude(self, mock_cli: MagicMock) -> None:
        mock_cli.return_value = "Summarized via claude"

        result = summarize_text(
            text="Some text",
            filename="test.pdf",
            model="claude-sonnet-4-20250514",
            mode="cli",
            provider="claude",
        )

        assert result.summary == "Summarized via claude"
        assert result.error is None
        mock_cli.assert_called_once()

    @patch("doc_triager.triage.call_codex")
    def test_cli_mode_codex(self, mock_codex: MagicMock) -> None:
        mock_codex.return_value = "Summarized via codex"

        result = summarize_text(
            text="Some text",
            filename="test.pdf",
            model="o3",
            mode="cli",
            provider="codex",
        )

        assert result.summary == "Summarized via codex"
        assert result.error is None
        mock_codex.assert_called_once()

    def test_unsupported_provider_falls_back(self) -> None:
        original = "Original text"

        result = summarize_text(
            text=original,
            filename="test.pdf",
            model="",
            mode="cli",
            provider="unknown_cli",
        )

        assert result.summary == original
        assert result.error is not None

    @patch("doc_triager.triage.call_claude")
    def test_cli_timeout_falls_back(self, mock_cli: MagicMock) -> None:
        mock_cli.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=120)
        original = "Original text"

        result = summarize_text(
            text=original,
            filename="test.pdf",
            model="",
            mode="cli",
            provider="claude",
        )

        assert result.summary == original
        assert result.error is not None


class TestClassifyDocumentFilePath:
    """Tests for file_path parameter in classify_document."""

    def _success_json(self) -> str:
        return json.dumps(
            {
                "classification": "evergreen",
                "confidence": 0.9,
                "reason": "Foundational content",
                "topics": ["design"],
            }
        )

    @patch("doc_triager.triage.call_claude")
    def test_cli_claude_does_not_pass_file_path_to_call(
        self, mock_cli: MagicMock
    ) -> None:
        """_call_llm → call_claude に file_path が渡されない。"""
        mock_cli.return_value = self._success_json()

        classify_document(
            text="",
            filename="slides.pdf",
            file_extension=".pdf",
            truncated=False,
            model="claude-sonnet-4-20250514",
            mode="cli",
            provider="claude",
            file_path=Path("/tmp/slides.pdf"),
        )

        mock_cli.assert_called_once()
        call_kwargs = mock_cli.call_args.kwargs
        assert "file_path" not in call_kwargs

    @patch("doc_triager.triage.call_claude")
    def test_file_mode_uses_classify_file_template(self, mock_cli: MagicMock) -> None:
        """file_path 指定時に classify_file.txt テンプレートが使用される。"""
        mock_cli.return_value = self._success_json()

        classify_document(
            text="",
            filename="slides.pdf",
            file_extension=".pdf",
            truncated=False,
            model="claude-sonnet-4-20250514",
            mode="cli",
            provider="claude",
            file_path=Path("/tmp/slides.pdf"),
        )

        call_kwargs = mock_cli.call_args.kwargs
        prompt = call_kwargs["prompt"]
        # classify_file.txt 固有の文言が含まれる（@ 参照）
        assert "@/tmp/slides.pdf" in prompt
        # classify.txt 固有の文言（extracted_text プレースホルダの展開結果）が含まれない
        assert "{extracted_text}" not in prompt

    @patch("doc_triager.triage.call_claude")
    def test_file_mode_prompt_contains_filename(self, mock_cli: MagicMock) -> None:
        """file_path 指定時のプロンプトにファイル名と拡張子が含まれる。"""
        mock_cli.return_value = self._success_json()

        classify_document(
            text="",
            filename="report.pptx",
            file_extension=".pptx",
            truncated=False,
            model="claude-sonnet-4-20250514",
            mode="cli",
            provider="claude",
            file_path=Path("/tmp/report.pptx"),
        )

        call_kwargs = mock_cli.call_args.kwargs
        prompt = call_kwargs["prompt"]
        assert "report.pptx" in prompt
        assert ".pptx" in prompt

    @patch("doc_triager.triage.call_claude")
    def test_text_mode_unchanged(self, mock_cli: MagicMock) -> None:
        """file_path=None 時は既存動作（classify.txt 使用）のまま。"""
        mock_cli.return_value = self._success_json()

        classify_document(
            text="Some document content",
            filename="test.pdf",
            file_extension=".pdf",
            truncated=False,
            model="claude-sonnet-4-20250514",
            mode="cli",
            provider="claude",
        )

        call_kwargs = mock_cli.call_args.kwargs
        prompt = call_kwargs["prompt"]
        # テキストモードでは extracted_text の内容がプロンプトに含まれる
        assert "Some document content" in prompt
        # file_path は渡されない
        assert "file_path" not in call_kwargs


class TestBuildClassifyPrompt:
    """Tests for build_classify_prompt function."""

    def test_build_prompt_file_mode(self) -> None:
        """file_path 指定時に classify_file.txt テンプレートが使用される。"""
        prompt = build_classify_prompt(
            filename="slides.pdf",
            file_extension=".pdf",
            file_path=Path("/tmp/slides.pdf"),
        )

        # classify_file.txt の特徴的な文言（@ 参照）
        assert "@/tmp/slides.pdf" in prompt
        assert "slides.pdf" in prompt
        assert ".pdf" in prompt
        # テキストモード固有のプレースホルダが展開されていないこと
        assert "{extracted_text}" not in prompt

    def test_build_prompt_text_mode(self) -> None:
        """file_path=None 時に classify.txt テンプレートが使用される。"""
        prompt = build_classify_prompt(
            filename="doc.pdf",
            file_extension=".pdf",
            text="Document content about algorithms",
            truncated=True,
        )

        assert "doc.pdf" in prompt
        assert ".pdf" in prompt
        assert "Document content about algorithms" in prompt
        assert "True" in prompt or "true" in prompt.lower()

    def test_build_prompt_text_mode_defaults(self) -> None:
        """text と truncated のデフォルト値で動作する。"""
        prompt = build_classify_prompt(
            filename="test.txt",
            file_extension=".txt",
        )

        assert "test.txt" in prompt
        assert ".txt" in prompt

    def test_build_prompt_file_mode_contains_classification_criteria(self) -> None:
        """file モードのプロンプトに分類基準が含まれる。"""
        prompt = build_classify_prompt(
            filename="report.pptx",
            file_extension=".pptx",
            file_path=Path("/tmp/report.pptx"),
        )

        assert "evergreen" in prompt
        assert "temporal" in prompt
        assert "/tmp/report.pptx" in prompt

    def test_build_prompt_text_mode_contains_classification_criteria(self) -> None:
        """text モードのプロンプトに分類基準が含まれる。"""
        prompt = build_classify_prompt(
            filename="report.pdf",
            file_extension=".pdf",
            text="Some text",
        )

        assert "evergreen" in prompt
        assert "temporal" in prompt

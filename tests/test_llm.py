"""Tests for llm module."""

import subprocess
from unittest.mock import MagicMock, patch

from doc_triager.llm import (
    build_claude_cmd,
    build_codex_cmd,
    call_api,
    call_claude,
    call_codex,
)


class TestCallApi:
    """Tests for call_api function (litellm backend)."""

    def _mock_response(self, content: str) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = content
        return mock_resp

    @patch("doc_triager.llm.litellm.completion")
    def test_returns_raw_response(self, mock_completion: MagicMock) -> None:
        expected = "some LLM output"
        mock_completion.return_value = self._mock_response(expected)

        result = call_api(
            prompt="test prompt",
            model="openai/gpt-4o",
            timeout=120,
        )

        assert result == expected

    @patch("doc_triager.llm.litellm.completion")
    def test_passes_model_and_timeout(self, mock_completion: MagicMock) -> None:
        mock_completion.return_value = self._mock_response("output")

        call_api(
            prompt="test prompt",
            model="anthropic/claude-sonnet-4-20250514",
            timeout=60,
        )

        call_kwargs = mock_completion.call_args.kwargs
        assert call_kwargs["model"] == "anthropic/claude-sonnet-4-20250514"
        assert call_kwargs["timeout"] == 60

    @patch("doc_triager.llm.litellm.completion")
    def test_passes_api_base(self, mock_completion: MagicMock) -> None:
        mock_completion.return_value = self._mock_response("output")

        call_api(
            prompt="test prompt",
            model="ollama/llama3",
            timeout=120,
            api_base="http://localhost:11434",
        )

        call_kwargs = mock_completion.call_args.kwargs
        assert call_kwargs["api_base"] == "http://localhost:11434"

    @patch("doc_triager.llm.litellm.completion")
    def test_api_base_not_passed_when_none(self, mock_completion: MagicMock) -> None:
        mock_completion.return_value = self._mock_response("output")

        call_api(
            prompt="test prompt",
            model="openai/gpt-4o",
            timeout=120,
            api_base=None,
        )

        call_kwargs = mock_completion.call_args.kwargs
        assert "api_base" not in call_kwargs

    @patch("doc_triager.llm.litellm.completion")
    def test_api_error_raises(self, mock_completion: MagicMock) -> None:
        mock_completion.side_effect = Exception("API connection failed")

        try:
            call_api(prompt="test", model="openai/gpt-4o", timeout=120)
            assert False, "Expected exception"
        except Exception as e:
            assert "API connection failed" in str(e)


class TestCallClaude:
    """Tests for call_claude function."""

    @patch("doc_triager.llm.subprocess.run")
    def test_returns_stdout(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout="LLM output text",
            stderr="",
        )

        result = call_claude(
            prompt="test prompt",
            model="claude-sonnet-4-20250514",
            timeout=120,
        )

        assert result == "LLM output text"

    @patch("doc_triager.llm.subprocess.run")
    def test_command_structure_with_model(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"], returncode=0, stdout="out", stderr=""
        )

        call_claude(prompt="p", model="my-model", timeout=120)

        call_args = mock_run.call_args
        cmd = call_args.kwargs["args"]
        assert cmd == [
            "claude",
            "-p",
            "--output-format",
            "text",
            "--model",
            "my-model",
        ]
        assert call_args.kwargs["input"] == "p"
        assert call_args.kwargs["timeout"] == 120

    @patch("doc_triager.llm.subprocess.run")
    def test_command_structure_without_model(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"], returncode=0, stdout="out", stderr=""
        )

        call_claude(prompt="p", model=None, timeout=120)

        cmd = mock_run.call_args.kwargs["args"]
        assert cmd == ["claude", "-p", "--output-format", "text"]

    @patch("doc_triager.llm.subprocess.run")
    def test_command_not_found_raises(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = FileNotFoundError(
            "[Errno 2] No such file or directory: 'claude'"
        )

        try:
            call_claude(prompt="p", model=None, timeout=120)
            assert False, "Expected exception"
        except FileNotFoundError:
            pass

    @patch("doc_triager.llm.subprocess.run")
    def test_timeout_raises(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=120)

        try:
            call_claude(prompt="p", model=None, timeout=120)
            assert False, "Expected exception"
        except subprocess.TimeoutExpired:
            pass

    @patch("doc_triager.llm.subprocess.run")
    def test_nonzero_exit_raises(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=1,
            stdout="",
            stderr="Some error occurred",
        )

        try:
            call_claude(prompt="p", model=None, timeout=120)
            assert False, "Expected exception"
        except RuntimeError as e:
            assert "CLI実行失敗" in str(e)
            assert "Some error occurred" in str(e)


class TestCallCodex:
    """Tests for call_codex function."""

    @patch("doc_triager.llm.subprocess.run")
    def test_returns_stdout(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["codex"],
            returncode=0,
            stdout="LLM output text",
            stderr="",
        )

        result = call_codex(
            prompt="test prompt",
            model="o3",
            timeout=120,
        )

        assert result == "LLM output text"

    @patch("doc_triager.llm.subprocess.run")
    def test_command_structure_with_model(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["codex"], returncode=0, stdout="out", stderr=""
        )

        call_codex(prompt="p", model="o3", timeout=120)

        call_args = mock_run.call_args
        cmd = call_args.kwargs["args"]
        assert cmd == ["codex", "exec", "-", "-m", "o3"]
        assert call_args.kwargs["input"] == "p"
        assert call_args.kwargs["timeout"] == 120

    @patch("doc_triager.llm.subprocess.run")
    def test_command_structure_without_model(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["codex"], returncode=0, stdout="out", stderr=""
        )

        call_codex(prompt="p", model=None, timeout=120)

        cmd = mock_run.call_args.kwargs["args"]
        assert cmd == ["codex", "exec", "-"]

    @patch("doc_triager.llm.subprocess.run")
    def test_command_not_found_raises(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = FileNotFoundError(
            "[Errno 2] No such file or directory: 'codex'"
        )

        try:
            call_codex(prompt="p", model=None, timeout=120)
            assert False, "Expected exception"
        except FileNotFoundError:
            pass

    @patch("doc_triager.llm.subprocess.run")
    def test_timeout_raises(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="codex", timeout=120)

        try:
            call_codex(prompt="p", model=None, timeout=120)
            assert False, "Expected exception"
        except subprocess.TimeoutExpired:
            pass

    @patch("doc_triager.llm.subprocess.run")
    def test_nonzero_exit_raises(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["codex"],
            returncode=1,
            stdout="",
            stderr="Codex error",
        )

        try:
            call_codex(prompt="p", model=None, timeout=120)
            assert False, "Expected exception"
        except RuntimeError as e:
            assert "CLI実行失敗" in str(e)
            assert "Codex error" in str(e)


class TestBuildClaudeCmd:
    """Tests for build_claude_cmd function."""

    def test_build_claude_cmd_minimal(self) -> None:
        """model=None で最小 cmd を返す。"""
        cmd = build_claude_cmd(model=None)
        assert cmd == ["claude", "-p", "--output-format", "text"]

    def test_build_claude_cmd_with_model(self) -> None:
        """model 指定時に --model が含まれる。"""
        cmd = build_claude_cmd(model="my-model")
        assert cmd == ["claude", "-p", "--output-format", "text", "--model", "my-model"]

    def test_build_claude_cmd_no_file_flag(self) -> None:
        """build_claude_cmd は -f フラグを含まない。"""
        cmd = build_claude_cmd(model="claude-sonnet-4-20250514")
        assert "-f" not in cmd

    @patch("doc_triager.llm.subprocess.run")
    def test_call_claude_uses_build_cmd(self, mock_run: MagicMock) -> None:
        """call_claude が build_claude_cmd を使用している。"""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"], returncode=0, stdout="output", stderr=""
        )

        call_claude(
            prompt="test",
            model="my-model",
            timeout=120,
        )

        cmd = mock_run.call_args.kwargs["args"]
        expected = build_claude_cmd(model="my-model")
        assert cmd == expected


class TestBuildCodexCmd:
    """Tests for build_codex_cmd function."""

    def test_build_codex_cmd_with_model(self) -> None:
        """model 指定時に正しい cmd リストを返す。"""
        cmd = build_codex_cmd(model="o3")
        assert cmd == ["codex", "exec", "-", "-m", "o3"]

    def test_build_codex_cmd_minimal(self) -> None:
        """model=None で最小 cmd を返す。"""
        cmd = build_codex_cmd(model=None)
        assert cmd == ["codex", "exec", "-"]

    @patch("doc_triager.llm.subprocess.run")
    def test_call_codex_uses_build_cmd(self, mock_run: MagicMock) -> None:
        """call_codex が build_codex_cmd を使用している。"""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["codex"], returncode=0, stdout="output", stderr=""
        )

        call_codex(prompt="test", model="o3", timeout=120)

        cmd = mock_run.call_args.kwargs["args"]
        expected = build_codex_cmd(model="o3")
        assert cmd == expected

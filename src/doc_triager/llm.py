"""LLM backend module for doc-triager.

Provides low-level LLM call implementations:
- call_api: litellm-based API calls
- call_claude: claude CLI subprocess calls
- call_codex: codex CLI subprocess calls
"""

from __future__ import annotations

import logging
import subprocess

import litellm

logger = logging.getLogger(__name__)


def call_api(
    *,
    prompt: str,
    model: str,
    timeout: int,
    api_base: str | None = None,
) -> str:
    """Call LLM via litellm API.

    Args:
        prompt: The prompt text.
        model: litellm model string (e.g. "openai/gpt-4o").
        timeout: Request timeout in seconds.
        api_base: Optional API base URL (for Ollama etc).

    Returns:
        Raw response text from the LLM.

    Raises:
        Exception: On API call failure.
    """
    kwargs: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "timeout": timeout,
    }
    if api_base:
        kwargs["api_base"] = api_base

    response = litellm.completion(**kwargs)
    raw = response.choices[0].message.content
    logger.debug("LLM APIレスポンス: %s", raw)
    return raw


def _run_cli(
    *,
    cmd: list[str],
    prompt: str,
    timeout: int,
) -> str:
    """Execute a CLI command and return stdout.

    Args:
        cmd: Command and arguments.
        prompt: Text to pass via stdin.
        timeout: Subprocess timeout in seconds.

    Returns:
        Raw stdout text.

    Raises:
        FileNotFoundError: If CLI command is not found.
        subprocess.TimeoutExpired: If CLI execution times out.
        RuntimeError: If CLI exits with non-zero code.
    """
    result = subprocess.run(
        args=cmd,
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        msg = f"CLI実行失敗 (code={result.returncode}): {result.stderr}"
        raise RuntimeError(msg)

    logger.debug("CLIレスポンス: %s", result.stdout)
    return result.stdout


def build_claude_cmd(
    *,
    model: str | None,
) -> list[str]:
    """Build claude CLI command list without executing.

    Args:
        model: Optional model name for --model option.

    Returns:
        Command list suitable for subprocess execution.
    """
    cmd = ["claude", "-p", "--output-format", "text"]
    if model:
        cmd.extend(["--model", model])
    return cmd


def call_claude(
    *,
    prompt: str,
    model: str | None,
    timeout: int,
) -> str:
    """Call LLM via claude CLI.

    Args:
        prompt: The prompt text to send via stdin.
        model: Optional model name for --model option.
        timeout: Subprocess timeout in seconds.

    Returns:
        Raw response text from stdout.

    Raises:
        FileNotFoundError: If claude command is not found.
        subprocess.TimeoutExpired: If execution times out.
        RuntimeError: If CLI exits with non-zero code.
    """
    cmd = build_claude_cmd(model=model)
    return _run_cli(cmd=cmd, prompt=prompt, timeout=timeout)


def build_codex_cmd(
    *,
    model: str | None,
) -> list[str]:
    """Build codex CLI command list without executing.

    Args:
        model: Optional model name for -m option.

    Returns:
        Command list suitable for subprocess execution.
    """
    cmd = ["codex", "exec", "-"]
    if model:
        cmd.extend(["-m", model])
    return cmd


def call_codex(
    *,
    prompt: str,
    model: str | None,
    timeout: int,
) -> str:
    """Call LLM via codex CLI.

    Args:
        prompt: The prompt text to send via stdin.
        model: Optional model name for -m option.
        timeout: Subprocess timeout in seconds.

    Returns:
        Raw response text from stdout.

    Raises:
        FileNotFoundError: If codex command is not found.
        subprocess.TimeoutExpired: If execution times out.
        RuntimeError: If CLI exits with non-zero code.
    """
    cmd = build_codex_cmd(model=model)
    return _run_cli(cmd=cmd, prompt=prompt, timeout=timeout)

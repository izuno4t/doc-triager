"""Document triage module for doc-triager.

Handles prompt construction, response parsing, and classification dispatch.
LLM call implementations are delegated to the llm module.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from doc_triager.llm import call_api, call_claude, call_codex

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).parent / "prompt"


def _load_prompt(name: str) -> str:
    """Load a prompt template from the prompt directory."""
    return (_PROMPT_DIR / name).read_text(encoding="utf-8")


@dataclass
class SummaryResult:
    """Result of LLM text summarization."""

    summary: str = ""
    error: str | None = None


@dataclass
class TriageResult:
    """Result of LLM triage."""

    triage: str = "unknown"
    confidence: float = 0.0
    reason: str = ""
    topics: list[str] = field(default_factory=list)
    error: str | None = None
    raw_response: str | None = None


def _call_llm(
    *,
    prompt: str,
    model: str,
    timeout: int,
    api_base: str | None = None,
    mode: str = "api",
    provider: str = "",
    file_path: Path | None = None,
) -> str:
    """Dispatch an LLM call to the appropriate backend.

    Raises:
        ValueError: If CLI provider is unsupported.
        FileNotFoundError: If CLI command not found.
        subprocess.TimeoutExpired: If CLI times out.
        RuntimeError: If CLI execution fails.
        Exception: If API call fails.
    """
    if mode == "cli":
        callers = {
            "claude": call_claude,
            "codex": call_codex,
        }
        caller = callers.get(provider)
        if caller is None:
            raise ValueError(f"未対応のCLIプロバイダ: {provider}")
        kwargs: dict = {"prompt": prompt, "model": model, "timeout": timeout}
        if provider == "claude" and file_path is not None:
            kwargs["file_path"] = file_path
        return caller(**kwargs)
    else:
        return call_api(prompt=prompt, model=model, timeout=timeout, api_base=api_base)


def summarize_text(
    *,
    text: str,
    filename: str,
    model: str,
    timeout: int = 120,
    api_base: str | None = None,
    mode: str = "api",
    provider: str = "",
) -> SummaryResult:
    """Summarize document text using LLM for classification preprocessing.

    On failure, falls back to the original text.

    Args:
        text: Document text to summarize.
        filename: Original filename.
        model: LLM model string.
        timeout: Request timeout in seconds.
        api_base: Optional API base URL.
        mode: "api" or "cli".
        provider: CLI provider name.

    Returns:
        SummaryResult with summary or fallback to original text.
    """
    prompt = _load_prompt("summary.txt").format(filename=filename, text=text)

    try:
        raw = _call_llm(
            prompt=prompt,
            model=model,
            timeout=timeout,
            api_base=api_base,
            mode=mode,
            provider=provider,
        )
    except Exception as e:
        logger.warning("要約LLM呼び出し失敗（フォールバック）: %s", e)
        return SummaryResult(summary=text, error=str(e))

    if not raw or not raw.strip():
        logger.warning("要約レスポンスが空（フォールバック）")
        return SummaryResult(summary=text, error="要約レスポンスが空です")

    logger.debug("要約レスポンス: %s", raw)
    return SummaryResult(summary=raw.strip())


def _extract_json(text: str) -> str:
    """Extract JSON from response, handling markdown code fences."""
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def _parse_response(raw: str) -> TriageResult:
    """Parse LLM response into TriageResult."""
    json_str = _extract_json(raw)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        return TriageResult(
            error=f"JSONパース失敗: {e}",
            raw_response=raw,
        )

    return TriageResult(
        triage=data.get("classification", "unknown"),
        confidence=float(data.get("confidence", 0.0)),
        reason=data.get("reason", ""),
        topics=data.get("topics", []),
    )


def build_classify_prompt(
    *,
    filename: str,
    file_extension: str,
    text: str = "",
    truncated: bool = False,
    file_path: Path | None = None,
) -> str:
    """Build classification prompt string.

    Args:
        filename: Original filename.
        file_extension: File extension (e.g. ".pdf").
        text: Extracted document text. Used when file_path is None.
        truncated: Whether the text was truncated. Used when file_path is None.
        file_path: If set, uses the file-direct prompt template.

    Returns:
        Formatted prompt string.
    """
    if file_path is not None:
        return _load_prompt("classify_file.txt").format(
            filename=filename,
            file_extension=file_extension,
        )
    else:
        return _load_prompt("classify.txt").format(
            filename=filename,
            file_extension=file_extension,
            truncated=truncated,
            extracted_text=text,
        )


def classify_document(
    *,
    text: str,
    filename: str,
    file_extension: str,
    truncated: bool,
    model: str,
    timeout: int = 120,
    api_base: str | None = None,
    mode: str = "api",
    provider: str = "",
    file_path: Path | None = None,
) -> TriageResult:
    """Classify a document using LLM.

    Args:
        text: Extracted document text.
        filename: Original filename.
        file_extension: File extension (e.g. ".pdf").
        truncated: Whether the text was truncated.
        model: litellm model string (e.g. "openai/gpt-4o") or CLI model name.
        timeout: Request timeout in seconds.
        api_base: Optional API base URL (for Ollama etc).
        mode: "api" (litellm) or "cli" (CLI subprocess).
        provider: CLI provider name (e.g. "claude", "codex"). Used when mode="cli".
        file_path: Optional file path for direct file attachment (CLI claude only).

    Returns:
        TriageResult with triage or error.
    """
    prompt = build_classify_prompt(
        filename=filename,
        file_extension=file_extension,
        text=text,
        truncated=truncated,
        file_path=file_path,
    )

    try:
        raw = _call_llm(
            prompt=prompt,
            model=model,
            timeout=timeout,
            api_base=api_base,
            mode=mode,
            provider=provider,
            file_path=file_path,
        )
    except ValueError as e:
        return TriageResult(error=str(e))
    except FileNotFoundError:
        return TriageResult(
            error=f"CLIコマンド '{provider}' が見つかりません",
        )
    except subprocess.TimeoutExpired:
        return TriageResult(
            error=f"CLI実行がタイムアウトしました ({timeout}秒)",
        )
    except RuntimeError as e:
        return TriageResult(error=str(e))
    except Exception as e:
        logger.warning("LLM呼び出し失敗: %s", e)
        return TriageResult(error=str(e))

    logger.debug("LLMレスポンス: %s", raw)
    return _parse_response(raw)


def apply_threshold(
    result: TriageResult,
    *,
    threshold: float,
) -> TriageResult:
    """Apply confidence threshold, changing triage to unknown if below.

    Args:
        result: Original triage result.
        threshold: Confidence threshold.

    Returns:
        TriageResult with possibly changed triage.
    """
    if result.error is not None:
        return result

    if result.confidence < threshold and result.triage != "unknown":
        logger.info(
            "確信度 %.2f < 閾値 %.2f: %s → unknown",
            result.confidence,
            threshold,
            result.triage,
        )
        result.triage = "unknown"

    return result

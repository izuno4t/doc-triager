"""Main processing pipeline for doc-triager."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from doc_triager.checksum import compute_checksum, is_processed
from doc_triager.triage import apply_threshold, classify_document, summarize_text
from doc_triager.config import Config
from doc_triager.database import insert_result
from doc_triager.extractor import extract_text, truncate_text
from doc_triager.mover import move_file

logger = logging.getLogger(__name__)


def _is_file_direct_mode(cfg: Config) -> bool:
    """Check if file direct mode is active (CLI + claude)."""
    return cfg.llm.mode == "cli" and cfg.llm.provider == "claude"


def process_file(
    *,
    file_path: Path,
    cfg: Config,
    dry_run: bool,
    debug_dir: Path | None = None,
) -> dict[str, Any]:
    """Process a single file through the full triage pipeline.

    Returns:
        dict with keys: triage, confidence, reason, topics,
        destination_path, skipped, error.
    """
    source_dir = Path(cfg.input.directory)
    output_dir = Path(cfg.output.directory)
    db_path = Path(cfg.database.path)

    # [3.1] チェックサム計算
    checksum = compute_checksum(file_path)
    file_size = file_path.stat().st_size

    # [3.2] DB照合 - 処理済みならスキップ
    if is_processed(db_path, file_path):
        logger.info("  スキップ（処理済み）")
        return {"triage": None, "skipped": True}

    # ファイル直接モード判定
    file_direct = _is_file_direct_mode(cfg)

    mode = cfg.llm.mode
    timeout = cfg.llm.rate_limit.request_timeout_sec
    base_url = cfg.llm.base_url

    if mode == "api":
        model = f"{cfg.llm.provider}/{cfg.llm.model}"
    else:
        model = cfg.llm.model

    if file_direct:
        # [3.3-alt] ファイル直接モード: 抽出/トランケート/要約をスキップ
        logger.info("  ファイル直接モード（CLI claude）")
        cls_result = classify_document(
            text="",
            filename=file_path.name,
            file_extension=file_path.suffix,
            truncated=False,
            model=model,
            timeout=timeout,
            api_base=base_url,
            mode=mode,
            provider=cfg.llm.provider,
            file_path=file_path,
        )

        extracted_text_length = 0
        truncated = False
    else:
        # [3.3] テキスト抽出
        extraction = extract_text(
            file_path,
            min_text_length=cfg.text_extraction.min_text_length,
            source_dir=source_dir,
            debug_dir=debug_dir,
        )

        if extraction.error:
            logger.warning("  抽出エラー: %s", extraction.error)
            _record_result(
                db_path=db_path,
                cfg=cfg,
                file_path=file_path,
                checksum=checksum,
                file_size=file_size,
                triage="unknown",
                confidence=0.0,
                reason="テキスト抽出失敗",
                topics=[],
                extracted_text_length=0,
                truncated=False,
                error_message=extraction.error,
                destination_path=None,
            )
            return {
                "triage": "unknown",
                "confidence": 0.0,
                "skipped": False,
                "error": extraction.error,
                "destination_path": None,
            }

        if extraction.insufficient:
            logger.info("  テキスト不足 → unknown")
            text_len = len(extraction.text.strip()) if extraction.text else 0
            _record_result(
                db_path=db_path,
                cfg=cfg,
                file_path=file_path,
                checksum=checksum,
                file_size=file_size,
                triage="unknown",
                confidence=0.0,
                reason="テキスト抽出不足",
                topics=[],
                extracted_text_length=text_len,
                truncated=False,
                error_message=None,
                destination_path=None,
            )
            return {
                "triage": "unknown",
                "confidence": 0.0,
                "skipped": False,
                "error": None,
                "destination_path": None,
            }

        # [3.4] テキストトランケート + [要約] + LLM分類
        text = extraction.text
        trunc_result = truncate_text(text, max_length=cfg.triage.max_input_tokens)

        # [3.4.1] オプション要約
        classify_text = trunc_result.text
        if cfg.text_extraction.llm_summary_enabled:
            logger.info("  要約ステップ実行中...")
            summary_result = summarize_text(
                text=trunc_result.text,
                filename=file_path.name,
                model=model,
                timeout=timeout,
                api_base=base_url,
                mode=mode,
                provider=cfg.llm.provider,
            )
            if summary_result.error:
                logger.warning(
                    "  要約失敗（元テキストで分類続行）: %s", summary_result.error
                )
            else:
                logger.info("  要約完了")
            classify_text = summary_result.summary

        cls_result = classify_document(
            text=classify_text,
            filename=file_path.name,
            file_extension=file_path.suffix,
            truncated=trunc_result.truncated,
            model=model,
            timeout=timeout,
            api_base=base_url,
            mode=mode,
            provider=cfg.llm.provider,
        )

        extracted_text_length = len(text)
        truncated = trunc_result.truncated

    # [3.5] 閾値チェック
    cls_result = apply_threshold(cls_result, threshold=cfg.triage.confidence_threshold)

    logger.info(
        "  分類: %s (%.2f) - %s",
        cls_result.triage,
        cls_result.confidence,
        cls_result.reason,
    )

    # [3.6] ファイル移動（dry-runでなければ）
    destination_path: str | None = None
    if not dry_run:
        try:
            dest = move_file(
                file_path,
                source_dir=source_dir,
                output_dir=output_dir,
                triage=cls_result.triage,
            )
            destination_path = str(dest)
        except OSError as e:
            logger.error("  ファイル移動失敗: %s", e)

    # [3.7] DB記録
    _record_result(
        db_path=db_path,
        cfg=cfg,
        file_path=file_path,
        checksum=checksum,
        file_size=file_size,
        triage=cls_result.triage,
        confidence=cls_result.confidence,
        reason=cls_result.reason,
        topics=cls_result.topics,
        extracted_text_length=extracted_text_length,
        truncated=truncated,
        error_message=cls_result.error,
        destination_path=destination_path,
    )

    return {
        "triage": cls_result.triage,
        "confidence": cls_result.confidence,
        "reason": cls_result.reason,
        "topics": cls_result.topics,
        "skipped": False,
        "error": cls_result.error,
        "destination_path": destination_path,
    }


def _record_result(
    *,
    db_path: Path,
    cfg: Config,
    file_path: Path,
    checksum: str,
    file_size: int,
    triage: str,
    confidence: float,
    reason: str,
    topics: list[str],
    extracted_text_length: int,
    truncated: bool,
    error_message: str | None,
    destination_path: str | None,
) -> None:
    """Record a triage result in the database."""
    insert_result(
        db_path,
        {
            "source_path": str(file_path),
            "destination_path": destination_path,
            "checksum": checksum,
            "file_size": file_size,
            "file_extension": file_path.suffix,
            "triage": triage,
            "confidence": confidence,
            "reason": reason,
            "topics": topics,
            "llm_provider": cfg.llm.provider,
            "llm_model": cfg.llm.model,
            "extracted_text_length": extracted_text_length,
            "truncated": truncated,
            "error_message": error_message,
            "processed_at": datetime.now(),
        },
    )


def process_files(
    *,
    files: list[Path],
    cfg: Config,
    dry_run: bool,
    debug_dir: Path | None = None,
) -> dict[str, int]:
    """Process multiple files and return a summary.

    Returns:
        dict with counts: total, evergreen, temporal, unknown, error, skipped.
    """
    source_dir = Path(cfg.input.directory)
    summary: dict[str, int] = {
        "total": len(files),
        "evergreen": 0,
        "temporal": 0,
        "unknown": 0,
        "error": 0,
        "skipped": 0,
    }

    for i, file_path in enumerate(files, 1):
        logger.info("[%d/%d] %s", i, len(files), file_path.relative_to(source_dir))

        result = process_file(
            file_path=file_path,
            cfg=cfg,
            dry_run=dry_run,
            debug_dir=debug_dir,
        )

        if result["skipped"]:
            summary["skipped"] += 1
        elif result.get("error"):
            summary["error"] += 1
        else:
            cls = result["triage"]
            if cls in summary:
                summary[cls] += 1

    logger.info("--- 処理サマリー ---")
    logger.info("合計: %d", summary["total"])
    logger.info("  evergreen: %d", summary["evergreen"])
    logger.info("  temporal:  %d", summary["temporal"])
    logger.info("  unknown:   %d", summary["unknown"])
    logger.info("  エラー:    %d", summary["error"])
    logger.info("  スキップ:  %d", summary["skipped"])

    return summary

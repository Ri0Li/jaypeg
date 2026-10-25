from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from src import __version__
from src.autotune import tune
from src.config import load_config
from src.discover import discover
from src.extract import develop_companion, extract_companion, has_embedded_preview
from src.formats import has_sibling_non_raw, sibling_stamped_by_tool
from src.logging_setup import setup_logging
from src.queue import JobQueue
from src.report import write_pre_extract_report

log = logging.getLogger("jaypeg")


def _process_one(
    raw: Path,
    *,
    cfg,
    queue: JobQueue | None,
    write: bool,
) -> str:
    """Return status key: ok_preview | ok_develop | skip | skip_has_embed | failed"""
    path_str = str(raw)

    if has_sibling_non_raw(raw):
        tool_made = sibling_stamped_by_tool(raw, cfg.tool_name)
        if tool_made and not cfg.rewrite:
            log.debug("skip tool companion (set REWRITE=true to regenerate): %s", raw)
            if queue:
                queue.mark_skipped(path_str, "tool_companion_exists")
            return "skip"
        if not tool_made:
            log.debug("skip camera dual: %s", raw)
            if queue:
                queue.mark_skipped(path_str, "sibling_exists")
            return "skip"

    if queue and write and queue.is_done(path_str) and not cfg.rewrite:
        log.debug("skip already done: %s", raw)
        return "skip"

    if cfg.mode == "develop":
        result = develop_companion(
            raw,
            output_ext=cfg.output_ext,
            min_jpeg_bytes=cfg.min_jpeg_bytes,
            rewrite=cfg.rewrite,
            enable_gpu=cfg.enable_gpu,
            tool_name=cfg.tool_name,
            write=write,
        )
    else:
        result = extract_companion(
            raw,
            output_ext=cfg.output_ext,
            min_jpeg_bytes=cfg.min_jpeg_bytes,
            rewrite=cfg.rewrite,
            enable_gpu=cfg.enable_gpu,
            tool_name=cfg.tool_name,
            write=write,
            develop_fallback=cfg.develop_fallback,
            force_develop=cfg.force_develop,
        )

    if result.status == "skip":
        key = "skip_has_embed" if result.reason == "has_embed" else "skip"
        if write and queue:
            queue.mark_skipped(path_str, result.reason or "skip")
        elif result.reason:
            log.debug("dry-run %s → skip (%s)", raw, result.reason)
        return key

    if result.status == "ok" and result.method == "preview":
        key = "ok_preview"
    elif result.status == "ok" and result.method == "develop":
        key = "ok_develop"
    else:
        key = "failed"

    if write:
        if result.status == "ok":
            if queue:
                queue.mark_done(path_str)
        else:
            log.warning("failed %s: %s", raw, result.reason or "unknown")
            if queue:
                queue.mark_failed(path_str, result.reason or "unknown")
    elif result.reason:
        log.debug("dry-run %s → %s (%s)", raw, result.method, result.reason)

    return key


_EST_BYTES_PER_COMPANION = 4 * 1024 * 1024


def _log_capacity_estimate(raw_only_count: int, develop_fallback: bool) -> None:
    est = raw_only_count * _EST_BYTES_PER_COMPANION
    log.info(
        "capacity estimate: raw_only=%s × ~4MiB (native size) ≈ %.2f GiB",
        raw_only_count,
        est / (1024**3),
    )
    log.info(
        "develop_fallback=%s (false=skip darktable on preview miss — safer for large NAS runs)",
        develop_fallback,
    )


def _preview_counts(raw_only: list[Path]) -> tuple[int, int]:
    with_preview = 0
    for p in raw_only:
        if has_embedded_preview(p):
            with_preview += 1
    return with_preview, len(raw_only) - with_preview


def _emit_report(cfg, found, *, mode: str) -> None:
    with_preview, without_preview = _preview_counts(found.raw_only)
    write_pre_extract_report(
        result_dir=cfg.result_dir,
        result_keep=cfg.result_keep,
        mode=mode,
        cfg=cfg,
        raw_total=found.raw_total,
        camera_dual=found.camera_dual,
        tool_companion=found.tool_companion,
        raw_only=len(found.raw_only),
        with_preview=with_preview,
        without_preview=without_preview,
        list_paths=[str(p) for p in found.raw_only],
    )


def run_scan(cfg, found) -> int:
    log.info(
        "scan: raw_total=%s camera_dual=%s tool_companion=%s raw_only=%s path=%s",
        found.raw_total,
        found.camera_dual,
        found.tool_companion,
        len(found.raw_only),
        cfg.input_path,
    )
    _log_capacity_estimate(len(found.raw_only), cfg.develop_fallback)
    if cfg.log_level in {"debug", "verbose"}:
        for p in found.raw_only[:50]:
            log.debug("raw_only: %s", p)
        if len(found.raw_only) > 50:
            log.debug("... and %s more", len(found.raw_only) - 50)
    try:
        _emit_report(cfg, found, mode="scan")
    except OSError as exc:
        log.error("failed to write result report: %s", exc)
    return 0


def run_work(cfg, found, *, write: bool) -> int:
    tune_result = tune(cfg)
    concurrency = tune_result.concurrency
    worker_id = f"{cfg.hostname}-{uuid.uuid4().hex[:8]}"

    try:
        queue = JobQueue(cfg.redis_url)
    except Exception as exc:  # noqa: BLE001
        log.error("redis unavailable: %s", exc)
        return 2

    # REWRITE also processes existing tool companions; camera duals skipped in _process_one.
    if cfg.rewrite:
        targets = list(dict.fromkeys([*found.raw_only, *found.tool_companion_paths]))
    else:
        targets = found.raw_only
    target_strs = [str(p) for p in targets]

    if not target_strs:
        log.info("nothing to process")
        try:
            if not write:
                _emit_report(cfg, found, mode="dry-run")
        except OSError as exc:
            log.error("failed to write result report: %s", exc)
        return 0

    _log_capacity_estimate(len(found.raw_only), cfg.develop_fallback)

    counts = {
        "ok_preview": 0,
        "ok_develop": 0,
        "skip": 0,
        "skip_has_embed": 0,
        "failed": 0,
    }
    counts_lock = threading.Lock()
    done_n = 0
    started = time.time()

    def note_progress(path_str: str, key: str, total_hint: int) -> None:
        nonlocal done_n
        with counts_lock:
            counts[key] = counts.get(key, 0) + 1
            done_n += 1
            local_done = done_n
            snapshot = dict(counts)
        elapsed = max(time.time() - started, 0.001)
        rate = local_done / elapsed
        remain = max(total_hint - local_done, 0)
        eta = remain / rate if rate else 0
        log.info(
            "[%s/%s] %.0f%% ok_preview=%s ok_develop=%s skip=%s skip_embed=%s fail=%s eta=%.0fs path=%s",
            local_done,
            total_hint,
            100.0 * local_done / max(total_hint, 1),
            snapshot["ok_preview"],
            snapshot["ok_develop"],
            snapshot["skip"],
            snapshot["skip_has_embed"],
            snapshot["failed"],
            eta,
            path_str,
        )
        queue.bump_progress(
            done=local_done,
            total=total_hint,
            ok_preview=snapshot["ok_preview"],
            ok_develop=snapshot["ok_develop"],
            skip=snapshot["skip"] + snapshot["skip_has_embed"],
            failed=snapshot["failed"],
        )

    if not write:
        try:
            _emit_report(cfg, found, mode="dry-run")
        except OSError as exc:
            log.error("failed to write result report: %s", exc)
        log.info(
            "job: mode=%s write=False targets=%s concurrency=%s enable_gpu=%s",
            cfg.mode,
            len(target_strs),
            concurrency,
            cfg.enable_gpu,
        )
        total_hint = len(target_strs)

        def dry_one(path_str: str) -> None:
            key = _process_one(
                Path(path_str),
                cfg=cfg,
                queue=None,
                write=False,
            )
            note_progress(path_str, key, total_hint)

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            list(pool.map(dry_one, target_strs))
    else:
        queued = queue.enqueue_many(target_strs, rewrite=cfg.rewrite)
        total_hint = max(len(target_strs), queue.pending_len(), 1)
        log.info(
            "job: mode=%s write=True targets=%s newly_queued=%s concurrency=%s enable_gpu=%s worker=%s",
            cfg.mode,
            len(target_strs),
            queued,
            concurrency,
            cfg.enable_gpu,
            worker_id,
        )

        def claim_and_process() -> None:
            while True:
                path_str = queue.claim(worker_id)
                if path_str is None:
                    break
                try:
                    key = _process_one(
                        Path(path_str),
                        cfg=cfg,
                        queue=queue,
                        write=True,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.error("worker error %s: %s", path_str, exc)
                    key = "failed"
                    queue.mark_failed(path_str, str(exc))
                note_progress(path_str, key, total_hint)

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(claim_and_process) for _ in range(concurrency)]
            for fut in as_completed(futures):
                fut.result()

    log.info(
        "summary: ok_preview=%s ok_develop=%s skip=%s skip_has_embed=%s failed=%s redis=%s",
        counts["ok_preview"],
        counts["ok_develop"],
        counts["skip"],
        counts["skip_has_embed"],
        counts["failed"],
        queue.stats(),
    )
    return 0 if counts["failed"] == 0 else 1


def main() -> int:
    cfg = load_config()
    setup_logging(cfg.log_level)
    log.info(
        "jaypeg %s starting mode=%s intent=%s enable_gpu=%s develop_fallback=%s force_develop=%s input=%s",
        __version__,
        cfg.mode,
        cfg.intent,
        cfg.enable_gpu,
        cfg.develop_fallback,
        cfg.force_develop,
        cfg.input_path,
    )

    found = discover(cfg.input_path, tool_name=cfg.tool_name)

    if cfg.mode == "scan":
        return run_scan(cfg, found)
    if cfg.mode == "dry-run":
        return run_work(cfg, found, write=False)
    if cfg.mode in {"extract", "develop"}:
        return run_work(cfg, found, write=True)
    log.error("unknown mode %s", cfg.mode)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

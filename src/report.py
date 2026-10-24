from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("raw2jpg")

EST_BYTES_PER_COMPANION = 1 * 1024 * 1024  # ~embed-sized after quality defaults


def _giB(n_files: int) -> float:
    return (n_files * EST_BYTES_PER_COMPANION) / (1024**3)


def write_pre_extract_report(
    *,
    result_dir: str,
    result_keep: int,
    mode: str,
    cfg,
    raw_total: int,
    dual: int,
    raw_only: int,
    with_preview: int,
    without_preview: int,
    list_paths: list[str] | None = None,
    max_listed: int = 100,
) -> Path:
    """Write scan/dry-run markdown so user can judge extract cost before writing JPGs."""
    root = Path(result_dir)
    jobs = root / "jobs"
    jobs.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    job_path = jobs / f"{ts}-{mode}.md"

    # Without fallback: only files that have embed preview produce JPGs
    gb_no_fb = _giB(with_preview)
    fail_no_fb = without_preview
    # With fallback: develop output is sized like embed → same ~1MiB/file for all raw_only
    gb_with_fb = _giB(raw_only)

    lines = [
        f"# raw2jpg {mode} report",
        "",
        f"- time_utc: `{ts}`",
        f"- input_path: `{cfg.input_path}`",
        f"- mode: `{mode}`",
        f"- intent: `{cfg.intent}`",
        f"- develop_fallback_default: `{int(cfg.develop_fallback)}`",
        f"- jpeg_quality_default: `{cfg.jpeg_quality}`",
        f"- max_long_edge_default: `{cfg.max_long_edge}` (develop matches embed size when known)",
        "",
        "## Counts",
        "",
        f"| metric | value |",
        f"|--------|------:|",
        f"| raw_total | {raw_total} |",
        f"| dual (already have sibling JPG) | {dual} |",
        f"| raw_only (need companion) | {raw_only} |",
        f"| raw_only with embedded preview | {with_preview} |",
        f"| raw_only **without** preview (fail if no fallback) | {fail_no_fb} |",
        "",
        "## Disk estimate before extract (≈1 MiB / companion, embed-sized)",
        "",
        f"| scenario | files written | est. GiB | fails |",
        f"|----------|--------------:|---------:|------:|",
        f"| **DEVELOP_FALLBACK=false** (preview only) | {with_preview} | {gb_no_fb:.2f} | {fail_no_fb} |",
        f"| **DEVELOP_FALLBACK=true** (preview + develop) | {raw_only} | {gb_with_fb:.2f} | 0* |",
        "",
        "\\* develop failures still possible; estimate assumes develop succeeds at embed-like size.",
        "",
        "## How to read this",
        "",
        "- Dual files are skipped (no extra disk).",
        "- Without fallback, files lacking embed preview are **failed** and use **0 GiB**.",
        "- With fallback, those files are developed to roughly the same size as embed preview.",
        "- Run `MODE=extract` only after this report looks acceptable.",
        "",
    ]

    if list_paths:
        lines.append("## Sample raw_only paths")
        lines.append("")
        shown = list_paths[:max_listed]
        for p in shown:
            lines.append(f"- `{p}`")
        if len(list_paths) > max_listed:
            lines.append(f"- … and {len(list_paths) - max_listed} more")
        lines.append("")

    job_path.write_text("\n".join(lines), encoding="utf-8")

    latest = root / "LATEST.md"
    latest.write_text(job_path.read_text(encoding="utf-8"), encoding="utf-8")

    _prune_jobs(jobs, result_keep)
    _write_history(root, jobs)

    log.info("wrote report %s (LATEST.md updated)", job_path)
    return job_path


def _prune_jobs(jobs_dir: Path, keep: int) -> None:
    keep = max(1, keep)
    files = sorted(jobs_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        old.unlink(missing_ok=True)
        log.debug("pruned old report %s", old)


def _write_history(root: Path, jobs_dir: Path) -> None:
    files = sorted(jobs_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    lines = ["# raw2jpg report history", ""]
    for f in files:
        lines.append(f"- [{f.name}](jobs/{f.name})")
    lines.append("")
    (root / "HISTORY.md").write_text("\n".join(lines), encoding="utf-8")

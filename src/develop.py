from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

log = logging.getLogger("jaypeg")

# Caps parallel darktable-cli. Extract may use many preview workers; without a
# gate, develop_fallback stampedes GPU/RAM (e.g. intent=remote → 20× darktable).
_dt_gate: threading.Semaphore | None = None
_dt_gate_lock = threading.Lock()


def configure_develop_gate(*, enable_gpu: bool, pool_concurrency: int) -> None:
    """Set max concurrent darktable-cli processes for this process.

    GPU: always 1 (one OpenCL job saturates the card).
    CPU: at most pool size, hard-capped at 4 (each develop is RAM-heavy).
    """
    global _dt_gate
    if enable_gpu:
        n = 1
    else:
        n = max(1, min(int(pool_concurrency), 4))
    with _dt_gate_lock:
        _dt_gate = threading.Semaphore(n)
    log.info(
        "develop gate: darktable concurrency=%s (enable_gpu=%s pool=%s)",
        n,
        enable_gpu,
        pool_concurrency,
    )


def _develop_gate(enable_gpu: bool) -> threading.Semaphore:
    with _dt_gate_lock:
        if _dt_gate is not None:
            return _dt_gate
    # Not configured yet (tests / unexpected call path): safe defaults.
    return threading.Semaphore(1 if enable_gpu else 4)


def _imagemagick_bin() -> str | None:
    for name in ("magick", "convert"):
        if shutil.which(name):
            return name
    return None


def _exif_s3(path: Path, *tags: str) -> str:
    proc = subprocess.run(
        ["exiftool", "-s3", *tags, str(path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return (proc.stdout or "").strip()


def _orientation_num(raw_path: Path) -> int:
    """Return EXIF Orientation as 1–8 (default 1)."""
    proc = subprocess.run(
        ["exiftool", "-n", "-s3", "-Orientation", str(raw_path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    try:
        return int((proc.stdout or "1").strip().splitlines()[0])
    except (ValueError, IndexError):
        return 1


def _jpeg_wh(jpg_path: Path) -> tuple[int, int]:
    blob = _exif_s3(jpg_path, "-ImageWidth", "-ImageHeight")
    nums = [int(x) for x in blob.splitlines() if x.strip().isdigit()]
    if len(nums) >= 2:
        return nums[0], nums[1]
    return 0, 0


def _set_orientation_normal(jpg_path: Path) -> None:
    subprocess.run(
        ["exiftool", "-overwrite_original", "-Orientation=1", "-n", str(jpg_path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _auto_orient_from_raw(raw_path: Path, jpg_path: Path) -> None:
    """Ensure develop JPG is upright in pixels; set Orientation=1.

    Darktable sometimes exports landscape sensor pixels (need rotate) and
    sometimes already-upright pixels (must NOT rotate again). Decide from
    RAW orientation tag vs JPG width/height.
    """
    ori = _orientation_num(raw_path)
    w, h = _jpeg_wh(jpg_path)
    portrait_tag = ori in {5, 6, 7, 8}
    landscape_pixels = w > 0 and h > 0 and w >= h

    if portrait_tag and landscape_pixels:
        # Sensor layout still in file — bake rotation into pixels.
        copy = subprocess.run(
            [
                "exiftool",
                "-overwrite_original",
                "-TagsFromFile",
                str(raw_path),
                "-Orientation",
                str(jpg_path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if copy.returncode != 0:
            log.debug(
                "orientation copy skipped: %s",
                copy.stderr.strip() or copy.stdout.strip(),
            )

        binary = _imagemagick_bin()
        if binary is None:
            log.warning("ImageMagick not found; cannot auto-orient develop JPG")
            _set_orientation_normal(jpg_path)
            return

        # Same directory as jpg so rename is not cross-device
        tmp_path = jpg_path.with_suffix(jpg_path.suffix + ".orienting")
        try:
            if binary == "magick":
                cmd = ["magick", str(jpg_path), "-auto-orient", str(tmp_path)]
            else:
                cmd = ["convert", str(jpg_path), "-auto-orient", str(tmp_path)]
            if log.isEnabledFor(5):
                log.log(5, "exec: %s", " ".join(cmd))
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
            if proc.returncode != 0 or not tmp_path.exists() or tmp_path.stat().st_size < 100:
                raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "auto-orient failed")
            tmp_path.replace(jpg_path)
        except Exception as exc:  # noqa: BLE001
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            log.warning("auto-orient failed for %s: %s", jpg_path, exc)
    elif portrait_tag and not landscape_pixels:
        log.debug("develop JPG already upright pixels for %s", jpg_path.name)

    _set_orientation_normal(jpg_path)


def full_develop(
    raw_path: Path,
    out_jpg: Path,
    *,
    enable_gpu: bool,
    timeout_sec: int = 600,
) -> None:
    """Develop RAW to JPEG via darktable-cli. Raises on failure."""
    if shutil.which("darktable-cli") is None:
        raise RuntimeError("darktable-cli not found in image")

    out_jpg.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["DARKTABLE_USE_OPENCL"] = "1" if enable_gpu else "0"

    gate = _develop_gate(enable_gpu)
    with gate:
        # Isolated config + in-memory library so queued workers don't share locks.
        with tempfile.TemporaryDirectory(prefix="jaypeg-dt-") as tmp:
            tmp_path = Path(tmp)
            cfg = tmp_path / "config"
            cfg.mkdir()
            tmp_out = tmp_path / "out.jpg"
            cmd = [
                "darktable-cli",
                str(raw_path),
                str(tmp_out),
                "--core",
                "--library",
                ":memory:",
                "--configdir",
                str(cfg),
                "--conf",
                f"opencl={1 if enable_gpu else 0}",
            ]
            log.debug("develop cmd: %s", " ".join(cmd))
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                env=env,
                check=False,
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    f"darktable-cli failed ({proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}"
                )
            produced = tmp_out if tmp_out.exists() else None
            if produced is None:
                candidates = sorted(tmp_path.glob("out*.jpg")) + sorted(tmp_path.glob("out*.JPG"))
                if candidates:
                    produced = candidates[0]
            if produced is None or not produced.exists():
                raise RuntimeError("darktable-cli produced no JPEG")
            shutil.copy2(produced, out_jpg)

    _auto_orient_from_raw(raw_path, out_jpg)

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger("raw2jpg")


def _imagemagick_bin() -> str | None:
    for name in ("magick", "convert"):
        if shutil.which(name):
            return name
    return None


def resize_and_compress(
    jpg_path: Path,
    *,
    max_long_edge: int,
    jpeg_quality: int,
) -> None:
    """Optionally resize (long edge) and/or recompress JPEG in place.

    max_long_edge <= 0 → no resize
    jpeg_quality <= 0 → no recompress (and if no resize, no-op)
    """
    do_resize = max_long_edge > 0
    do_quality = jpeg_quality > 0
    if not do_resize and not do_quality:
        return

    binary = _imagemagick_bin()
    if binary is None:
        log.warning("ImageMagick not found; skipping resize/compress")
        return

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        cmd: list[str]
        if binary == "magick":
            cmd = ["magick", str(jpg_path)]
        else:
            cmd = ["convert", str(jpg_path)]
        if do_resize:
            edge = max(1, max_long_edge)
            cmd.extend(["-resize", f"{edge}x{edge}>"])
        if do_quality:
            cmd.extend(["-quality", str(min(100, max(1, jpeg_quality)))])
        cmd.append(str(tmp_path))

        if log.isEnabledFor(5):
            log.log(5, "exec: %s", " ".join(cmd))
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
        if proc.returncode != 0 or not tmp_path.exists() or tmp_path.stat().st_size < 100:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "imagemagick failed")
        tmp_path.replace(jpg_path)
        log.debug(
            "postprocess: %s resize=%s quality=%s → %s bytes",
            jpg_path.name,
            max_long_edge if do_resize else "off",
            jpeg_quality if do_quality else "off",
            jpg_path.stat().st_size,
        )
    except Exception as exc:  # noqa: BLE001
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        log.warning("postprocess skipped for %s: %s", jpg_path, exc)

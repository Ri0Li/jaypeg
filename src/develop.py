from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger("raw2jpg")


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
    if enable_gpu:
        env.setdefault("DARKTABLE_PREFERENCES", "")
        # Prefer OpenCL when available; darktable reads configs — set hint via env
        env["DARKTABLE_USE_OPENCL"] = "1"
    else:
        env["DARKTABLE_USE_OPENCL"] = "0"

    with tempfile.TemporaryDirectory(prefix="raw2jpg-dt-") as tmp:
        tmp_out = Path(tmp) / "out.jpg"
        # darktable-cli writes beside input or to given path; use explicit output
        cmd = [
            "darktable-cli",
            str(raw_path),
            str(tmp_out),
            "--core",
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
        # darktable may append _01 or change extension
        produced = tmp_out if tmp_out.exists() else None
        if produced is None:
            candidates = sorted(Path(tmp).glob("out*.jpg")) + sorted(Path(tmp).glob("out*.JPG"))
            if candidates:
                produced = candidates[0]
        if produced is None or not produced.exists():
            raise RuntimeError("darktable-cli produced no JPEG")
        shutil.copy2(produced, out_jpg)

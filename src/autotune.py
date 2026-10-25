from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from src.config import Config

log = logging.getLogger("raw2jpg")


@dataclass(frozen=True)
class TuneResult:
    cpus: int
    ram_mb: int
    concurrency: int
    enable_gpu: bool
    source: str


def _cpu_count() -> int:
    return max(1, os.cpu_count() or 1)


def _ram_mb() -> int:
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
                if line.startswith("MemTotal:"):
                    total = int(line.split()[1]) // 1024
        return total  # type: ignore[name-defined]
    except OSError:
        return 0


def _detect_gpu() -> bool:
    return os.path.exists("/dev/nvidia0") or os.path.exists("/dev/dri/renderD128")


def tune(cfg: Config) -> TuneResult:
    cpus = _cpu_count()
    ram = _ram_mb()
    gpu_present = _detect_gpu()

    if cfg.concurrency is not None:
        concurrency = max(1, cfg.concurrency)
        source = "override"
    elif cfg.force_develop:
        # darktable-cli does not like parallel workers sharing host resources
        concurrency = 1
        source = "force_develop"
    elif cfg.intent == "nas":
        concurrency = min(2, cpus)
        source = "intent=nas"
    elif cfg.intent == "remote":
        concurrency = min(16, max(2, cpus))
        source = "intent=remote"
    else:
        concurrency = min(4, max(2, cpus // 2 or 1))
        source = "intent=balanced"

    if ram and ram < 1024:
        concurrency = min(concurrency, 1)

    log.info(
        "autotune: %s cpus, %sMiB ram, gpu_present=%s, intent=%s → concurrency=%s (%s), enable_gpu=%s",
        cpus,
        ram or "?",
        gpu_present,
        cfg.intent,
        concurrency,
        source,
        cfg.enable_gpu,
    )
    return TuneResult(
        cpus=cpus,
        ram_mb=ram,
        concurrency=concurrency,
        enable_gpu=cfg.enable_gpu,
        source=source,
    )

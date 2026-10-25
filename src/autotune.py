from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from src.config import Config

log = logging.getLogger("jaypeg")

# Darktable is RAM-hungry; ~2 GiB headroom per parallel CPU worker.
_MB_PER_CPU_DEVELOP_WORKER = 2048


@dataclass(frozen=True)
class TuneResult:
    cpus: int
    ram_mb: int
    concurrency: int
    enable_gpu: bool
    source: str
    omp_num_threads: int | None


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


def _intent_concurrency(cfg: Config, cpus: int) -> tuple[int, str]:
    if cfg.intent == "nas":
        return min(2, cpus), "intent=nas"
    if cfg.intent == "remote":
        return max(2, cpus), "intent=remote"
    return min(4, max(2, cpus // 2 or 1)), "intent=balanced"


def _cpu_develop_concurrency(cfg: Config, cpus: int, ram: int) -> tuple[int, str]:
    """Aggressive parallel darktable on CPU: size by cores and RAM, then INTENT cap."""
    if ram > 0:
        by_ram = max(1, ram // _MB_PER_CPU_DEVELOP_WORKER)
        estimated = min(cpus, by_ram)
    else:
        estimated = cpus

    if cfg.intent == "nas":
        concurrency = min(2, estimated)
        source = "develop_cpu+nas"
    elif cfg.intent == "balanced":
        concurrency = min(4, estimated)
        source = "develop_cpu+balanced"
    else:
        # remote without GPU: use full estimate
        concurrency = max(1, estimated)
        source = "develop_cpu+remote"
    return concurrency, source


def _heavy_develop(cfg: Config) -> bool:
    """Jobs that are mostly/always darktable (need GPU/CPU develop autotune)."""
    return cfg.mode == "develop" or cfg.force_develop


def tune(cfg: Config) -> TuneResult:
    cpus = _cpu_count()
    ram = _ram_mb()
    gpu_present = _detect_gpu()
    omp_num_threads: int | None = None

    if cfg.concurrency is not None:
        concurrency = max(1, cfg.concurrency)
        source = "override"
    elif _heavy_develop(cfg) and cfg.enable_gpu:
        # One darktable-cli + OpenCL saturates the GPU; parallel fights for VRAM.
        concurrency = 1
        source = "gpu_saturate"
    elif _heavy_develop(cfg) and not cfg.enable_gpu:
        concurrency, source = _cpu_develop_concurrency(cfg, cpus, ram)
    else:
        # extract / dry-run (preview-first): unchanged INTENT formula
        concurrency, source = _intent_concurrency(cfg, cpus)

    if ram and ram < 1024:
        concurrency = min(concurrency, 1)

    # Cap OpenMP per darktable process so N workers don't oversubscribe all cores.
    if _heavy_develop(cfg) and not cfg.enable_gpu and concurrency > 1:
        omp_num_threads = max(1, cpus // concurrency)
        os.environ["OMP_NUM_THREADS"] = str(omp_num_threads)

    log.info(
        "autotune: %s cpus, %sMiB ram, gpu_present=%s, intent=%s → concurrency=%s (%s), "
        "enable_gpu=%s, omp_num_threads=%s",
        cpus,
        ram or "?",
        gpu_present,
        cfg.intent,
        concurrency,
        source,
        cfg.enable_gpu,
        omp_num_threads if omp_num_threads is not None else os.environ.get("OMP_NUM_THREADS", "-"),
    )
    return TuneResult(
        cpus=cpus,
        ram_mb=ram,
        concurrency=concurrency,
        enable_gpu=cfg.enable_gpu,
        source=source,
        omp_num_threads=omp_num_threads,
    )

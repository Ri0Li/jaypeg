from __future__ import annotations

import os
import socket
from dataclasses import dataclass


def _env(name: str, default: str | None = None) -> str | None:
    val = os.environ.get(name)
    if val is None or val == "":
        return default
    return val


def _env_bool(name: str, default: bool) -> bool:
    val = _env(name)
    if val is None:
        return default
    s = val.strip().lower()
    if s in {"true", "1", "yes", "on"}:
        return True
    if s in {"false", "0", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false, got {val!r}")


def _env_int(name: str, default: int | None = None) -> int | None:
    val = _env(name)
    if val is None:
        return default
    return int(val)


@dataclass(frozen=True)
class Config:
    input_path: str
    mode: str
    log_level: str
    intent: str
    rewrite: bool
    output_ext: str
    min_jpeg_bytes: int
    concurrency: int | None
    enable_gpu: bool
    path_prefix: str | None
    shard: int | None
    shard_count: int | None
    redis_url: str
    tool_name: str
    hostname: str
    max_long_edge: int
    jpeg_quality: int
    develop_fallback: bool

    @property
    def write_files(self) -> bool:
        return self.mode == "extract"


def load_config() -> Config:
    intent = (_env("INTENT", "balanced") or "balanced").strip().lower()
    if intent not in {"nas", "remote", "balanced"}:
        raise ValueError(f"Invalid INTENT={intent!r}; use nas|remote|balanced")

    mode = (_env("MODE", "scan") or "scan").strip().lower()
    if mode not in {"scan", "dry-run", "extract"}:
        raise ValueError(f"Invalid MODE={mode!r}; use scan|dry-run|extract")

    gpu_override = _env("ENABLE_GPU")
    if gpu_override is None:
        enable_gpu = intent == "remote"
    else:
        enable_gpu = _env_bool("ENABLE_GPU", False)

    input_path = _env("INPUT_PATH", "/mnt/photos") or "/mnt/photos"
    path_prefix = _env("PATH_PREFIX")

    shard = _env_int("SHARD")
    shard_count = _env_int("SHARD_COUNT")
    if (shard is None) ^ (shard_count is None):
        raise ValueError("Set both SHARD and SHARD_COUNT, or neither")
    if shard_count is not None and (shard_count < 1 or shard is None or shard < 0 or shard >= shard_count):
        raise ValueError("SHARD must be 0..SHARD_COUNT-1")

    return Config(
        input_path=input_path,
        mode=mode,
        log_level=(_env("LOG_LEVEL", "log") or "log").strip().lower(),
        intent=intent,
        rewrite=_env_bool("REWRITE", False),
        output_ext=_env("OUTPUT_EXT", ".JPG") or ".JPG",
        min_jpeg_bytes=_env_int("MIN_JPEG_BYTES", 51200) or 51200,
        concurrency=_env_int("CONCURRENCY"),
        enable_gpu=enable_gpu,
        path_prefix=path_prefix,
        shard=shard,
        shard_count=shard_count,
        redis_url=_env("REDIS_URL", "redis://redis:6379/0") or "redis://redis:6379/0",
        tool_name=_env("TOOL_NAME", "raw2jpg") or "raw2jpg",
        hostname=socket.gethostname(),
        max_long_edge=_env_int("MAX_LONG_EDGE", 2560) or 2560,
        jpeg_quality=_env_int("JPEG_QUALITY", 85) or 85,
        develop_fallback=_env_bool("DEVELOP_FALLBACK", True),
    )

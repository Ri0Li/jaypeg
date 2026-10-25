from __future__ import annotations

import os
import socket
from dataclasses import dataclass

# Only keys listed in .env.example may be read from the environment.


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


@dataclass(frozen=True)
class Config:
    input_path: str
    mode: str
    log_level: str
    intent: str
    rewrite: bool
    enable_gpu: bool
    develop_fallback: bool
    # Hardcoded (not user env)
    output_ext: str
    min_jpeg_bytes: int
    concurrency: int | None
    redis_url: str
    tool_name: str
    hostname: str
    result_dir: str
    result_keep: int

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

    return Config(
        input_path=_env("INPUT_PATH", "/mnt/photos") or "/mnt/photos",
        mode=mode,
        log_level=(_env("LOG_LEVEL", "log") or "log").strip().lower(),
        intent=intent,
        rewrite=_env_bool("REWRITE", False),
        enable_gpu=enable_gpu,
        develop_fallback=_env_bool("DEVELOP_FALLBACK", True),
        output_ext=".JPG",
        min_jpeg_bytes=51200,
        concurrency=None,
        # Compose sets this for the stack; not a user .env.example knob
        redis_url=_env("REDIS_URL", "redis://redis:6379/0") or "redis://redis:6379/0",
        tool_name="raw2jpg",
        hostname=socket.gethostname(),
        result_dir="/result",
        result_keep=20,
    )

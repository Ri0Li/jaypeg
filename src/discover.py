from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from src.formats import has_sibling_non_raw, is_raw

log = logging.getLogger("raw2jpg")


@dataclass
class DiscoverResult:
    raw_total: int
    dual: int
    raw_only: list[Path]
    all_raw: list[Path]


def _shard_ok(path: Path, shard: int | None, shard_count: int | None) -> bool:
    if shard is None or shard_count is None:
        return True
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % shard_count == shard


def discover(
    root: str | Path,
    *,
    path_prefix: str | None = None,
    shard: int | None = None,
    shard_count: int | None = None,
) -> DiscoverResult:
    root_path = Path(root)
    if not root_path.exists():
        raise FileNotFoundError(f"INPUT_PATH does not exist: {root_path}")
    if not root_path.is_dir():
        raise NotADirectoryError(f"INPUT_PATH is not a directory: {root_path}")

    all_raw: list[Path] = []
    dual = 0
    raw_only: list[Path] = []

    for dirpath, _dirnames, filenames in os_walk(root_path):
        base = Path(dirpath)
        for name in filenames:
            if not is_raw(name):
                continue
            path = base / name
            if path_prefix and path_prefix not in str(path):
                continue
            if not _shard_ok(path, shard, shard_count):
                continue
            all_raw.append(path)
            if has_sibling_non_raw(path):
                dual += 1
            else:
                raw_only.append(path)

    all_raw.sort()
    raw_only.sort()
    log.debug("discover: root=%s raw=%s dual=%s raw_only=%s", root_path, len(all_raw), dual, len(raw_only))
    return DiscoverResult(
        raw_total=len(all_raw),
        dual=dual,
        raw_only=raw_only,
        all_raw=all_raw,
    )


def os_walk(root: Path):
    import os

    return os.walk(root)

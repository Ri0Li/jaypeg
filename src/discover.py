from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from src.formats import has_sibling_non_raw, is_raw, sibling_stamped_by_tool

log = logging.getLogger("raw2jpg")


@dataclass
class DiscoverResult:
    raw_total: int
    camera_dual: int
    tool_companion: int
    raw_only: list[Path]
    tool_companion_paths: list[Path]
    all_raw: list[Path]

    @property
    def dual(self) -> int:
        """Back-compat alias: camera duals only (not tool companions)."""
        return self.camera_dual


def discover(
    root: str | Path,
    *,
    tool_name: str = "raw2jpg",
) -> DiscoverResult:
    root_path = Path(root)
    if not root_path.exists():
        raise FileNotFoundError(f"INPUT_PATH does not exist: {root_path}")
    if not root_path.is_dir():
        raise NotADirectoryError(f"INPUT_PATH is not a directory: {root_path}")

    all_raw: list[Path] = []
    camera_dual = 0
    tool_companion_paths: list[Path] = []
    raw_only: list[Path] = []

    for dirpath, _dirnames, filenames in os_walk(root_path):
        base = Path(dirpath)
        for name in filenames:
            if not is_raw(name):
                continue
            path = base / name
            all_raw.append(path)
            if not has_sibling_non_raw(path):
                raw_only.append(path)
            elif sibling_stamped_by_tool(path, tool_name):
                tool_companion_paths.append(path)
            else:
                camera_dual += 1

    all_raw.sort()
    raw_only.sort()
    tool_companion_paths.sort()
    log.debug(
        "discover: root=%s raw=%s camera_dual=%s tool_companion=%s raw_only=%s",
        root_path,
        len(all_raw),
        camera_dual,
        len(tool_companion_paths),
        len(raw_only),
    )
    return DiscoverResult(
        raw_total=len(all_raw),
        camera_dual=camera_dual,
        tool_companion=len(tool_companion_paths),
        raw_only=raw_only,
        tool_companion_paths=tool_companion_paths,
        all_raw=all_raw,
    )


def os_walk(root: Path):
    import os

    return os.walk(root)

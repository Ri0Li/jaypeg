from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from src.formats import has_sibling_non_raw, is_raw, sibling_stamped_by_tool

log = logging.getLogger("jaypeg")


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


def iter_split_roots(root: str | Path, depth: int) -> list[Path]:
    """Directories at exactly relative depth N under root, newest mtime first."""
    if depth < 1:
        raise ValueError(f"split depth must be >= 1, got {depth}")
    root_path = Path(root)
    level = [root_path]
    for _ in range(depth):
        next_level: list[Path] = []
        for parent in level:
            try:
                for child in parent.iterdir():
                    try:
                        if child.is_dir():
                            next_level.append(child)
                    except OSError:
                        continue
            except OSError as exc:
                log.warning("cannot list %s: %s", parent, exc)
        level = next_level
        if not level:
            break

    def _mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0

    level.sort(key=_mtime, reverse=True)
    return level


def root_has_direct_raws(root: str | Path) -> bool:
    """True if root itself contains RAW files (not only in subdirs)."""
    root_path = Path(root)
    try:
        for child in root_path.iterdir():
            try:
                if child.is_file() and is_raw(child.name):
                    return True
            except OSError:
                continue
    except OSError:
        return False
    return False


def discover(
    root: str | Path,
    *,
    tool_name: str = "jaypeg",
    recursive: bool = True,
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

    if recursive:
        walk_iter = os_walk(root_path)
    else:
        try:
            names = [p.name for p in root_path.iterdir() if p.is_file()]
        except OSError as exc:
            raise FileNotFoundError(f"cannot list {root_path}: {exc}") from exc
        walk_iter = [(str(root_path), [], names)]

    for dirpath, _dirnames, filenames in walk_iter:
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
        "discover: root=%s recursive=%s raw=%s camera_dual=%s tool_companion=%s raw_only=%s",
        root_path,
        recursive,
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

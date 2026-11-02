from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path

from src.formats import iter_sibling_non_raw

log = logging.getLogger("jaypeg")

KIND_RAW_ONLY = "raw_only"
KIND_CAMERA_DUAL = "camera_dual"
KIND_TOOL_COMPANION = "tool_companion"


def sibling_fingerprint(raw_path: Path) -> str:
    """Cheap sibling signature (name+mtime_ns+size). Empty = no non-RAW sibling."""
    parts: list[str] = []
    try:
        for sibling in iter_sibling_non_raw(raw_path):
            try:
                st = sibling.stat()
            except OSError:
                continue
            parts.append(f"{sibling.name}:{st.st_mtime_ns}:{st.st_size}")
    except OSError:
        return ""
    return "|".join(sorted(parts))


class DiscoverCache:
    """Immich-style incremental classify cache (skip exiftool when unchanged)."""

    def __init__(self, db_path: Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entries (
                path TEXT PRIMARY KEY,
                raw_mtime_ns INTEGER NOT NULL,
                raw_size INTEGER NOT NULL,
                sibling_fp TEXT NOT NULL,
                kind TEXT NOT NULL
            )
            """
        )
        self._conn.commit()
        self.hits = 0
        self.misses = 0
        self._writes = 0

    def get(
        self,
        path: str,
        raw_mtime_ns: int,
        raw_size: int,
        sibling_fp: str,
    ) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT kind, raw_mtime_ns, raw_size, sibling_fp FROM entries WHERE path = ?",
                (path,),
            ).fetchone()
        if row is None:
            self.misses += 1
            return None
        kind, mtime_ns, size, fp = row
        if mtime_ns == raw_mtime_ns and size == raw_size and fp == sibling_fp:
            self.hits += 1
            return str(kind)
        self.misses += 1
        return None

    def put(
        self,
        path: str,
        raw_mtime_ns: int,
        raw_size: int,
        sibling_fp: str,
        kind: str,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO entries(path, raw_mtime_ns, raw_size, sibling_fp, kind)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    raw_mtime_ns = excluded.raw_mtime_ns,
                    raw_size = excluded.raw_size,
                    sibling_fp = excluded.sibling_fp,
                    kind = excluded.kind
                """,
                (path, raw_mtime_ns, raw_size, sibling_fp, kind),
            )
            self._writes += 1
            if self._writes % 200 == 0:
                self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.commit()
            self._conn.close()
        log.info(
            "discover cache: path=%s hits=%s misses=%s hit_rate=%.1f%%",
            self.path,
            self.hits,
            self.misses,
            100.0 * self.hits / max(self.hits + self.misses, 1),
        )

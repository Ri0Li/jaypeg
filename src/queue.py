from __future__ import annotations

import json
import logging
import time
from typing import Any

import redis

log = logging.getLogger("raw2jpg")

KEY_PENDING = "raw2jpg:pending"
KEY_DONE = "raw2jpg:done"
KEY_FAILED = "raw2jpg:failed"
KEY_SKIPPED = "raw2jpg:skipped"
KEY_PROGRESS = "raw2jpg:progress"
KEY_LOCK_PREFIX = "raw2jpg:lock:"


class JobQueue:
    def __init__(self, redis_url: str):
        self.r = redis.Redis.from_url(redis_url, decode_responses=True)
        self.r.ping()
        log.debug("redis connected: %s", redis_url)

    def clear_job(self) -> None:
        pipe = self.r.pipeline()
        pipe.delete(
            KEY_PENDING,
            KEY_DONE,
            KEY_FAILED,
            KEY_SKIPPED,
            KEY_SKIPPED + ":reasons",
            KEY_PROGRESS,
        )
        pipe.execute()

    def enqueue_many(self, paths: list[str], *, rewrite: bool = False) -> int:
        if not paths:
            return 0
        if rewrite:
            pipe = self.r.pipeline()
            for p in paths:
                pipe.srem(KEY_DONE, p)
            pipe.execute()
            fresh = paths
        else:
            fresh = [p for p in paths if not self.r.sismember(KEY_DONE, p)]
        if not fresh:
            return 0
        self.r.rpush(KEY_PENDING, *fresh)
        return len(fresh)

    def pending_len(self) -> int:
        return int(self.r.llen(KEY_PENDING))

    def claim(self, worker_id: str, ttl_sec: int = 600) -> str | None:
        while True:
            path = self.r.lpop(KEY_PENDING)
            if path is None:
                return None
            if self.r.sismember(KEY_DONE, path):
                continue
            lock_key = KEY_LOCK_PREFIX + path
            if self.r.set(lock_key, worker_id, nx=True, ex=ttl_sec):
                return path
            continue

    def mark_done(self, path: str) -> None:
        pipe = self.r.pipeline()
        pipe.sadd(KEY_DONE, path)
        pipe.delete(KEY_LOCK_PREFIX + path)
        pipe.execute()

    def mark_skipped(self, path: str, reason: str) -> None:
        # Skips go only to KEY_SKIPPED — never inflate failed stats.
        pipe = self.r.pipeline()
        pipe.sadd(KEY_SKIPPED, path)
        pipe.hset(KEY_SKIPPED + ":reasons", path, json.dumps({"reason": reason}))
        pipe.delete(KEY_LOCK_PREFIX + path)
        pipe.execute()

    def mark_failed(self, path: str, reason: str) -> None:
        pipe = self.r.pipeline()
        pipe.hset(KEY_FAILED, path, json.dumps({"status": "failed", "reason": reason}))
        pipe.delete(KEY_LOCK_PREFIX + path)
        pipe.execute()

    def bump_progress(self, **fields: Any) -> dict[str, str]:
        if fields:
            mapping = {k: str(v) for k, v in fields.items()}
            mapping["updated_at"] = str(time.time())
            self.r.hset(KEY_PROGRESS, mapping=mapping)
        return self.r.hgetall(KEY_PROGRESS)

    def stats(self) -> dict[str, int]:
        return {
            "pending": int(self.r.llen(KEY_PENDING)),
            "done": int(self.r.scard(KEY_DONE)),
            "skipped": int(self.r.scard(KEY_SKIPPED)),
            "failed": int(self.r.hlen(KEY_FAILED)),
        }

    def is_done(self, path: str) -> bool:
        return bool(self.r.sismember(KEY_DONE, path))

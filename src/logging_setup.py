from __future__ import annotations

import logging
import sys

# Immich / Nest-style levels mapped onto Python logging
LEVEL_MAP = {
    "verbose": 5,  # below DEBUG
    "debug": logging.DEBUG,
    "log": logging.INFO,
    "warn": logging.WARNING,
    "error": logging.ERROR,
}

logging.addLevelName(5, "VERBOSE")


def verbose(self: logging.Logger, message: str, *args, **kwargs) -> None:
    if self.isEnabledFor(5):
        self._log(5, message, args, **kwargs)


logging.Logger.verbose = verbose  # type: ignore[attr-defined]


def setup_logging(level_name: str) -> logging.Logger:
    level = LEVEL_MAP.get(level_name.lower(), logging.INFO)
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))
    root.addHandler(handler)
    root.setLevel(level)
    return logging.getLogger("jaypeg")

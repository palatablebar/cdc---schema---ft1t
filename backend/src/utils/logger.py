"""统一 logger：stdout 一行一条，便于 docker logs 检索。"""
from __future__ import annotations

import logging
import sys

_FORMAT = "%(asctime)s %(levelname)-5s [%(name)s] %(message)s"


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(_FORMAT))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger

"""One configured logger for the whole application."""

from __future__ import annotations

import logging
import os
import sys

_CONFIGURED = False
LOGGER_NAME = "lead_investor_map"


def configure(verbose: bool = False) -> None:
    global _CONFIGURED
    level = logging.DEBUG if verbose else logging.INFO
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    if not _CONFIGURED:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(levelname)s  %(message)s"))
        logger.addHandler(handler)
        _CONFIGURED = True
    for h in logger.handlers:
        h.setLevel(level)


def get_logger() -> logging.Logger:
    if not _CONFIGURED:
        configure(verbose=bool(os.getenv("LIM_VERBOSE")))
    return logging.getLogger(LOGGER_NAME)

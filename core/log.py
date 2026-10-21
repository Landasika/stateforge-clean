
from __future__ import annotations

import logging

ROOT = "stateforge"


def get_logger(name: str) -> logging.Logger:
    if name != ROOT and not name.startswith(ROOT + "."):
        name = f"{ROOT}.{name}"
    root = logging.getLogger(ROOT)
    if not any(isinstance(h, logging.NullHandler) for h in root.handlers):
        root.addHandler(logging.NullHandler())
    return logging.getLogger(name)


def setup_logging(verbose: bool = False) -> None:
    root = logging.getLogger(ROOT)
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.handlers[:] = [h for h in root.handlers
                        if not getattr(h, "_stateforge_setup", False)]
    handler = logging.StreamHandler()                      
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    handler._stateforge_setup = True
    root.addHandler(handler)

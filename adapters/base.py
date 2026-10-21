
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class TargetAdapter(Protocol):
    def prepare(self, atheris) -> None:
        pass

    def execute(self, data: bytes) -> object:
        pass

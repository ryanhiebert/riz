from __future__ import annotations

from dataclasses import dataclass
from typing import override


@dataclass(frozen=True)
class Product[T]:
    items: tuple[T, ...]

    @override
    def __str__(self) -> str:
        return f"({', '.join(map(str, self.items))})"

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar, override


T_co = TypeVar("T_co", covariant=True)


@dataclass(frozen=True)
class Product(Generic[T_co]):
    items: tuple[T_co, ...]

    @override
    def __str__(self) -> str:
        return f"({', '.join(map(str, self.items))})"

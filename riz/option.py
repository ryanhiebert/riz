"""Built-in optional values."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar, override


T_co = TypeVar("T_co", covariant=True)


@dataclass(frozen=True)
class Some(Generic[T_co]):
    value: T_co

    @override
    def __str__(self) -> str:
        return f"Some({self.value})"


@dataclass(frozen=True)
class Nothing:
    @override
    def __str__(self) -> str:
        return "None"

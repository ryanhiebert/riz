"""Runtime values for Riz's built-in variants."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Never, TypeVar, override


T_co = TypeVar("T_co", covariant=True)


@dataclass(frozen=True)
class VariantValue(Generic[T_co]):
    type_name: str
    constructor: str
    value: T_co | None

    @override
    def __str__(self) -> str:
        if self.value is None:
            return self.constructor
        return f"{self.constructor}({self.value})"


class Some(VariantValue[T_co]):
    def __init__(self, value: T_co):
        super().__init__("Option", "Some", value)


class Nothing(VariantValue[Never]):
    def __init__(self):
        super().__init__("Option", "None", None)


class Success(VariantValue[T_co]):
    def __init__(self, value: T_co):
        super().__init__("Result", "Ok", value)


class Failure(VariantValue[T_co]):
    def __init__(self, value: T_co):
        super().__init__("Result", "Err", value)

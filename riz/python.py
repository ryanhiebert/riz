"""Values and errors for Riz's Python interoperability boundary."""

from dataclasses import dataclass
from typing import override


@dataclass(frozen=True)
class Python:
    """The temporary prelude capability for accessing the hosting Python."""

    @override
    def __str__(self) -> str:
        return "<python>"


@dataclass(frozen=True, eq=False)
class PythonValue:
    """An opaque Python object; Riz can only use its explicit bridge API."""

    value: object | None

    @override
    def __str__(self) -> str:
        return "<python value>"


@dataclass(frozen=True)
class RizPythonError:
    exception: Exception

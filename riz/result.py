"""Evaluation results: a value (`Ok`) or an error (`Err`).

Errors propagate as values, never as host exceptions. To the runtime, a program
that divides by zero or fails to parse is a *normal, expected* outcome — so it
returns an `Err`. (Host `raise`/`panic` stays reserved for what's exceptional to
the runtime itself: bugs, impossible states.) This is also how the eventual Zig
VM threads error unions.
"""

from dataclasses import dataclass
from typing import Generic, TypeVar


T_co = TypeVar("T_co", covariant=True)


@dataclass(frozen=True)
class Ok(Generic[T_co]):
    value: T_co


@dataclass(frozen=True)
class Err:
    error: object  # some Riz error value; no shared base type yet


type Result[T] = Ok[T] | Err

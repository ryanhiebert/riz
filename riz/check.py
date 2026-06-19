"""Type checker: reject ill-typed programs before evaluation.

Runs between parse and eval. For now the only rule is that arithmetic operands
must be numbers, so `True + 1` is a *type* error caught here — not at eval (Riz
never enforces a type rule at runtime). The lattice is intentionally coarse
(Number vs Boolean); it gains Int-vs-Rational precision when something needs it.
"""

from dataclasses import dataclass
from enum import Enum, auto

from .parse import (
    Add,
    BoolLiteral,
    Divide,
    Expr,
    IntLiteral,
    Multiply,
    Negate,
    Subtract,
)
from .result import Err, Ok, Result


@dataclass(frozen=True)
class RizTypeError: ...


class Type(Enum):
    NUMBER = auto()
    BOOLEAN = auto()


def check(node: Expr) -> Result[Type]:
    match node:
        case IntLiteral():
            return Ok(Type.NUMBER)
        case BoolLiteral():
            return Ok(Type.BOOLEAN)
        case Negate(operand):
            return _numeric(check(operand))
        case (
            Add(left, right)
            | Subtract(left, right)
            | Multiply(left, right)
            | Divide(left, right)
        ):
            return _numeric(check(left), check(right))


def _numeric(*operands: Result[Type]) -> Result[Type]:
    """All operands must type-check to NUMBER; the result is NUMBER."""
    for operand in operands:
        if isinstance(operand, Err):
            return operand
        if operand.value is not Type.NUMBER:
            return Err(RizTypeError())
    return Ok(Type.NUMBER)

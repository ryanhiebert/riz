"""Type checker: reject ill-typed programs before evaluation.

Runs between parse and eval. For now the only rule is that arithmetic operands
must be numbers, so `True + 1` is a *type* error caught here — not at eval (Riz
never enforces a type rule at runtime). The lattice is intentionally coarse
(Number vs Boolean); it gains Integer-vs-Ratio precision when something needs it.
"""

from dataclasses import dataclass
from enum import Enum, auto

from .parse import (
    Add,
    BoolLiteral,
    Divide,
    Equal,
    Expr,
    GreaterOrEqual,
    GreaterThan,
    IntLiteral,
    LessOrEqual,
    LessThan,
    Multiply,
    Negate,
    NotEqual,
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
        case (
            LessThan(left, right)
            | GreaterThan(left, right)
            | LessOrEqual(left, right)
            | GreaterOrEqual(left, right)
        ):
            return _comparison(check(left), check(right))
        case Equal(left, right) | NotEqual(left, right):
            return _equality(check(left), check(right))


def _numeric(*operands: Result[Type]) -> Result[Type]:
    """All operands must type-check to NUMBER; the result is NUMBER."""
    for operand in operands:
        if isinstance(operand, Err):
            return operand
        if operand.value is not Type.NUMBER:
            return Err(RizTypeError())
    return Ok(Type.NUMBER)


def _comparison(*operands: Result[Type]) -> Result[Type]:
    """Ordering operands must be NUMBER (for now); the result is BOOLEAN."""
    for operand in operands:
        if isinstance(operand, Err):
            return operand
        if operand.value is not Type.NUMBER:
            return Err(RizTypeError())
    return Ok(Type.BOOLEAN)


def _equality(left: Result[Type], right: Result[Type]) -> Result[Type]:
    """Equality operands must be the *same* type (Eq); the result is BOOLEAN."""
    if isinstance(left, Err):
        return left
    if isinstance(right, Err):
        return right
    if left.value is not right.value:
        return Err(RizTypeError())
    return Ok(Type.BOOLEAN)

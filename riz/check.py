"""Type checker: reject ill-typed programs before evaluation.

Runs between parse and eval. Synthesizes a type bottom-up (mirroring eval's
operation table, including the coercion law) and rejects illegal operand
combinations — `True + 1`, `1/2 & 3`, `1 == True` — as type errors *here*,
never at eval (Riz doesn't enforce type rules at runtime).
"""

from dataclasses import dataclass
from enum import Enum, auto

from .parse import (
    Add,
    And,
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
    Not,
    NotEqual,
    Or,
    Subtract,
)
from .result import Err, Ok, Result


@dataclass(frozen=True)
class RizTypeError: ...


class Type(Enum):
    INTEGER = auto()
    RATIONAL = auto()
    BOOLEAN = auto()


_NUMERIC = (Type.INTEGER, Type.RATIONAL)


def check(node: Expr) -> Result[Type]:
    match node:
        case IntLiteral():
            return Ok(Type.INTEGER)
        case BoolLiteral():
            return Ok(Type.BOOLEAN)
        case Negate(operand):
            return _numeric_unary(check(operand))
        case Add(left, right) | Subtract(left, right) | Multiply(left, right):
            return _arithmetic(check(left), check(right))
        case Divide(left, right):
            return _division(check(left), check(right))
        case (
            LessThan(left, right)
            | GreaterThan(left, right)
            | LessOrEqual(left, right)
            | GreaterOrEqual(left, right)
        ):
            return _ordering(check(left), check(right))
        case Equal(left, right) | NotEqual(left, right):
            return _equality(check(left), check(right))
        case Not(operand):
            return _logical_unary(check(operand))
        case And(left, right) | Or(left, right):
            return _and_or(check(left), check(right))


def _number(operand: Result[Type]) -> Type | Err:
    """Unwrap a numeric operand's type, or an Err if it isn't numeric."""
    if isinstance(operand, Err):
        return operand
    if operand.value not in _NUMERIC:
        return Err(RizTypeError())
    return operand.value


def _numbers(left: Result[Type], right: Result[Type]) -> tuple[Type, Type] | Err:
    a = _number(left)
    if isinstance(a, Err):
        return a
    b = _number(right)
    if isinstance(b, Err):
        return b
    return a, b


def _numeric_unary(operand: Result[Type]) -> Result[Type]:
    """`-`: numeric operand → the same numeric type."""
    a = _number(operand)
    return a if isinstance(a, Err) else Ok(a)


def _arithmetic(left: Result[Type], right: Result[Type]) -> Result[Type]:
    """`+ - *`: both numeric; `Int op Int → Int`, else widen to `Rational`."""
    operands = _numbers(left, right)
    if isinstance(operands, Err):
        return operands
    a, b = operands
    if a is Type.INTEGER and b is Type.INTEGER:
        return Ok(Type.INTEGER)
    return Ok(Type.RATIONAL)


def _division(left: Result[Type], right: Result[Type]) -> Result[Type]:
    """`/`: both numeric; always `Rational` (int / int → rational)."""
    operands = _numbers(left, right)
    if isinstance(operands, Err):
        return operands
    return Ok(Type.RATIONAL)


def _ordering(left: Result[Type], right: Result[Type]) -> Result[Type]:
    """`< > <= >=`: both numeric; result BOOLEAN."""
    operands = _numbers(left, right)
    if isinstance(operands, Err):
        return operands
    return Ok(Type.BOOLEAN)


def _equality(left: Result[Type], right: Result[Type]) -> Result[Type]:
    """`== !=`: same type, or both numeric (Int/Rational inter-compare); → BOOLEAN."""
    if isinstance(left, Err):
        return left
    if isinstance(right, Err):
        return right
    both_numeric = left.value in _NUMERIC and right.value in _NUMERIC
    if both_numeric or left.value is right.value:
        return Ok(Type.BOOLEAN)
    return Err(RizTypeError())


def _logical_unary(operand: Result[Type]) -> Result[Type]:
    """`!`: boolean operand → BOOLEAN."""
    if isinstance(operand, Err):
        return operand
    if operand.value is not Type.BOOLEAN:
        return Err(RizTypeError())
    return Ok(Type.BOOLEAN)


def _and_or(left: Result[Type], right: Result[Type]) -> Result[Type]:
    """`& |`: logical on booleans (→ BOOLEAN), bitwise on integers (→ INTEGER)."""
    if isinstance(left, Err):
        return left
    if isinstance(right, Err):
        return right
    if left.value is Type.BOOLEAN and right.value is Type.BOOLEAN:
        return Ok(Type.BOOLEAN)
    if left.value is Type.INTEGER and right.value is Type.INTEGER:
        return Ok(Type.INTEGER)
    return Err(RizTypeError())

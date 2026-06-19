"""Evaluator: walk the syntax tree to a value, or an error that escaped."""

from collections.abc import Callable
from dataclasses import dataclass

from .boolean import Boolean
from .integer import Integer
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
from .ratio import Ratio
from .result import Err, Ok, Result

type Value = Integer | Ratio | Boolean
type Numeric = Integer | Ratio


@dataclass(frozen=True)
class RizDivisionByZeroError: ...


def eval(node: Expr) -> Result[Value]:
    match node:
        case IntLiteral(value):
            return Ok(Integer(value))
        case BoolLiteral(value):
            return Ok(Boolean(value))
        case Negate(operand):
            return _unary(eval(operand), _negate)
        case Add(left, right):
            return _binary(eval(left), eval(right), _add)
        case Subtract(left, right):
            return _binary(eval(left), eval(right), _subtract)
        case Multiply(left, right):
            return _binary(eval(left), eval(right), _multiply)
        case Divide(left, right):
            return _binary(eval(left), eval(right), _divide)
        case LessThan(left, right):
            return _binary(eval(left), eval(right), _less_than)
        case GreaterThan(left, right):
            return _binary(eval(left), eval(right), _greater_than)
        case LessOrEqual(left, right):
            return _binary(eval(left), eval(right), _less_or_equal)
        case GreaterOrEqual(left, right):
            return _binary(eval(left), eval(right), _greater_or_equal)
        case Equal(left, right):
            return _binary_value(eval(left), eval(right), _equal)
        case NotEqual(left, right):
            return _binary_value(eval(left), eval(right), _not_equal)


def _unary(
    operand: Result[Value], op: Callable[[Numeric], Result[Value]]
) -> Result[Value]:
    if isinstance(operand, Err):
        return operand
    return op(_number(operand.value))


def _binary(
    left: Result[Value],
    right: Result[Value],
    op: Callable[[Numeric, Numeric], Result[Value]],
) -> Result[Value]:
    if isinstance(left, Err):
        return left
    if isinstance(right, Err):
        return right
    return op(_number(left.value), _number(right.value))


def _binary_value(
    left: Result[Value],
    right: Result[Value],
    op: Callable[[Value, Value], Result[Value]],
) -> Result[Value]:
    # Like _binary, but passes full values (equality also applies to booleans).
    if isinstance(left, Err):
        return left
    if isinstance(right, Err):
        return right
    return op(left.value, right.value)


def _number(value: Value) -> Numeric:
    # The type checker rejects booleans in arithmetic before eval runs, so one
    # reaching here is a checker bug, not a user error — hence a hard failure.
    if isinstance(value, Boolean):
        raise AssertionError("type checker should reject booleans in arithmetic")
    return value


def _negate(value: Numeric) -> Result[Value]:
    if isinstance(value, Integer):
        return Ok(Integer(-value.value))
    return Ok(Ratio(-value.numerator, value.denominator))


def _add(left: Numeric, right: Numeric) -> Result[Value]:
    if isinstance(left, Integer) and isinstance(right, Integer):
        return Ok(Integer(left.value + right.value))
    a, b = _widen(left), _widen(right)
    return Ok(
        Ratio(
            a.numerator * b.denominator + b.numerator * a.denominator,
            a.denominator * b.denominator,
        )
    )


def _subtract(left: Numeric, right: Numeric) -> Result[Value]:
    if isinstance(left, Integer) and isinstance(right, Integer):
        return Ok(Integer(left.value - right.value))
    a, b = _widen(left), _widen(right)
    return Ok(
        Ratio(
            a.numerator * b.denominator - b.numerator * a.denominator,
            a.denominator * b.denominator,
        )
    )


def _multiply(left: Numeric, right: Numeric) -> Result[Value]:
    if isinstance(left, Integer) and isinstance(right, Integer):
        return Ok(Integer(left.value * right.value))
    a, b = _widen(left), _widen(right)
    return Ok(Ratio(a.numerator * b.numerator, a.denominator * b.denominator))


def _divide(left: Numeric, right: Numeric) -> Result[Value]:
    a, b = _widen(left), _widen(right)
    if b.numerator == 0:
        return Err(RizDivisionByZeroError())
    return Ok(Ratio(a.numerator * b.denominator, a.denominator * b.numerator))


def _ordering(left: Numeric, right: Numeric) -> tuple[int, int]:
    # Compare as fractions by cross-multiplying; denominators are positive, so
    # the inequality direction is preserved.
    a, b = _widen(left), _widen(right)
    return a.numerator * b.denominator, b.numerator * a.denominator


def _less_than(left: Numeric, right: Numeric) -> Result[Value]:
    lhs, rhs = _ordering(left, right)
    return Ok(Boolean(lhs < rhs))


def _greater_than(left: Numeric, right: Numeric) -> Result[Value]:
    lhs, rhs = _ordering(left, right)
    return Ok(Boolean(lhs > rhs))


def _less_or_equal(left: Numeric, right: Numeric) -> Result[Value]:
    lhs, rhs = _ordering(left, right)
    return Ok(Boolean(lhs <= rhs))


def _greater_or_equal(left: Numeric, right: Numeric) -> Result[Value]:
    lhs, rhs = _ordering(left, right)
    return Ok(Boolean(lhs >= rhs))


def _equal(left: Value, right: Value) -> Result[Value]:
    return Ok(Boolean(_equals(left, right)))


def _not_equal(left: Value, right: Value) -> Result[Value]:
    return Ok(Boolean(not _equals(left, right)))


def _equals(left: Value, right: Value) -> bool:
    if isinstance(left, Boolean) and isinstance(right, Boolean):
        return left.value == right.value
    if isinstance(left, Boolean) or isinstance(right, Boolean):
        raise AssertionError("type checker should reject == across number and boolean")
    # both numeric: equal iff equal as fractions
    a, b = _widen(left), _widen(right)
    return a.numerator * b.denominator == b.numerator * a.denominator


def _widen(value: Numeric) -> Ratio:
    if isinstance(value, Integer):
        return Ratio(value.value, 1)
    return value

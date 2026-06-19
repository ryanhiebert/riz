"""Evaluator: walk the syntax tree to a value, or an error that escaped."""

from collections.abc import Callable
from dataclasses import dataclass

from .boolean import Boolean
from .integer import Integer
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
from .rational import Rational
from .result import Err, Ok, Result

type Value = Integer | Rational | Boolean
type Numeric = Integer | Rational


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


def _number(value: Value) -> Numeric:
    # The type checker rejects booleans in arithmetic before eval runs, so one
    # reaching here is a checker bug, not a user error — hence a hard failure.
    if isinstance(value, Boolean):
        raise AssertionError("type checker should reject booleans in arithmetic")
    return value


def _negate(value: Numeric) -> Result[Value]:
    if isinstance(value, Integer):
        return Ok(Integer(-value.value))
    return Ok(Rational(-value.numerator, value.denominator))


def _add(left: Numeric, right: Numeric) -> Result[Value]:
    if isinstance(left, Integer) and isinstance(right, Integer):
        return Ok(Integer(left.value + right.value))
    a, b = _widen(left), _widen(right)
    return Ok(
        Rational(
            a.numerator * b.denominator + b.numerator * a.denominator,
            a.denominator * b.denominator,
        )
    )


def _subtract(left: Numeric, right: Numeric) -> Result[Value]:
    if isinstance(left, Integer) and isinstance(right, Integer):
        return Ok(Integer(left.value - right.value))
    a, b = _widen(left), _widen(right)
    return Ok(
        Rational(
            a.numerator * b.denominator - b.numerator * a.denominator,
            a.denominator * b.denominator,
        )
    )


def _multiply(left: Numeric, right: Numeric) -> Result[Value]:
    if isinstance(left, Integer) and isinstance(right, Integer):
        return Ok(Integer(left.value * right.value))
    a, b = _widen(left), _widen(right)
    return Ok(Rational(a.numerator * b.numerator, a.denominator * b.denominator))


def _divide(left: Numeric, right: Numeric) -> Result[Value]:
    a, b = _widen(left), _widen(right)
    if b.numerator == 0:
        return Err(RizDivisionByZeroError())
    return Ok(Rational(a.numerator * b.denominator, a.denominator * b.numerator))


def _widen(value: Numeric) -> Rational:
    if isinstance(value, Integer):
        return Rational(value.value, 1)
    return value

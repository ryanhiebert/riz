"""Evaluator: walk the syntax tree to a value, or an error that escaped."""

from collections.abc import Callable
from dataclasses import dataclass

from .integer import Integer
from .parse import Add, Divide, Expr, IntLiteral, Multiply, Negate, Subtract
from .rational import Rational
from .result import Err, Ok, Result

type Value = Integer | Rational


@dataclass(frozen=True)
class RizDivisionByZeroError: ...


def eval(node: Expr) -> Result[Value]:
    match node:
        case IntLiteral(value):
            return Ok(Integer(value))
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
    operand: Result[Value], op: Callable[[Value], Result[Value]]
) -> Result[Value]:
    if isinstance(operand, Err):
        return operand
    return op(operand.value)


def _binary(
    left: Result[Value],
    right: Result[Value],
    op: Callable[[Value, Value], Result[Value]],
) -> Result[Value]:
    if isinstance(left, Err):
        return left
    if isinstance(right, Err):
        return right
    return op(left.value, right.value)


def _negate(value: Value) -> Result[Value]:
    if isinstance(value, Integer):
        return Ok(Integer(-value.value))
    return Ok(Rational(-value.numerator, value.denominator))


def _add(left: Value, right: Value) -> Result[Value]:
    if isinstance(left, Integer) and isinstance(right, Integer):
        return Ok(Integer(left.value + right.value))
    a, b = _widen(left), _widen(right)
    return Ok(
        Rational(
            a.numerator * b.denominator + b.numerator * a.denominator,
            a.denominator * b.denominator,
        )
    )


def _subtract(left: Value, right: Value) -> Result[Value]:
    if isinstance(left, Integer) and isinstance(right, Integer):
        return Ok(Integer(left.value - right.value))
    a, b = _widen(left), _widen(right)
    return Ok(
        Rational(
            a.numerator * b.denominator - b.numerator * a.denominator,
            a.denominator * b.denominator,
        )
    )


def _multiply(left: Value, right: Value) -> Result[Value]:
    if isinstance(left, Integer) and isinstance(right, Integer):
        return Ok(Integer(left.value * right.value))
    a, b = _widen(left), _widen(right)
    return Ok(Rational(a.numerator * b.numerator, a.denominator * b.denominator))


def _divide(left: Value, right: Value) -> Result[Value]:
    # int / int -> rational; any operand widens int -> rational losslessly first
    a, b = _widen(left), _widen(right)
    if b.numerator == 0:
        return Err(RizDivisionByZeroError())
    return Ok(Rational(a.numerator * b.denominator, a.denominator * b.numerator))


def _widen(value: Value) -> Rational:
    if isinstance(value, Integer):
        return Rational(value.value, 1)
    return value

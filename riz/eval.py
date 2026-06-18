"""Evaluator: walk the syntax tree to produce Riz values."""

from .integer import Integer
from .parse import Add, Divide, Expr, IntLiteral, Multiply, Subtract
from .rational import Rational


def eval(node: Expr) -> Integer | Rational:
    match node:
        case IntLiteral(value):
            return Integer(value)
        case Add(left, right):
            return _add(eval(left), eval(right))
        case Subtract(left, right):
            return _subtract(eval(left), eval(right))
        case Multiply(left, right):
            return _multiply(eval(left), eval(right))
        case Divide(left, right):
            return _divide(eval(left), eval(right))


def _add(left: Integer | Rational, right: Integer | Rational) -> Integer | Rational:
    if isinstance(left, Integer) and isinstance(right, Integer):
        return Integer(left.value + right.value)
    a, b = _widen(left), _widen(right)
    return Rational(
        a.numerator * b.denominator + b.numerator * a.denominator,
        a.denominator * b.denominator,
    )


def _subtract(left: Integer | Rational, right: Integer | Rational) -> Integer | Rational:
    if isinstance(left, Integer) and isinstance(right, Integer):
        return Integer(left.value - right.value)
    a, b = _widen(left), _widen(right)
    return Rational(
        a.numerator * b.denominator - b.numerator * a.denominator,
        a.denominator * b.denominator,
    )


def _multiply(left: Integer | Rational, right: Integer | Rational) -> Integer | Rational:
    if isinstance(left, Integer) and isinstance(right, Integer):
        return Integer(left.value * right.value)
    a, b = _widen(left), _widen(right)
    return Rational(a.numerator * b.numerator, a.denominator * b.denominator)


def _divide(left: Integer | Rational, right: Integer | Rational) -> Rational:
    # int / int -> rational; any operand widens int -> rational losslessly first
    a, b = _widen(left), _widen(right)
    return Rational(a.numerator * b.denominator, a.denominator * b.numerator)


def _widen(value: Integer | Rational) -> Rational:
    if isinstance(value, Integer):
        return Rational(value.value, 1)
    return value

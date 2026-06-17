"""Evaluator: walk the syntax tree to produce Riz values."""

from .integer import Integer
from .parse import Divide, Expr, IntLiteral
from .rational import Rational


def eval(node: Expr) -> Integer | Rational:
    match node:
        case IntLiteral(value):
            return Integer(value)
        case Divide(numerator, denominator):
            # int / int -> rational (the one lossless widening)
            return Rational(numerator.value, denominator.value)

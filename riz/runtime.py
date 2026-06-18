"""The Riz runtime."""

from .eval import eval
from .integer import Integer
from .lex import lex
from .parse import RizParseError, parse
from .rational import Rational


class Runtime:
    def evaluate(self, source: str) -> Integer | Rational:
        return eval(parse(lex(source)))


def test_integer_parsing():
    riz = Runtime()
    assert str(riz.evaluate("5")) == "5"
    assert str(riz.evaluate("4")) == "4"


def test_non_decimal_digits_rejected():
    riz = Runtime()
    # Digit-like characters that aren't decimal digits (str.isdigit() is True
    # but they're not Nd) must surface as RizParseError, not crash the runtime.
    for bad in ("²", "①"):
        try:
            _ = riz.evaluate(bad)
        except RizParseError:
            pass
        else:
            raise AssertionError(f"{bad!r} should raise RizParseError")


def test_divides_to_lowest_terms():
    riz = Runtime()
    assert str(riz.evaluate("6/3")) == "2"
    assert str(riz.evaluate("6/4")) == "3/2"
    assert str(riz.evaluate("5/4")) == "5/4"


def test_addition():
    riz = Runtime()
    assert str(riz.evaluate("2+3")) == "5"
    assert str(riz.evaluate("1/2+1/3")) == "5/6"
    assert str(riz.evaluate("2+3/4")) == "11/4"


def test_subtraction():
    riz = Runtime()
    assert str(riz.evaluate("5-2")) == "3"
    assert str(riz.evaluate("2-5")) == "-3"
    assert str(riz.evaluate("1/3-1/2")) == "-1/6"
    assert str(riz.evaluate("5-2-1")) == "2"
    assert str(riz.evaluate("1-1/2")) == "1/2"


def test_multiplication():
    riz = Runtime()
    assert str(riz.evaluate("2*3")) == "6"
    assert str(riz.evaluate("1/2*2/3")) == "1/3"
    assert str(riz.evaluate("2*3/4")) == "3/2"  # same tier as '/', left-assoc
    assert str(riz.evaluate("2+3*4")) == "14"  # '*' binds tighter than '+'


def test_operator_precedence():
    riz = Runtime()
    assert str(riz.evaluate("1+1/2")) == "3/2"
    assert str(riz.evaluate("6/4/2")) == "3/4"


def test_parentheses():
    riz = Runtime()
    assert str(riz.evaluate("(2+3)*4")) == "20"  # overrides precedence
    assert str(riz.evaluate("2*(3+4)")) == "14"
    assert str(riz.evaluate("(6+4)/2")) == "5"
    for bad in ("(2+3", "2+3)", "()"):  # mismatched parens are parse errors
        try:
            _ = riz.evaluate(bad)
        except RizParseError:
            pass
        else:
            raise AssertionError(f"{bad!r} should raise RizParseError")


def test_whitespace():
    riz = Runtime()
    assert str(riz.evaluate("2 + 3")) == "5"
    assert str(riz.evaluate(" 1/2  +  1/3 ")) == "5/6"
    assert str(riz.evaluate("(2 + 3) * 4")) == "20"


def test_unary_minus():
    riz = Runtime()
    assert str(riz.evaluate("-3")) == "-3"
    assert str(riz.evaluate("-1/2")) == "-1/2"  # (-1)/2, a negative rational
    assert str(riz.evaluate("-(2+3)")) == "-5"  # negates a parenthesized group
    assert str(riz.evaluate("-2*3")) == "-6"  # (-2)*3 — binds tighter than *
    assert str(riz.evaluate("2*-3")) == "-6"  # 2*(-3) — prefix in operand position
    assert str(riz.evaluate("-2-3")) == "-5"  # (-2)-3, not -(2-3)
    assert str(riz.evaluate("2--3")) == "5"  # 2-(-3)
    assert str(riz.evaluate("--3")) == "3"  # double negation

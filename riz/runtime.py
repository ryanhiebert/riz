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


def test_operator_precedence():
    riz = Runtime()
    assert str(riz.evaluate("1+1/2")) == "3/2"
    assert str(riz.evaluate("6/4/2")) == "3/4"

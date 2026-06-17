"""The Riz runtime."""

import re

from .integer import Integer
from .parse import RizParseError
from .rational import Rational


class Runtime:
    def evaluate(self, source: str) -> Integer | Rational:
        if re.match(r"^\d+$", source):
            return Integer(int(source))
        match = re.match(r"^(\d+)/(\d+)$", source)
        if not match:
            raise RizParseError("Invalid syntax.")
        num, den = match.group(1, 2)
        return Rational(int(num), int(den))


def test_integer_parsing():
    riz = Runtime()
    assert str(riz.evaluate("5")) == "5"
    assert str(riz.evaluate("4")) == "4"


def test_non_decimal_digits_rejected():
    riz = Runtime()
    # str.isdigit() accepts these but int() would reject them; they must
    # surface as RizParseError, not a leaked host ValueError.
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

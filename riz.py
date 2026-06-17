import re
from dataclasses import dataclass
from math import gcd
from typing import override


class RizParseError(Exception): ...


@dataclass(frozen=True)
class Integer:
    value: int

    @override
    def __str__(self):
        return str(self.value)


@dataclass(frozen=True)
class Rational:
    numerator: int
    denominator: int

    def __post_init__(self):
        g = gcd(self.numerator, self.denominator)
        object.__setattr__(self, "numerator", self.numerator // g)
        object.__setattr__(self, "denominator", self.denominator // g)

    @override
    def __str__(self):
        if self.denominator == 1:
            return str(self.numerator)
        return f"{self.numerator}/{self.denominator}"


class Riz:
    def evaluate(self, source: str) -> Integer | Rational:
        if re.match(r"^\d+$", source):
            return Integer(int(source))
        match = re.match(r"^(\d+)/(\d+)$", source)
        if not match:
            raise RizParseError("Invalid syntax.")
        num, den = match.group(1, 2)
        return Rational(int(num), int(den))


def test_divides_to_lowest_terms():
    assert str(Riz().evaluate("6/3")) == "2"
    assert str(Riz().evaluate("6/4")) == "3/2"
    assert str(Riz().evaluate("5/4")) == "5/4"


def test_integer_parsing():
    assert str(Riz().evaluate("5")) == "5"
    assert str(Riz().evaluate("4")) == "4"

from dataclasses import dataclass
from math import gcd
from typing import override


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

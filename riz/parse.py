from dataclasses import dataclass

from .lex import IntegerToken, SlashToken, Token


class RizParseError(Exception): ...


@dataclass(frozen=True)
class IntLiteral:
    value: int


@dataclass(frozen=True)
class Divide:
    numerator: IntLiteral
    denominator: IntLiteral


Expr = IntLiteral | Divide


def parse(tokens: list[Token]) -> Expr:
    match tokens:
        case [IntegerToken(value)]:
            return IntLiteral(value)
        case [IntegerToken(numerator), SlashToken(), IntegerToken(denominator)]:
            return Divide(IntLiteral(numerator), IntLiteral(denominator))
        case _:
            raise RizParseError("Invalid syntax.")

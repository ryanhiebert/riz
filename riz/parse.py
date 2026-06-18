from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .lex import IntegerToken, MinusToken, PlusToken, SlashToken, StarToken, Token


class RizParseError(Exception): ...


@dataclass(frozen=True)
class IntLiteral:
    value: int


@dataclass(frozen=True)
class Add:
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Subtract:
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Multiply:
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Divide:
    left: Expr
    right: Expr


Expr = IntLiteral | Add | Subtract | Multiply | Divide


# Infix operators: token type -> (binding power, AST constructor).
# Higher binding power binds tighter; all are left-associative.
_INFIX: dict[type[Token], tuple[int, Callable[[Expr, Expr], Expr]]] = {
    PlusToken: (1, Add),
    MinusToken: (1, Subtract),
    StarToken: (2, Multiply),
    SlashToken: (2, Divide),
}


class _Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens: list[Token] = tokens
        self.position: int = 0

    def at_end(self) -> bool:
        return self.position >= len(self.tokens)

    def peek(self) -> Token | None:
        return None if self.at_end() else self.tokens[self.position]

    def expression(self, min_bp: int) -> Expr:
        left = self.primary()
        while (token := self.peek()) is not None:
            infix = _INFIX.get(type(token))
            if infix is None:
                break
            bp, make = infix
            if bp < min_bp:
                break
            self.position += 1
            left = make(left, self.expression(bp + 1))
        return left

    def primary(self) -> Expr:
        token = self.peek()
        if not isinstance(token, IntegerToken):
            raise RizParseError("Invalid syntax.")
        self.position += 1
        return IntLiteral(token.value)


def parse(tokens: list[Token]) -> Expr:
    parser = _Parser(tokens)
    expr = parser.expression(0)
    if not parser.at_end():
        raise RizParseError("Invalid syntax.")
    return expr

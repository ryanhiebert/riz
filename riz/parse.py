from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .lex import (
    IdentifierToken,
    IntegerToken,
    LeftParenthesisToken,
    MinusToken,
    PlusToken,
    RightParenthesisToken,
    SlashToken,
    StarToken,
    Token,
)
from .result import Err, Ok, Result


@dataclass(frozen=True)
class RizParseError: ...


@dataclass(frozen=True)
class IntLiteral:
    value: int


@dataclass(frozen=True)
class BoolLiteral:
    value: bool


@dataclass(frozen=True)
class Negate:
    operand: Expr


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


Expr = IntLiteral | BoolLiteral | Negate | Add | Subtract | Multiply | Divide


# Infix operators: token type -> (binding power, AST constructor).
# Higher binding power binds tighter; all are left-associative.
_INFIX: dict[type[Token], tuple[int, Callable[[Expr, Expr], Expr]]] = {
    PlusToken: (1, Add),
    MinusToken: (1, Subtract),
    StarToken: (2, Multiply),
    SlashToken: (2, Divide),
}

# Prefix `-` (negation) binds tighter than any binary operator, so `-2*3`
# is `(-2)*3` and `-2-3` is `(-2)-3`.
_PREFIX_BP = 3


class _Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens: list[Token] = tokens
        self.position: int = 0

    def at_end(self) -> bool:
        return self.position >= len(self.tokens)

    def peek(self) -> Token | None:
        return None if self.at_end() else self.tokens[self.position]

    def expression(self, min_bp: int) -> Result[Expr]:
        left = self.primary()
        if isinstance(left, Err):
            return left
        node = left.value
        while (token := self.peek()) is not None:
            infix = _INFIX.get(type(token))
            if infix is None:
                break
            bp, make = infix
            if bp < min_bp:
                break
            self.position += 1
            right = self.expression(bp + 1)
            if isinstance(right, Err):
                return right
            node = make(node, right.value)
        return Ok(node)

    def primary(self) -> Result[Expr]:
        token = self.peek()
        if isinstance(token, IntegerToken):
            self.position += 1
            return Ok(IntLiteral(token.value))
        if isinstance(token, IdentifierToken):
            self.position += 1
            if token.name == "True":
                return Ok(BoolLiteral(True))
            if token.name == "False":
                return Ok(BoolLiteral(False))
            return Err(RizParseError())  # unknown identifier (no variables yet)
        if isinstance(token, LeftParenthesisToken):
            self.position += 1
            inner = self.expression(0)
            if isinstance(inner, Err):
                return inner
            if not isinstance(self.peek(), RightParenthesisToken):
                return Err(RizParseError())
            self.position += 1
            return inner
        if isinstance(token, MinusToken):
            self.position += 1
            operand = self.expression(_PREFIX_BP)
            if isinstance(operand, Err):
                return operand
            return Ok(Negate(operand.value))
        return Err(RizParseError())


def parse(tokens: list[Token]) -> Result[Expr]:
    parser = _Parser(tokens)
    result = parser.expression(0)
    if isinstance(result, Err):
        return result
    if not parser.at_end():
        return Err(RizParseError())
    return result

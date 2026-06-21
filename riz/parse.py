from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .lex import (
    AndToken,
    ColonToken,
    EqualsToken,
    EqualToken,
    GreaterOrEqualToken,
    GreaterThanToken,
    IdentifierToken,
    IntegerToken,
    LeftParenthesisToken,
    LessOrEqualToken,
    LessThanToken,
    MinusToken,
    NotEqualToken,
    NotToken,
    OrToken,
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
class Variable:
    name: str


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


@dataclass(frozen=True)
class LessThan:
    left: Expr
    right: Expr


@dataclass(frozen=True)
class GreaterThan:
    left: Expr
    right: Expr


@dataclass(frozen=True)
class LessOrEqual:
    left: Expr
    right: Expr


@dataclass(frozen=True)
class GreaterOrEqual:
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Equal:
    left: Expr
    right: Expr


@dataclass(frozen=True)
class NotEqual:
    left: Expr
    right: Expr


@dataclass(frozen=True)
class And:
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Or:
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Not:
    operand: Expr


# A conditional `if c: a else: b` — an expression yielding the taken branch's
# value. Both branches must share a type (the checker's rule); eval runs only
# the branch the condition selects.
@dataclass(frozen=True)
class Conditional:
    condition: Expr
    consequent: Expr
    alternative: Expr


# A loop `while c: body` — an expression of type Unit; the body runs for effect
# (its value is discarded) while the condition holds.
@dataclass(frozen=True)
class WhileLoop:
    condition: Expr
    body: Expr


# A binding's left-hand side is a *pattern*, not a bare name — the seam that
# grows tuple/wildcard/nested variants once destructuring lands. Today the only
# variant is `Bind`, an identifier pattern.
@dataclass(frozen=True)
class Bind:
    name: str


Pattern = Bind


# Assignment is an *expression* that evaluates to `Unit` (riz is
# expression-oriented), so `Binding` lives in `Expr` and nests freely — misuse
# like `1 + (x = 5)` is left for the type checker (Int + Unit), not the grammar.
# `=` is non-recursive: its right side is parsed in the surrounding scope, so a
# name still holds its old value there (which is what makes `n = n + 1` work).
@dataclass(frozen=True)
class Binding:
    target: Pattern
    value: Expr


Expr = (
    IntLiteral
    | BoolLiteral
    | Variable
    | Binding
    | Conditional
    | WhileLoop
    | Negate
    | Not
    | Add
    | Subtract
    | Multiply
    | Divide
    | LessThan
    | GreaterThan
    | LessOrEqual
    | GreaterOrEqual
    | Equal
    | NotEqual
    | And
    | Or
)


# Infix operators: token type -> (binding power, AST constructor).
# Higher binding power binds tighter; all are left-associative.
# Binding powers start at 1; 0 is the floor passed to `expression` to parse a
# full expression (so every real operator binds tighter than "parse anything").
_INFIX: dict[type[Token], tuple[int, Callable[[Expr, Expr], Expr]]] = {
    OrToken: (1, Or),
    AndToken: (2, And),
    EqualToken: (3, Equal),
    NotEqualToken: (3, NotEqual),
    LessThanToken: (4, LessThan),
    GreaterThanToken: (4, GreaterThan),
    LessOrEqualToken: (4, LessOrEqual),
    GreaterOrEqualToken: (4, GreaterOrEqual),
    PlusToken: (5, Add),
    MinusToken: (5, Subtract),
    StarToken: (6, Multiply),
    SlashToken: (6, Divide),
}

# Prefix operators `-` (negate) and `!` (not) bind tighter than any binary
# operator, so `-2*3` is `(-2)*3` and `!a == b` is `(!a) == b`.
_PREFIX_BP = 7

# Assignment `=` is the loosest operator of all — looser than every `_INFIX`
# entry (which start at 1) — and right-associative, so `a = b = c` groups as
# `a = (b = c)`. Its already-parsed left side is reinterpreted as a pattern.
_ASSIGN_BP = 0


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
            if isinstance(token, EqualsToken):
                if _ASSIGN_BP < min_bp:
                    break
                self.position += 1
                target = self._as_pattern(node)
                if isinstance(target, Err):
                    return target
                # Right-associative: parse the RHS at the same binding power.
                right = self.expression(_ASSIGN_BP)
                if isinstance(right, Err):
                    return right
                node = Binding(target.value, right.value)
                continue
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
            if token.name == "if":
                return self._conditional()
            if token.name == "while":
                return self._while()
            if token.name == "else":
                return Err(RizParseError())  # 'else' with no matching 'if'
            return Ok(Variable(token.name))
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
        if isinstance(token, NotToken):
            self.position += 1
            operand = self.expression(_PREFIX_BP)
            if isinstance(operand, Err):
                return operand
            return Ok(Not(operand.value))
        return Err(RizParseError())


    def _conditional(self) -> Result[Expr]:
        # `if` already consumed. Parse `<cond> : <consequent> else : <alt>`.
        # Each part is a full expression; the condition stops at the `:` (which
        # isn't an operator), and the consequent stops at the `else` keyword.
        condition = self.expression(0)
        if isinstance(condition, Err):
            return condition
        if not isinstance(self.peek(), ColonToken):
            return Err(RizParseError())
        self.position += 1
        consequent = self.expression(0)
        if isinstance(consequent, Err):
            return consequent
        keyword = self.peek()
        if not (isinstance(keyword, IdentifierToken) and keyword.name == "else"):
            return Err(RizParseError())
        self.position += 1
        if not isinstance(self.peek(), ColonToken):
            return Err(RizParseError())
        self.position += 1
        alternative = self.expression(0)
        if isinstance(alternative, Err):
            return alternative
        return Ok(Conditional(condition.value, consequent.value, alternative.value))

    def _while(self) -> Result[Expr]:
        # `while` already consumed. Parse `<cond> : <body>` (single-expression
        # body for now; multi-statement bodies await the block-syntax decision).
        condition = self.expression(0)
        if isinstance(condition, Err):
            return condition
        if not isinstance(self.peek(), ColonToken):
            return Err(RizParseError())
        self.position += 1
        body = self.expression(0)
        if isinstance(body, Err):
            return body
        return Ok(WhileLoop(condition.value, body.value))

    def _as_pattern(self, expr: Expr) -> Result[Pattern]:
        # Only a bare name is a legal binding target today; `1 = 2` etc. fail.
        if isinstance(expr, Variable):
            return Ok(Bind(expr.name))
        return Err(RizParseError())


def parse(tokens: list[Token]) -> Result[Expr]:
    parser = _Parser(tokens)
    result = parser.expression(0)
    if isinstance(result, Err):
        return result
    if not parser.at_end():
        return Err(RizParseError())
    return result

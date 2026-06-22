from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .lex import (
    AndToken,
    ColonToken,
    DedentToken,
    EqualsToken,
    EqualToken,
    GreaterOrEqualToken,
    GreaterThanToken,
    IdentifierToken,
    IndentToken,
    IntegerToken,
    LeftParenthesisToken,
    LessOrEqualToken,
    LessThanToken,
    MinusToken,
    NewlineToken,
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


# A sequence of statements (newline-separated, or an indented body). It runs them
# in order and evaluates to the last one's value — the top-level program is one.
@dataclass(frozen=True)
class Block:
    statements: tuple[Expr, ...]


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
    | Block
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
        consequent = self._body()
        if isinstance(consequent, Err):
            return consequent
        keyword = self.peek()
        if not (isinstance(keyword, IdentifierToken) and keyword.name == "else"):
            return Err(RizParseError())
        self.position += 1
        if not isinstance(self.peek(), ColonToken):
            return Err(RizParseError())
        self.position += 1
        alternative = self._body()
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
        body = self._body()
        if isinstance(body, Err):
            return body
        return Ok(WhileLoop(condition.value, body.value))

    def _body(self) -> Result[Expr]:
        # The body after a `:` — an inline expression on the same line, or an
        # indented block (NEWLINE, then INDENT…statements…DEDENT).
        if not isinstance(self.peek(), NewlineToken):
            return self.expression(0)  # inline body
        self.position += 1  # consume the NEWLINE
        if not isinstance(self.peek(), IndentToken):
            return Err(RizParseError())  # expected an indented block
        self.position += 1  # consume the INDENT
        statements = self.statements()
        if isinstance(statements, Err):
            return statements
        if not statements.value or not isinstance(self.peek(), DedentToken):
            return Err(RizParseError())  # empty or unterminated block
        self.position += 1  # consume the DEDENT
        if len(statements.value) == 1:
            return Ok(statements.value[0])
        body: Expr = Block(tuple(statements.value))
        return Ok(body)

    def statements(self) -> Result[list[Expr]]:
        # Statements until this level ends (a DEDENT, or end of input). They're
        # separated by NEWLINE — except a block-bodied statement ends with a
        # DEDENT instead, so it needs no NEWLINE after it.
        statements: list[Expr] = []
        while not self.at_end() and not isinstance(self.peek(), DedentToken):
            statement = self.expression(0)
            if isinstance(statement, Err):
                return statement
            statements.append(statement.value)
            if isinstance(self.peek(), NewlineToken):
                self.position += 1  # the separator between statements
            elif self.at_end() or isinstance(self.peek(), DedentToken):
                break  # this statement-list ends here
            elif isinstance(self.tokens[self.position - 1], DedentToken):
                continue  # the previous statement was a block — no NEWLINE needed
            else:
                return Err(RizParseError())  # two statements with no separator
        return Ok(statements)

    def _as_pattern(self, expr: Expr) -> Result[Pattern]:
        # Only a bare name is a legal binding target today; `1 = 2` etc. fail.
        if isinstance(expr, Variable):
            return Ok(Bind(expr.name))
        return Err(RizParseError())


def parse(tokens: list[Token]) -> Result[Expr]:
    # A program is the top-level statement-list. A lone statement is returned
    # bare; several become a `Block`. A stray INDENT (unexpected indent) makes
    # the first statement fail; a stray DEDENT leaves tokens past the at_end check.
    parser = _Parser(tokens)
    statements = parser.statements()
    if isinstance(statements, Err):
        return statements
    if not parser.at_end():
        return Err(RizParseError())
    if not statements.value:
        return Err(RizParseError())  # empty program
    if len(statements.value) == 1:
        return Ok(statements.value[0])
    program: Expr = Block(tuple(statements.value))
    return Ok(program)

"""Lexer: turn Riz source text into a stream of tokens.

Total by design: it never raises. Anything it can't recognize becomes an
``UnknownToken`` and the parser decides what to reject.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class IntegerToken:
    value: int


@dataclass(frozen=True)
class SlashToken: ...


@dataclass(frozen=True)
class PlusToken: ...


@dataclass(frozen=True)
class MinusToken: ...


@dataclass(frozen=True)
class StarToken: ...


@dataclass(frozen=True)
class LeftParenthesisToken: ...


@dataclass(frozen=True)
class RightParenthesisToken: ...


@dataclass(frozen=True)
class LessThanToken: ...


@dataclass(frozen=True)
class GreaterThanToken: ...


@dataclass(frozen=True)
class LessOrEqualToken: ...


@dataclass(frozen=True)
class GreaterOrEqualToken: ...


@dataclass(frozen=True)
class EqualToken: ...


@dataclass(frozen=True)
class EqualsToken: ...  # a single '=', the binding operator (vs '==' equality)


@dataclass(frozen=True)
class ColonToken: ...  # separates a conditional's parts: `if c: a else: b`


@dataclass(frozen=True)
class NotEqualToken: ...


@dataclass(frozen=True)
class AndToken: ...


@dataclass(frozen=True)
class OrToken: ...


@dataclass(frozen=True)
class NotToken: ...


@dataclass(frozen=True)
class IdentifierToken:
    name: str


@dataclass(frozen=True)
class UnknownToken:
    char: str


Token = (
    IntegerToken
    | SlashToken
    | PlusToken
    | MinusToken
    | StarToken
    | LeftParenthesisToken
    | RightParenthesisToken
    | LessThanToken
    | GreaterThanToken
    | LessOrEqualToken
    | GreaterOrEqualToken
    | EqualToken
    | EqualsToken
    | ColonToken
    | NotEqualToken
    | AndToken
    | OrToken
    | NotToken
    | IdentifierToken
    | UnknownToken
)


def lex(source: str) -> list[Token]:
    tokens: list[Token] = []
    position = 0
    while position < len(source):
        char = source[position]
        if char in (" ", "\t"):
            # Discard horizontal whitespace. Newlines are left untouched; they
            # may become statement separators later, like in Python.
            position += 1
        elif char == "/":
            tokens.append(SlashToken())
            position += 1
        elif char == "+":
            tokens.append(PlusToken())
            position += 1
        elif char == "-":
            tokens.append(MinusToken())
            position += 1
        elif char == "*":
            tokens.append(StarToken())
            position += 1
        elif char == "(":
            tokens.append(LeftParenthesisToken())
            position += 1
        elif char == ")":
            tokens.append(RightParenthesisToken())
            position += 1
        elif char == "<":
            if source[position + 1 : position + 2] == "=":
                tokens.append(LessOrEqualToken())
                position += 2
            else:
                tokens.append(LessThanToken())
                position += 1
        elif char == ">":
            if source[position + 1 : position + 2] == "=":
                tokens.append(GreaterOrEqualToken())
                position += 2
            else:
                tokens.append(GreaterThanToken())
                position += 1
        elif char == "=":
            if source[position + 1 : position + 2] == "=":
                tokens.append(EqualToken())
                position += 2
            else:
                tokens.append(EqualsToken())  # bare '=' binds a name
                position += 1
        elif char == "!":
            if source[position + 1 : position + 2] == "=":
                tokens.append(NotEqualToken())
                position += 2
            else:
                tokens.append(NotToken())
                position += 1
        elif char == ":":
            tokens.append(ColonToken())
            position += 1
        elif char == "&":
            tokens.append(AndToken())
            position += 1
        elif char == "|":
            tokens.append(OrToken())
            position += 1
        elif char.isalpha():
            start = position
            while position < len(source) and source[position].isalnum():
                position += 1
            tokens.append(IdentifierToken(source[start:position]))
        elif char.isdecimal():
            start = position
            while position < len(source) and source[position].isdecimal():
                position += 1
            tokens.append(IntegerToken(int(source[start:position])))
        else:
            tokens.append(UnknownToken(char))
            position += 1
    return tokens

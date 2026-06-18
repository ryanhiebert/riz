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
        elif char.isdecimal():
            start = position
            while position < len(source) and source[position].isdecimal():
                position += 1
            tokens.append(IntegerToken(int(source[start:position])))
        else:
            tokens.append(UnknownToken(char))
            position += 1
    return tokens

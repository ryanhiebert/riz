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
class UnknownToken:
    char: str


Token = IntegerToken | SlashToken | PlusToken | MinusToken | UnknownToken


def lex(source: str) -> list[Token]:
    tokens: list[Token] = []
    position = 0
    while position < len(source):
        char = source[position]
        if char == "/":
            tokens.append(SlashToken())
            position += 1
        elif char == "+":
            tokens.append(PlusToken())
            position += 1
        elif char == "-":
            tokens.append(MinusToken())
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

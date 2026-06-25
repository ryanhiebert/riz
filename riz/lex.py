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
class CommaToken: ...  # separates parameters and arguments: `f(a, b)`


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
class NewlineToken: ...  # separates statements (between logical lines)


@dataclass(frozen=True)
class IndentToken: ...  # a logical line indented deeper than the previous one


@dataclass(frozen=True)
class DedentToken: ...  # a logical line indented less; closes a block


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
    | CommaToken
    | NotEqualToken
    | AndToken
    | OrToken
    | NotToken
    | NewlineToken
    | IndentToken
    | DedentToken
    | IdentifierToken
    | UnknownToken
)


def lex(source: str) -> list[Token]:
    """Lex Riz source into tokens, including layout (NEWLINE/INDENT/DEDENT).

    Indentation is by **spaces**, Python-style: any deeper indentation opens one
    block — the amount is free but must be consistent, so a dedent has to land on
    an enclosing level. A tab anywhere is an error — riz uses spaces, never tabs.

    Column 0 is level 0, so a line that starts indented at the top is an
    "unexpected indent" — a stray INDENT the parser rejects. Newlines and
    indentation are suppressed inside parentheses (line continuation). A NEWLINE
    separates logical lines; there is no trailing NEWLINE, and DEDENTs close open
    blocks at end of input — so an unindented single line tokenizes exactly as it
    did before layout.
    """
    tokens: list[Token] = []
    position = 0
    length = len(source)
    indent_stack = [0]
    paren_depth = 0
    at_line_start = True

    while position < length:
        if at_line_start and paren_depth == 0:
            indent = 0
            while position < length and source[position] == " ":
                indent += 1
                position += 1
            if position >= length:
                break  # only trailing whitespace remained
            if source[position] == "\n":
                position += 1  # blank line: no tokens, indentation irrelevant
                continue
            if source[position] == "\t":
                tokens.append(UnknownToken("\t"))  # indentation is spaces-only
                position += 1
                at_line_start = False
                continue
            if indent > indent_stack[-1]:
                indent_stack.append(indent)  # any deeper indentation opens a block
                tokens.append(IndentToken())
            elif indent < indent_stack[-1]:
                while len(indent_stack) > 1 and indent < indent_stack[-1]:
                    _ = indent_stack.pop()
                    tokens.append(DedentToken())
                if indent != indent_stack[-1]:
                    tokens.append(UnknownToken(" "))  # dedent matches no outer level
            at_line_start = False
            continue

        char = source[position]
        if char == "\n":
            if paren_depth == 0:
                tokens.append(NewlineToken())
                at_line_start = True
            position += 1
        elif char == " ":
            position += 1  # a space within a line is insignificant (tabs error)
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
            paren_depth += 1
            position += 1
        elif char == ")":
            tokens.append(RightParenthesisToken())
            if paren_depth > 0:
                paren_depth -= 1
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
        elif char == ",":
            tokens.append(CommaToken())
            position += 1
        elif char == "&":
            tokens.append(AndToken())
            position += 1
        elif char == "|":
            tokens.append(OrToken())
            position += 1
        elif char.isalpha() or char == "_":
            start = position
            while position < len(source) and (
                source[position].isalnum() or source[position] == "_"
            ):
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

    while len(indent_stack) > 1:  # close any blocks still open at end of input
        _ = indent_stack.pop()
        tokens.append(DedentToken())
    return tokens


def test_single_line_has_no_layout_tokens():
    # Single-line input tokenizes exactly as it did before layout existed.
    assert lex("2 + 3") == [IntegerToken(2), PlusToken(), IntegerToken(3)]


def test_leading_indent_at_top_level_is_an_unexpected_indent():
    # Column 0 is level 0, so a top-level line that starts indented produces a
    # stray INDENT (which the parser rejects).
    assert lex("  1 + 2") == [
        IndentToken(),
        IntegerToken(1),
        PlusToken(),
        IntegerToken(2),
        DedentToken(),
    ]


def test_underscores_in_identifiers():
    # An identifier may contain (and start with) underscores — snake_case names.
    assert lex("snake_case") == [IdentifierToken("snake_case")]
    assert lex("_private") == [IdentifierToken("_private")]
    assert lex("add_1") == [IdentifierToken("add_1")]


def test_newline_separates_top_level_lines():
    assert lex("a\nb") == [IdentifierToken("a"), NewlineToken(), IdentifierToken("b")]


def test_blank_lines_are_skipped():
    assert lex("a\n\n\nb") == [
        IdentifierToken("a"),
        NewlineToken(),
        IdentifierToken("b"),
    ]


def test_indentation_emits_indent_then_dedent():
    assert lex("if c:\n  a\n  b") == [
        IdentifierToken("if"),
        IdentifierToken("c"),
        ColonToken(),
        NewlineToken(),
        IndentToken(),
        IdentifierToken("a"),
        NewlineToken(),
        IdentifierToken("b"),
        DedentToken(),
    ]


def test_dedent_back_to_baseline():
    assert lex("if c:\n  a\nb") == [
        IdentifierToken("if"),
        IdentifierToken("c"),
        ColonToken(),
        NewlineToken(),
        IndentToken(),
        IdentifierToken("a"),
        NewlineToken(),
        DedentToken(),
        IdentifierToken("b"),
    ]


def test_nested_indentation_closes_with_two_dedents():
    assert lex("a:\n  b:\n    c") == [
        IdentifierToken("a"),
        ColonToken(),
        NewlineToken(),
        IndentToken(),
        IdentifierToken("b"),
        ColonToken(),
        NewlineToken(),
        IndentToken(),
        IdentifierToken("c"),
        DedentToken(),
        DedentToken(),
    ]


def test_newlines_suppressed_inside_parentheses():
    # A newline (and the continuation line's indentation) inside parens is line
    # continuation, not a statement separator.
    assert lex("(a +\n b)") == [
        LeftParenthesisToken(),
        IdentifierToken("a"),
        PlusToken(),
        IdentifierToken("b"),
        RightParenthesisToken(),
    ]


def test_tab_in_indentation_is_an_error():
    assert UnknownToken("\t") in lex("\ta")


def test_tab_within_a_line_is_an_error():
    # Tabs aren't insignificant whitespace either — riz uses spaces, never tabs.
    assert UnknownToken("\t") in lex("a\t+ b")


def test_inconsistent_dedent_is_an_error():
    # A dedent must return to an enclosing indentation level; 2 spaces matches
    # neither the body's 4 nor the baseline 0.
    assert UnknownToken(" ") in lex("if c:\n    a\n  b")

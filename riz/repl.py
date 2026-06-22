"""A thin read-eval-print loop over the Riz runtime.

Each entry is parsed and evaluated as its own complete program, and its value is
printed. A line that opens a block (ends with `:`) starts a multi-line entry:
the loop keeps reading indented lines until a blank one, then evaluates the lot.

Run it with `python -m riz` (or `python -m riz.repl`).
"""

import importlib

from .lex import ColonToken, lex
from .result import Err, Ok
from .runtime import Runtime
from .unit import Unit

try:  # readline, if present, enables REPL history and line editing as a side
    _ = importlib.import_module("readline")  # effect — we don't reference it
except ImportError:  # pragma: no cover
    pass

# Same width, so the continuation lines up under the prompt. Indentation is
# spaces (not tabs), so there's no tab-stop grid to align to — the width is free.
_PROMPT = "riz> "
_CONTINUATION = "...| "


def render(source: str, runtime: Runtime) -> str | None:
    """Render one line of input: the value, or a friendly error.

    Returns `None` when there's nothing to echo — blank input, or a binding
    (which evaluates to `Unit`).
    """
    if not source.strip():
        return None
    match runtime.evaluate(source):
        case Ok(Unit()):
            return None
        case Ok(value):
            return str(value)
        case Err(error):
            # Errors are fieldless; the type name is the whole story.
            return f"error: {type(error).__name__}"


def _opens_block(source: str) -> bool:
    """True if a line opens a block — it ends with `:`, so a body must follow."""
    tokens = lex(source)
    return bool(tokens) and isinstance(tokens[-1], ColonToken)


def _read_block(opener: str) -> str | None:
    """Collect an indented block's lines until a blank line; join into one source.

    Returns `None` if the entry is abandoned (Ctrl-C).
    """
    lines = [opener]
    while True:
        try:
            line = input(_CONTINUATION)
        except EOFError:  # Ctrl-D ends the block with what's been entered so far.
            print()
            break
        except KeyboardInterrupt:  # Ctrl-C abandons the whole entry.
            print()
            return None
        if not line.strip():  # a blank line ends the block
            break
        lines.append(line)
    return "\n".join(lines)


def repl() -> None:
    """Read an entry, evaluate it, print the result; repeat until EOF."""
    runtime = Runtime()
    while True:
        try:
            source = input(_PROMPT)
        except EOFError:  # Ctrl-D: leave the REPL.
            print()
            return
        except KeyboardInterrupt:  # Ctrl-C: abandon this line, keep going.
            print()
            continue
        if source == "exit":  # a bare `exit` at the top level leaves the REPL
            return
        if _opens_block(source):
            block = _read_block(source)
            if block is None:  # the entry was abandoned
                continue
            source = block
        rendered = render(source, runtime)
        if rendered is not None:
            print(rendered)


def test_render_value():
    runtime = Runtime()
    assert render("6/4", runtime) == "3/2"
    assert render("2 + 3", runtime) == "5"
    assert render("True", runtime) == "True"


def test_render_blank_is_silent():
    runtime = Runtime()
    assert render("", runtime) is None
    assert render("   ", runtime) is None  # whitespace-only counts as blank


def test_render_error():
    runtime = Runtime()
    assert render("1/0", runtime) == "error: RizDivisionByZeroError"
    assert render("1+", runtime) == "error: RizParseError"
    assert render("True+1", runtime) == "error: RizTypeError"
    assert render("nope", runtime) == "error: RizNameError"


def test_render_binding_is_silent_then_usable():
    runtime = Runtime()
    assert render("x = 6/4", runtime) is None  # a binding echoes nothing
    assert render("x + x", runtime) == "3"  # ...but the name carries across calls


def test_opens_block():
    # A line ending in `:` opens a block and needs an indented body to follow.
    assert _opens_block("while i <= 5:")
    assert _opens_block("if c:")
    assert _opens_block("else:")
    assert not _opens_block("2 + 3")
    assert not _opens_block("if c: a else: b")  # inline form is complete
    assert not _opens_block("")


def test_render_a_multi_line_block():
    runtime = Runtime()
    # What a completed multi-line REPL entry becomes: one newline-joined source.
    source = "i = 1\nsum = 0\nwhile i <= 5:\n  sum = sum + i\n  i = i + 1\nsum"
    assert render(source, runtime) == "15"


if __name__ == "__main__":
    repl()

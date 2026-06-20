"""A thin read-eval-print loop over the Riz runtime.

Each entered line is parsed and evaluated as its own complete program, and
its value is printed. Line-orientation is deliberate: one entry is one
program, keeping statement separation a per-line affair.

Run it with `python -m riz` (or `python -m riz.repl`).
"""

from .result import Err, Ok
from .runtime import Runtime
from .unit import Unit


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


def repl() -> None:
    """Read a line, evaluate it, print the result; repeat until EOF."""
    runtime = Runtime()
    while True:
        try:
            source = input("riz> ")
        except EOFError:  # Ctrl-D: leave the REPL.
            print()
            return
        except KeyboardInterrupt:  # Ctrl-C: abandon this line, keep going.
            print()
            continue
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


if __name__ == "__main__":
    repl()

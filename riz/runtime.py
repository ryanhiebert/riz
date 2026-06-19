"""The Riz runtime."""

from .check import RizTypeError, check
from .eval import RizDivisionByZeroError, Value, eval
from .lex import lex
from .parse import RizParseError, parse
from .result import Err, Ok, Result


class Runtime:
    def evaluate(self, source: str) -> Result[Value]:
        # Whole pipeline is Result-valued: no program error ever raises here.
        parsed = parse(lex(source))
        if isinstance(parsed, Err):
            return parsed
        checked = check(parsed.value)
        if isinstance(checked, Err):
            return checked
        return eval(parsed.value)


def _rendered(result: Result[Value]) -> str:
    """Unwrap a successful result to its rendered value; fail the test otherwise."""
    match result:
        case Ok(value):
            return str(value)
        case Err(error):
            raise AssertionError(f"expected a value, got error: {error!r}")


def test_integer_parsing():
    riz = Runtime()
    assert _rendered(riz.evaluate("5")) == "5"
    assert _rendered(riz.evaluate("4")) == "4"


def test_non_decimal_digits_rejected():
    riz = Runtime()
    # Digit-like characters that aren't decimal digits (str.isdigit() is True
    # but they're not Nd) must surface as a parse error, not crash the runtime.
    for bad in ("²", "①"):
        result = riz.evaluate(bad)
        assert isinstance(result, Err)
        assert isinstance(result.error, RizParseError)


def test_divides_to_lowest_terms():
    riz = Runtime()
    assert _rendered(riz.evaluate("6/3")) == "2"
    assert _rendered(riz.evaluate("6/4")) == "3/2"
    assert _rendered(riz.evaluate("5/4")) == "5/4"


def test_addition():
    riz = Runtime()
    assert _rendered(riz.evaluate("2+3")) == "5"  # int + int -> int
    assert _rendered(riz.evaluate("1/2+1/3")) == "5/6"  # rational + rational
    assert _rendered(riz.evaluate("2+3/4")) == "11/4"  # int widens to rational


def test_subtraction():
    riz = Runtime()
    assert _rendered(riz.evaluate("5-2")) == "3"
    assert _rendered(riz.evaluate("2-5")) == "-3"  # negative integer result
    assert _rendered(riz.evaluate("1/3-1/2")) == "-1/6"  # negative rational
    assert _rendered(riz.evaluate("5-2-1")) == "2"  # left-associative
    assert _rendered(riz.evaluate("1-1/2")) == "1/2"  # '/' binds tighter than '-'


def test_multiplication():
    riz = Runtime()
    assert _rendered(riz.evaluate("2*3")) == "6"
    assert _rendered(riz.evaluate("1/2*2/3")) == "1/3"
    assert _rendered(riz.evaluate("2*3/4")) == "3/2"  # same tier as '/', left-assoc
    assert _rendered(riz.evaluate("2+3*4")) == "14"  # '*' binds tighter than '+'


def test_operator_precedence():
    riz = Runtime()
    assert _rendered(riz.evaluate("1+1/2")) == "3/2"
    assert _rendered(riz.evaluate("6/4/2")) == "3/4"


def test_parentheses():
    riz = Runtime()
    assert _rendered(riz.evaluate("(2+3)*4")) == "20"  # overrides precedence
    assert _rendered(riz.evaluate("2*(3+4)")) == "14"
    assert _rendered(riz.evaluate("(6+4)/2")) == "5"
    for bad in ("(2+3", "2+3)", "()"):  # mismatched parens are parse errors
        result = riz.evaluate(bad)
        assert isinstance(result, Err)
        assert isinstance(result.error, RizParseError)


def test_whitespace():
    riz = Runtime()
    assert _rendered(riz.evaluate("2 + 3")) == "5"
    assert _rendered(riz.evaluate(" 1/2  +  1/3 ")) == "5/6"
    assert _rendered(riz.evaluate("(2 + 3) * 4")) == "20"


def test_unary_minus():
    riz = Runtime()
    assert _rendered(riz.evaluate("-3")) == "-3"
    assert _rendered(riz.evaluate("-1/2")) == "-1/2"  # (-1)/2, a negative rational
    assert _rendered(riz.evaluate("-(2+3)")) == "-5"  # negates a parenthesized group
    assert _rendered(riz.evaluate("-2*3")) == "-6"  # (-2)*3, binds tighter than *
    assert _rendered(riz.evaluate("2*-3")) == "-6"  # 2*(-3), prefix in operand pos.
    assert _rendered(riz.evaluate("-2-3")) == "-5"  # (-2)-3, not -(2-3)
    assert _rendered(riz.evaluate("2--3")) == "5"  # 2-(-3)
    assert _rendered(riz.evaluate("--3")) == "3"  # double negation


def test_division_by_zero():
    riz = Runtime()
    assert _rendered(riz.evaluate("0/5")) == "0"  # zero numerator is fine
    for bad in ("1/0", "5/0", "1/(2-2)", "3/0/4"):
        result = riz.evaluate(bad)
        assert isinstance(result, Err)
        assert isinstance(result.error, RizDivisionByZeroError)


def test_parse_errors():
    riz = Runtime()
    # Each is malformed differently; all must come back as a RizParseError.
    for bad in (
        "",  # empty input
        "+",  # operator with no operands
        "1+",  # binary operator missing its right operand
        "*2",  # binary operator missing its left operand
        "2 3",  # two expressions, no operator between them
        "(",  # nothing inside an unclosed group
        "(2+3",  # unclosed group
        ")",  # stray close paren
        "2)",  # trailing close paren
        "foo",  # unknown identifier (no variables yet)
        "true",  # lowercase: not a keyword (literals are True/False)
    ):
        result = riz.evaluate(bad)
        assert isinstance(result, Err), f"{bad!r} should be an error, got {result!r}"
        assert isinstance(result.error, RizParseError)


def test_bool_literals():
    riz = Runtime()
    assert _rendered(riz.evaluate("True")) == "True"
    assert _rendered(riz.evaluate("False")) == "False"


def test_type_errors():
    riz = Runtime()
    # Booleans in arithmetic are rejected by the checker, before eval.
    for bad in ("True+1", "1+False", "-True", "True/2", "False*3", "(True)+1"):
        result = riz.evaluate(bad)
        assert isinstance(result, Err), f"{bad!r} should be an error, got {result!r}"
        assert isinstance(result.error, RizTypeError)

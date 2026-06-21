"""The Riz runtime."""

from .check import RizNameError, RizTypeError, Type, check
from .eval import RizDivisionByZeroError, Value, eval
from .lex import lex
from .parse import RizParseError, parse
from .result import Err, Ok, Result


class Runtime:
    def __init__(self):
        # Bindings persist across calls (one REPL session). Two parallel envs:
        # the checker's name -> Type and the evaluator's name -> Value.
        self._types: dict[str, Type] = {}
        self._values: dict[str, Value] = {}

    def evaluate(self, source: str) -> Result[Value]:
        # Whole pipeline is Result-valued: no program error ever raises here.
        parsed = parse(lex(source))
        if isinstance(parsed, Err):
            return parsed
        # Check and evaluate against copies, committing both only if the whole
        # statement succeeds — a binding that fails partway leaves no trace.
        types = dict(self._types)
        checked = check(parsed.value, types)
        if isinstance(checked, Err):
            return checked
        values = dict(self._values)
        evaluated = eval(parsed.value, values)
        if isinstance(evaluated, Err):
            return evaluated
        self._types = types
        self._values = values
        return evaluated


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
        "1 = 2",  # a non-name on the left of a binding
        "x = = 3",  # nothing to bind on the right
        "if True 1 else 2",  # conditional missing its colons
        "if True: 1",  # conditional missing its else branch
        "else: 1",  # 'else' with no matching 'if'
    ):
        result = riz.evaluate(bad)
        assert isinstance(result, Err), f"{bad!r} should be an error, got {result!r}"
        assert isinstance(result.error, RizParseError)


def test_bool_literals():
    riz = Runtime()
    assert _rendered(riz.evaluate("True")) == "True"
    assert _rendered(riz.evaluate("False")) == "False"


def test_comparisons():
    riz = Runtime()
    assert _rendered(riz.evaluate("2<3")) == "True"
    assert _rendered(riz.evaluate("3<2")) == "False"
    assert _rendered(riz.evaluate("2<2")) == "False"
    assert _rendered(riz.evaluate("2<=2")) == "True"
    assert _rendered(riz.evaluate("3>2")) == "True"
    assert _rendered(riz.evaluate("2>=3")) == "False"
    assert _rendered(riz.evaluate("1/2 < 2/3")) == "True"  # rationals
    assert _rendered(riz.evaluate("1+1 < 3")) == "True"  # arithmetic binds tighter
    assert _rendered(riz.evaluate("1 < 2+3")) == "True"
    assert _rendered(riz.evaluate("-1 < 1")) == "True"


def test_equality():
    riz = Runtime()
    assert _rendered(riz.evaluate("1==1")) == "True"
    assert _rendered(riz.evaluate("1==2")) == "False"
    assert _rendered(riz.evaluate("1!=2")) == "True"
    assert _rendered(riz.evaluate("6/4 == 3/2")) == "True"  # equal rationals
    assert _rendered(riz.evaluate("6/3 == 2")) == "True"  # ratio equals integer
    assert _rendered(riz.evaluate("True == True")) == "True"
    assert _rendered(riz.evaluate("True != False")) == "True"
    assert _rendered(riz.evaluate("(1<2) == (3<4)")) == "True"  # compare two bools
    assert _rendered(riz.evaluate("1<2 == False")) == "False"  # (1<2) == False; == looser


def test_boolean_operators():
    riz = Runtime()
    assert _rendered(riz.evaluate("True & False")) == "False"
    assert _rendered(riz.evaluate("True & True")) == "True"
    assert _rendered(riz.evaluate("False | True")) == "True"
    assert _rendered(riz.evaluate("False | False")) == "False"
    assert _rendered(riz.evaluate("!True")) == "False"
    assert _rendered(riz.evaluate("!False")) == "True"
    assert _rendered(riz.evaluate("!(1 < 2)")) == "False"
    assert _rendered(riz.evaluate("1<2 & 3<4")) == "True"  # comparisons bind tighter
    assert _rendered(riz.evaluate("1<2 | 5<4")) == "True"
    assert _rendered(riz.evaluate("!True == False")) == "True"  # (!True) == False
    # & binds tighter than |: `True | False & False` = `True | (False & False)`
    assert _rendered(riz.evaluate("True | False & False")) == "True"


def test_boolean_operators_are_eager():
    riz = Runtime()
    # No short-circuit (deliberately, for now): both operands always evaluate,
    # so a div-by-zero on either side surfaces regardless of the other.
    for bad in ("True | 1/0 == 1", "False & 1/0 == 1"):
        result = riz.evaluate(bad)
        assert isinstance(result, Err)
        assert isinstance(result.error, RizDivisionByZeroError)


def test_bitwise():
    riz = Runtime()
    # On integers, & and | are bitwise (logical on booleans).
    assert _rendered(riz.evaluate("6 & 3")) == "2"  # 0b110 & 0b011 = 0b010
    assert _rendered(riz.evaluate("5 | 2")) == "7"  # 0b101 | 0b010 = 0b111
    assert _rendered(riz.evaluate("12 & 10")) == "8"
    assert _rendered(riz.evaluate("1 | 0")) == "1"


def test_type_errors():
    riz = Runtime()
    # Booleans in arithmetic, chained comparisons, cross-type equality, and
    # non-booleans in &&/||/! are rejected by the checker before eval.
    for bad in (
        "True+1",
        "1+False",
        "-True",
        "True/2",
        "False*3",
        "(True)+1",
        "True<2",
        "2<True",
        "1<2<3",
        "1==True",  # cross-type equality: Number vs Boolean
        "True==1",
        "1==2==3",  # (1==2)==3 = Bool == Int
        "True & 1",  # & mixing boolean and integer
        "1 | True",
        "1/2 & 1",  # bitwise & needs integers, not a ratio
        "1/2 | 1/3",
        "!1",  # non-boolean in !
    ):
        result = riz.evaluate(bad)
        assert isinstance(result, Err), f"{bad!r} should be an error, got {result!r}"
        assert isinstance(result.error, RizTypeError)


def test_variables():
    riz = Runtime()
    assert _rendered(riz.evaluate("x = 6/4")) == "()"  # a binding evaluates to Unit
    assert _rendered(riz.evaluate("x")) == "3/2"  # ...and persists across calls
    assert _rendered(riz.evaluate("x + x")) == "3"  # 3/1, a whole ratio, shows as 3
    assert _rendered(riz.evaluate("x * 2")) == "3"


def test_rebinding():
    riz = Runtime()
    _ = riz.evaluate("n = 5")
    _ = riz.evaluate("n = n + 1")  # '=' is non-recursive: the right side sees old n
    assert _rendered(riz.evaluate("n")) == "6"
    _ = riz.evaluate("n = True")  # names rebind freely, even to a different type
    assert _rendered(riz.evaluate("n")) == "True"
    assert _rendered(riz.evaluate("n & False")) == "False"  # now typed as a boolean


def test_assignment_is_an_expression():
    riz = Runtime()
    # A binding nests: it evaluates to Unit, which can flow into another binding.
    assert _rendered(riz.evaluate("y = (x = 5)")) == "()"
    assert _rendered(riz.evaluate("x")) == "5"
    assert _rendered(riz.evaluate("y")) == "()"  # y holds the Unit from (x = 5)
    # Chained, right-associative: `a = (b = 7)`, so a holds Unit and b holds 7.
    assert _rendered(riz.evaluate("a = b = 7")) == "()"
    assert _rendered(riz.evaluate("b")) == "7"
    assert _rendered(riz.evaluate("a")) == "()"


def test_unit_in_arithmetic_is_a_type_error():
    riz = Runtime()
    # Nesting is policed by the checker, not the grammar: Unit isn't a number.
    for bad in ("1 + (x = 5)", "(x = 5) * 2", "-(x = 5)"):
        result = riz.evaluate(bad)
        assert isinstance(result, Err), f"{bad!r} should be an error, got {result!r}"
        assert isinstance(result.error, RizTypeError)


def test_conditional():
    riz = Runtime()
    assert _rendered(riz.evaluate("if True: 1 else: 2")) == "1"
    assert _rendered(riz.evaluate("if False: 1 else: 2")) == "2"
    assert _rendered(riz.evaluate("if 1 < 2: 10 else: 20")) == "10"
    _ = riz.evaluate("x = 5")
    assert _rendered(riz.evaluate("if x < 10: x else: 0")) == "5"  # reads a binding
    # Nests; the inner `else` binds greedily.
    assert _rendered(riz.evaluate("if False: 1 else: if True: 2 else: 3")) == "2"
    # It's an expression — usable as a sub-expression and as a binding's value.
    assert _rendered(riz.evaluate("10 + if True: 1 else: 2")) == "11"
    _ = riz.evaluate("y = if True: 7 else: 8")
    assert _rendered(riz.evaluate("y")) == "7"
    # Branches meet under the coercion law — Int widens to Ratio, like arithmetic.
    assert _rendered(riz.evaluate("if True: 5/3 else: 7")) == "5/3"
    assert _rendered(riz.evaluate("if False: 5/3 else: 7")) == "7"
    assert _rendered(riz.evaluate("(if False: 5/3 else: 7) + 1/3")) == "22/3"


def test_conditional_is_lazy():
    riz = Runtime()
    # Only the taken branch evaluates, so the dead branch's div-by-zero is never
    # reached (both branches are Rational, to satisfy the same-type rule).
    assert _rendered(riz.evaluate("if True: 1/1 else: 1/0")) == "1"
    assert _rendered(riz.evaluate("if False: 1/0 else: 2/1")) == "2"


def test_conditional_type_errors():
    riz = Runtime()
    for bad in (
        "if 1: 2 else: 3",  # non-boolean condition
        "if True: 1 else: True",  # branches disagree: Int vs Bool, no widening
    ):
        result = riz.evaluate(bad)
        assert isinstance(result, Err), f"{bad!r} should be an error, got {result!r}"
        assert isinstance(result.error, RizTypeError)


def test_name_errors():
    riz = Runtime()
    # A name that was never bound is a name error, caught by the checker.
    for bad in ("foo", "true", "x + 1", "1 + y"):
        result = riz.evaluate(bad)
        assert isinstance(result, Err), f"{bad!r} should be an error, got {result!r}"
        assert isinstance(result.error, RizNameError)


def test_failed_binding_leaves_no_trace():
    riz = Runtime()
    # The right side fails to evaluate, so the binding must not commit: a later
    # reference to the name is still a name error, not a crash.
    result = riz.evaluate("x = 1/0")
    assert isinstance(result, Err)
    assert isinstance(result.error, RizDivisionByZeroError)
    after = riz.evaluate("x")
    assert isinstance(after, Err)
    assert isinstance(after.error, RizNameError)

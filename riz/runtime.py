"""The Riz runtime and its Python embedding boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from .boolean import Boolean
from .check import (
    FunctionType,
    ModuleType,
    OPTION,
    ProductType,
    ResultType,
    RizNameError,
    RizType,
    RizTypeError,
    RESULT,
    Type,
    TypeVariable,
    VariantType,
    check,
    check_call_type,
    types_compatible,
)
from .eval import (
    Closure,
    ModuleValue,
    NativeFunction,
    RizDivisionByZeroError,
    Value,
    call,
    eval,
    python_import_function,
)
from .integer import Integer
from .lex import IdentifierToken, lex
from .parse import RizParseError, parse
from .product import Product
from .variant import Failure, Nothing, Some, Success, VariantValue
from .ratio import Ratio
from .result import Err, Ok, Result
from .unit import Unit
from .string import String
from .python import PythonError, PythonValue


class Runtime:
    def __init__(self):
        # Bindings persist across calls (one REPL session). Two parallel envs:
        # the checker's name -> Type and the evaluator's name -> Value.
        self._modules: dict[str, ModuleValue] = {}
        self._types: dict[str, RizType] = {"use": ModuleType(())}
        self._values: dict[str, Value] = {"use": self._module_root()}
        python_import_type = FunctionType(
            ProductType((Type.STRING,)),
            ResultType(Type.PYTHON_VALUE, Type.PYTHON_ERROR),
        )
        registered = self.register_module(
            "python",
            ModuleType((("import", python_import_type),)),
            lambda runtime: Ok({"import": python_import_function()}),
        )
        assert isinstance(registered, Ok)

    def register_module(
        self,
        name: str,
        interface: ModuleType,
        loader: Callable[[Runtime], Result[Mapping[str, Value]]],
    ) -> Result[Unit]:
        """Register one typed root module with a lazy, cached loader."""
        if not _is_bindable_name(name) or not _is_module_interface(interface):
            return Err(RizTypeError())

        def load() -> Result[Mapping[str, Value]]:
            result = loader(self)
            if isinstance(result, Err):
                return result
            expected = dict(interface.members)
            if set(result.value) != set(expected):
                return Err(RizTypeError())
            for member, value in result.value.items():
                if not _matches_type(value, expected[member]):
                    return Err(RizTypeError())
            return result

        self._modules[name] = ModuleValue(name, interface, load)
        self._refresh_module_root()
        return Ok(Unit())

    def _module_root(self) -> ModuleValue:
        interface = ModuleType(
            tuple((name, module.interface) for name, module in self._modules.items())
        )
        return ModuleValue("use", interface, lambda: Ok(dict(self._modules)))

    def _refresh_module_root(self) -> None:
        root = self._module_root()
        self._types["use"] = root.interface
        self._values["use"] = root

    def define(self, name: str, value: Value) -> Result[Unit]:
        """Define a host-supplied Riz value in this interpreter.

        The value and its inferred Riz type enter the parallel environments
        together. Function values need an explicit signature and will be added
        by the native-function API rather than this value-only boundary.
        """
        if not _is_bindable_name(name):
            return Err(RizNameError())
        value_type = _type_of(value)
        if value_type is None:
            return Err(RizTypeError())
        self._types[name] = value_type
        self._values[name] = value
        return Ok(Unit())

    def lookup(self, name: str) -> Result[Value]:
        """Return a global Riz value, or a name error when it is unbound."""
        if name not in self._values:
            return Err(RizNameError())
        return Ok(self._values[name])

    def define_function(
        self,
        name: str,
        signature: FunctionType,
        callback: Callable[[Runtime, Product[Value]], Result[Value]],
    ) -> Result[Unit]:
        """Define a typed native function callable from Riz.

        Native callbacks use the same argument product and Result boundary as
        Riz itself. Their declared signature is checked on registration and on
        every returned value, keeping host code from violating Riz's type rules.
        """
        function = self.native_function(name, signature, callback)
        if isinstance(function, Err):
            return function
        self._types[name] = signature
        self._values[name] = function.value
        return Ok(Unit())

    def native_function(
        self,
        name: str,
        signature: FunctionType,
        callback: Callable[[Runtime, Product[Value]], Result[Value]],
    ) -> Result[NativeFunction]:
        """Create a checked native function value without globally binding it."""
        if not _is_bindable_name(name) or not _is_concrete_function(signature):
            return Err(RizTypeError())

        def invoke(arguments: Product[Value]) -> Result[Value]:
            result = callback(self, arguments)
            if isinstance(result, Err):
                return result
            if not _matches_type(result.value, signature.output):
                return Err(RizTypeError())
            return result

        return Ok(NativeFunction(name, signature, invoke))

    def load(self, extension: Extension) -> Result[Unit]:
        """Load an extension atomically into this interpreter."""
        types, values, modules = (
            dict(self._types),
            dict(self._values),
            dict(self._modules),
        )
        result = extension(self)
        if isinstance(result, Err):
            self._types, self._values, self._modules = types, values, modules
            return result
        return Ok(Unit())

    def call(self, function: Value, arguments: Product[Value]) -> Result[Value]:
        """Call a typed Riz or native function directly from the host."""
        if not isinstance(function, (Closure, NativeFunction)):
            return Err(RizTypeError())
        argument_type = _type_of(arguments)
        if not isinstance(argument_type, ProductType):
            return Err(RizTypeError())
        expected = check_call_type(function.signature, argument_type)
        if isinstance(expected, Err):
            return expected
        result = call(function, arguments)
        if isinstance(result, Err):
            return result
        if not _matches_type(result.value, expected.value):
            return Err(RizTypeError())
        return Ok(_specialize_callable(result.value, expected.value))

    def evaluate(self, source: str) -> Result[Value]:
        # Whole pipeline is Result-valued: no program error ever raises here.
        parsed = parse(lex(source))
        if isinstance(parsed, Err):
            return parsed
        # Check and evaluate against copies, committing both only if the whole
        # statement succeeds — a binding that fails partway leaves no trace.
        types = dict(self._types)
        functions: dict[int, FunctionType] = {}
        checked = check(parsed.value, types, functions)
        if isinstance(checked, Err):
            return checked
        values = dict(self._values)
        evaluated = eval(parsed.value, values, functions)
        if isinstance(evaluated, Err):
            return evaluated
        self._types = types
        self._values = values
        return evaluated


_RESERVED_NAMES = {
    "True",
    "False",
    "None",
    "Some",
    "Ok",
    "Err",
    "if",
    "else",
    "while",
    "fn",
    "match",
    "use",
}


def _is_bindable_name(name: str) -> bool:
    tokens = lex(name)
    return (
        len(tokens) == 1
        and isinstance(tokens[0], IdentifierToken)
        and tokens[0].name == name
        and name not in _RESERVED_NAMES
    )


def _type_of(value: Value) -> RizType | None:
    if isinstance(value, Integer):
        return Type.INTEGER
    if isinstance(value, Ratio):
        return Type.RATIONAL
    if isinstance(value, Boolean):
        return Type.BOOLEAN
    if isinstance(value, String):
        return Type.STRING
    if isinstance(value, Unit):
        return ProductType(())
    if isinstance(value, PythonValue):
        return Type.PYTHON_VALUE
    if isinstance(value, PythonError):
        return Type.PYTHON_ERROR
    if isinstance(value, Product):
        item_types: list[RizType] = []
        for item in value.items:
            item_type = _type_of(item)
            if item_type is None:
                return None
            item_types.append(item_type)
        return ProductType(tuple(item_types))
    if isinstance(value, VariantValue):
        definition = OPTION if value.type_name == "Option" else RESULT
        arguments: list[RizType] = [
            TypeVariable() for _ in range(definition.parameters)
        ]
        payload = dict(definition.constructors)[value.constructor]
        if payload is not None:
            assert value.value is not None
            payload_type = _type_of(value.value)
            if payload_type is None:
                return None
            arguments[payload] = payload_type
        return VariantType(definition, tuple(arguments))
    if isinstance(value, NativeFunction):
        return value.signature
    if isinstance(value, ModuleValue):
        return value.interface
    return value.signature  # the remaining Value variant is Closure


def _matches_type(value: Value, expected: RizType) -> bool:
    actual = _type_of(value)
    if actual is None:
        return False
    if isinstance(actual, ProductType) and isinstance(expected, ProductType):
        return len(actual.items) == len(expected.items) and all(
            _same_public_type(a, b) for a, b in zip(actual.items, expected.items)
        )
    return _same_public_type(actual, expected)


def _specialize_callable(value: Value, expected: RizType) -> Value:
    if not isinstance(value, Closure) or not isinstance(expected, FunctionType):
        return value
    specialized = Closure(
        value.name,
        expected,
        value.parameter,
        value.body,
        dict(value.env),
        value.functions,
    )
    if specialized.env.get(value.name) is value:
        specialized.env[value.name] = specialized
    return specialized


def _same_public_type(left: RizType, right: RizType) -> bool:
    if left is right:
        return True
    if isinstance(left, ProductType) and isinstance(right, ProductType):
        return len(left.items) == len(right.items) and all(
            _same_public_type(a, b) for a, b in zip(left.items, right.items)
        )
    if isinstance(left, ModuleType) and isinstance(right, ModuleType):
        return (
            tuple(name for name, _ in left.members)
            == tuple(name for name, _ in right.members)
            and all(
                _same_public_type(a, b)
                for (_, a), (_, b) in zip(left.members, right.members)
            )
        )
    if isinstance(left, VariantType) and isinstance(right, VariantType):
        return types_compatible(left, right)
    if isinstance(left, FunctionType) and isinstance(right, FunctionType):
        return types_compatible(left, right)
    return False


def _is_concrete_type(value: RizType) -> bool:
    if isinstance(value, Type):
        return True
    if isinstance(value, ProductType):
        return all(_is_concrete_type(item) for item in value.items)
    if isinstance(value, ModuleType):
        return _is_module_interface(value)
    if isinstance(value, VariantType):
        return all(_is_concrete_type(argument) for argument in value.arguments)
    if isinstance(value, FunctionType):
        return _is_concrete_function(value)
    return False


def _is_concrete_function(signature: FunctionType) -> bool:
    return (
        not signature.constraints
        and not signature.variables
        and _is_concrete_type(signature.input)
        and _is_concrete_type(signature.output)
    )


def _is_module_interface(interface: ModuleType) -> bool:
    names = tuple(name for name, _ in interface.members)
    return (
        len(names) == len(set(names))
        and all(_is_bindable_name(name) for name in names)
        and all(_is_concrete_type(member) for _, member in interface.members)
    )


type Extension = Callable[[Runtime], Result[Unit]]


def _rendered(result: Result[Value]) -> str:
    """Unwrap a successful result to its rendered value; fail the test otherwise."""
    match result:
        case Ok(value):
            return str(value)
        case Err(error):
            raise AssertionError(f"expected a value, got error: {error!r}")


def _import_python(runtime: Runtime) -> None:
    assert runtime.evaluate("{python} = use") == Ok(Unit())


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


def test_strings():
    riz = Runtime()
    assert riz.evaluate('"hello"') == Ok(String("hello"))
    assert riz.evaluate('"same" == "same"') == Ok(Boolean(True))
    assert riz.evaluate('"same" != "different"') == Ok(Boolean(True))
    assert isinstance(riz.evaluate('"one" + "two"'), Err)
    assert isinstance(riz.evaluate('"one" + 1'), Err)


def test_unit_is_the_empty_product():
    riz = Runtime()
    assert riz.evaluate("()") == Ok(Unit())
    assert riz.evaluate("() == ()") == Ok(Boolean(True))
    assert riz.evaluate("value = ()") == Ok(Unit())
    assert riz.lookup("value") == Ok(Unit())
    assert riz.evaluate("() = ()") == Ok(Unit())
    assert riz.define("host_empty", Product(())) == Ok(Unit())
    assert riz.evaluate("host_empty == ()") == Ok(Boolean(True))


def test_empty_product_is_a_regular_function_argument():
    riz = Runtime()
    assert riz.evaluate("fn identity(value): value") == Ok(Unit())
    assert riz.evaluate("identity(())") == Ok(Unit())
    assert riz.evaluate("fn empty(()): True") == Ok(Unit())
    assert riz.evaluate("empty(())") == Ok(Boolean(True))


def test_option_values():
    riz = Runtime()
    assert riz.evaluate("Some(42)") == Ok(Some(Integer(42)))
    assert riz.evaluate("None") == Ok(Nothing())


def test_option_match_is_exhaustive_and_destructures_some():
    riz = Runtime()
    source = "match Some(41):\n  Some(value): value + 1\n  None: 0"
    assert riz.evaluate(source) == Ok(Integer(42))
    source = "match None:\n  Some(value): value + 1\n  None: 0"
    assert riz.evaluate(source) == Ok(Integer(0))


def test_option_match_case_order_is_irrelevant():
    riz = Runtime()
    source = "match Some(42):\n  None: 0\n  Some(value): value"
    assert riz.evaluate(source) == Ok(Integer(42))


def test_option_match_bindings_are_case_local():
    riz = Runtime()
    source = "match Some(42):\n  Some(value): value\n  None: 0"
    assert riz.evaluate(source) == Ok(Integer(42))
    assert isinstance(riz.lookup("value"), Err)


def test_option_match_updates_preexisting_outer_bindings():
    riz = Runtime()
    source = (
        "answer = 0\n"
        "match Some(42):\n"
        "  Some(value): answer = value\n"
        "  None: answer = -1\n"
        "answer"
    )
    assert riz.evaluate(source) == Ok(Integer(42))
    assert isinstance(riz.lookup("value"), Err)


def test_option_match_updates_from_none_and_widens_outer_types():
    riz = Runtime()
    source = (
        "number = 1\n"
        "match None:\n"
        "  Some(value): number = value\n"
        "  None: number = number / 2\n"
        "number"
    )
    assert riz.evaluate(source) == Ok(Ratio(1, 2))


def test_option_pattern_shadowing_does_not_replace_outer_binding():
    riz = Runtime()
    source = (
        "value = 1\n"
        "match Some(42):\n"
        "  Some(value): value\n"
        "  None: 0\n"
        "value"
    )
    assert riz.evaluate(source) == Ok(Integer(1))


def test_option_match_requires_both_cases_and_compatible_results():
    riz = Runtime()
    invalid = (
        "match Some(1):\n  Some(value): value",
        "match Some(1):\n  Some(value): value\n  Some(other): other",
        "match Some(1):\n  Some(value): value\n  None: True",
        "match 1:\n  Some(value): value\n  None: 0",
    )
    for source in invalid:
        assert isinstance(riz.evaluate(source), Err)


def test_option_match_participates_in_function_inference():
    riz = Runtime()
    source = (
        "fn default(option, fallback):\n"
        "  match option:\n"
        "    Some(value): value\n"
        "    None: fallback"
    )
    assert riz.evaluate(source) == Ok(Unit())
    assert riz.evaluate("default(Some(42), 0)") == Ok(Integer(42))
    assert riz.evaluate("default(None, 7)") == Ok(Integer(7))
    assert isinstance(riz.evaluate("default(Some(True), 0)"), Err)


def test_result_values():
    riz = Runtime()
    assert riz.evaluate("Ok(42)") == Ok(Success(Integer(42)))
    assert riz.evaluate('Err("missing")') == Ok(Failure(String("missing")))
    assert _rendered(riz.evaluate("Ok(42)")) == "Ok(42)"
    assert _rendered(riz.evaluate('Err("missing")')) == 'Err("missing")'


def test_result_match_is_exhaustive_and_destructures_payloads():
    riz = Runtime()
    success = "match Ok(41):\n  Ok(value): value + 1\n  Err(error): 0"
    assert riz.evaluate(success) == Ok(Integer(42))
    failure = (
        'match Err((41, "missing")):\n'
        "  Ok(value): value\n"
        "  Err((code, message)): code + 1"
    )
    assert riz.evaluate(failure) == Ok(Integer(42))


def test_result_match_participates_in_function_inference():
    riz = Runtime()
    source = (
        "fn recover(result, fallback):\n"
        "  match result:\n"
        "    Ok(value): value\n"
        "    Err(error): fallback"
    )
    assert riz.evaluate(source) == Ok(Unit())
    assert riz.evaluate("recover(Ok(42), 0)") == Ok(Integer(42))
    assert riz.evaluate('recover(Err("missing"), 7)') == Ok(Integer(7))
    assert isinstance(riz.evaluate("recover(Ok(True), 0)"), Err)


def test_result_and_option_cases_cannot_be_mixed():
    riz = Runtime()
    invalid = (
        "match Ok(1):\n  Ok(value): value\n  None: 0",
        "match Ok(1):\n  Ok(value): value",
        'match Err("bad"):\n  Ok(value): value\n  Err: 0',
    )
    for source in invalid:
        assert isinstance(riz.evaluate(source), Err)


def test_result_match_preserves_outer_binding_rules():
    riz = Runtime()
    source = (
        "answer = 0\n"
        'match Err("missing"):\n'
        "  Ok(value): answer = value\n"
        "  Err(error): answer = 42\n"
        "answer"
    )
    assert riz.evaluate(source) == Ok(Integer(42))
    assert isinstance(riz.lookup("error"), Err)


def test_ratio_members():
    riz = Runtime()
    assert riz.evaluate("value = 6/4\nvalue.numerator") == Ok(Integer(3))
    assert riz.evaluate("value.denominator") == Ok(Integer(2))
    assert riz.evaluate("(6/4).numerator + 1") == Ok(Integer(4))
    assert riz.evaluate("fn half(): 1/2\nhalf().denominator") == Ok(Integer(2))


def test_named_structural_destructuring():
    riz = Runtime()
    assert riz.evaluate("{numerator, denominator} = 6/4") == Ok(Unit())
    assert riz.lookup("numerator") == Ok(Integer(3))
    assert riz.lookup("denominator") == Ok(Integer(2))


def test_named_destructuring_participates_in_function_inference():
    riz = Runtime()
    source = "fn numerator_of(value):\n  {numerator} = value\n  numerator"
    assert riz.evaluate(source) == Ok(Unit())
    assert riz.evaluate("numerator_of(10/4)") == Ok(Integer(5))
    rejected = riz.evaluate("numerator_of(1)")
    assert isinstance(rejected, Err)
    assert isinstance(rejected.error, RizTypeError)


def test_named_destructuring_evaluates_its_source_once():
    riz = Runtime()
    calls = 0
    signature = FunctionType(ProductType(()), Type.RATIONAL)

    def fraction(
        runtime: Runtime, arguments: Product[Value]
    ) -> Result[Value]:
        nonlocal calls
        del runtime, arguments
        calls += 1
        return Ok(Ratio(6, 4))

    assert riz.define_function("fraction", signature, fraction) == Ok(Unit())
    assert riz.evaluate("{numerator, denominator} = fraction()") == Ok(Unit())
    assert calls == 1
    assert riz.lookup("numerator") == Ok(Integer(3))
    assert riz.lookup("denominator") == Ok(Integer(2))


def test_invalid_named_destructuring_is_atomic():
    riz = Runtime()
    result = riz.evaluate("{numerator, missing} = 1/2")
    assert isinstance(result, Err)
    assert isinstance(result.error, RizTypeError)
    assert isinstance(riz.lookup("numerator"), Err)
    assert isinstance(riz.lookup("missing"), Err)


def test_named_destructuring_parse_errors():
    riz = Runtime()
    for source in ("{} = 1/2", "{numerator,} = 1/2", "{numerator, numerator} = 1/2", "{numerator}"):
        result = riz.evaluate(source)
        assert isinstance(result, Err)
        assert isinstance(result.error, RizParseError)


def _successful_python(result: Result[Value]) -> PythonValue:
    assert isinstance(result, Ok)
    assert isinstance(result.value, Success)
    assert isinstance(result.value.value, PythonValue)
    return result.value.value


def _failed_python(result: Result[Value]) -> PythonError:
    assert isinstance(result, Ok)
    assert isinstance(result.value, Failure)
    assert isinstance(result.value.value, PythonError)
    return result.value.value


def test_python_import_returns_language_results():
    riz = Runtime()
    _import_python(riz)
    math = _successful_python(riz.evaluate('python.import("math")'))
    assert isinstance(math, PythonValue)
    error = _failed_python(riz.evaluate('python.import("module_that_does_not_exist")'))
    assert str(error) == "<python error>"


def test_python_attribute_lookup_returns_language_results():
    class Attributes:
        answer: int = 42

    riz = Runtime()
    assert riz.define("owner", PythonValue(Attributes())) == Ok(Unit())
    answer = _successful_python(riz.evaluate('owner.attr("answer")'))
    assert answer.value == 42
    _ = _failed_python(riz.evaluate('owner.attr("missing")'))


def test_python_calls_return_language_results():
    def double(value: int) -> int:
        return value * 2

    riz = Runtime()
    assert riz.define("double", PythonValue(double)) == Ok(Unit())
    value = _successful_python(riz.evaluate("double(21)"))
    assert value.value == 42
    assert riz.define("not_callable", PythonValue(1)) == Ok(Unit())
    _ = _failed_python(riz.evaluate("not_callable()"))
    assert riz.define("raises", PythonValue(lambda: 1 / 0)) == Ok(Unit())
    _ = _failed_python(riz.evaluate("raises()"))


def test_python_operations_compose_through_explicit_result_matches():
    riz = Runtime()
    _import_python(riz)
    source = (
        'match python.import("math"):\n'
        "  Ok(math):\n"
        '    match math.attr("isqrt"):\n'
        "      Ok(isqrt):\n"
        "        match isqrt(1764):\n"
        "          Ok(value): value.integer()\n"
        "          Err(error): None\n"
        "      Err(error): None\n"
        "  Err(error): None"
    )
    assert riz.evaluate(source) == Ok(Some(Integer(42)))


def test_python_value_projections_are_options_and_strict():
    riz = Runtime()
    values = {
        "integer": PythonValue(42),
        "boolean": PythonValue(True),
        "string": PythonValue("riz"),
        "unit": PythonValue(None),
    }
    for name, value in values.items():
        assert riz.define(name, value) == Ok(Unit())
    assert riz.evaluate("integer.integer()") == Ok(Some(Integer(42)))
    assert riz.evaluate("boolean.boolean()") == Ok(Some(Boolean(True)))
    assert riz.evaluate("string.string()") == Ok(Some(String("riz")))
    assert riz.evaluate("unit.unit()") == Ok(Some(Unit()))
    assert riz.evaluate("string.integer()") == Ok(Nothing())


def test_python_calls_accept_only_unambiguous_python_arguments():
    riz = Runtime()
    assert riz.define("length", PythonValue(len)) == Ok(Unit())
    value = _successful_python(riz.evaluate('length("riz")'))
    assert value.value == 3
    assert isinstance(riz.evaluate("length(1/2)"), Err)
    assert isinstance(riz.evaluate("length(())"), Err)


def test_python_argument_constraint_is_inferred_in_functions():
    riz = Runtime()
    assert riz.define("python_string", PythonValue(str)) == Ok(Unit())
    assert riz.evaluate("fn stringify(value): python_string(value)") == Ok(Unit())
    for source in ("stringify(42)", "stringify(True)", 'stringify("hello")'):
        assert isinstance(_successful_python(riz.evaluate(source)), PythonValue)
    assert isinstance(riz.evaluate("stringify(1/2)"), Err)


def test_python_bridge_rendering_and_static_checks():
    riz = Runtime()
    assert isinstance(riz.evaluate("python"), Err)
    _import_python(riz)
    assert _rendered(riz.evaluate("python")) == "<module use.python>"
    assert _rendered(riz.evaluate("python.import")) == "<fn python.import>"
    assert isinstance(riz.evaluate("python.module"), Err)
    assert isinstance(riz.evaluate("python.missing"), Err)
    assert isinstance(riz.evaluate("python.import(1)"), Err)
    assert riz.define("value", PythonValue(1)) == Ok(Unit())
    assert isinstance(riz.evaluate("value.attr(1)"), Err)
    assert isinstance(riz.evaluate("value.integer(1)"), Err)


def test_ratio_member_type_inference_in_functions():
    riz = Runtime()
    assert riz.evaluate("fn numerator(value): value.numerator") == Ok(Unit())
    assert riz.evaluate("numerator(10/4)") == Ok(Integer(5))
    assert isinstance(riz.evaluate("numerator(1)"), Err)


def test_invalid_member_access():
    riz = Runtime()
    assert isinstance(riz.evaluate("(1/2).missing"), Err)
    assert isinstance(riz.evaluate("1.numerator"), Err)
    assert isinstance(riz.evaluate("(1/2)."), Err)


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
    for bad in ("(2+3", "2+3)"):  # mismatched parens are parse errors
        result = riz.evaluate(bad)
        assert isinstance(result, Err)
        assert isinstance(result.error, RizParseError)


def test_whitespace():
    riz = Runtime()
    assert _rendered(riz.evaluate("2 + 3")) == "5"
    assert _rendered(riz.evaluate("1/2  +  1/3 ")) == "5/6"  # internal/trailing ws
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
        "while True 5",  # while missing its colon
        "while True:",  # while missing its body
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


def test_while():
    riz = Runtime()
    _ = riz.evaluate("n = 1")
    # The body rebinds the loop counter in the enclosing scope, so it progresses.
    assert _rendered(riz.evaluate("while n < 100: n = n * 2")) == "()"  # loop is Unit
    assert _rendered(riz.evaluate("n")) == "128"
    # A loop whose condition starts false never runs and leaves state untouched.
    _ = riz.evaluate("m = 5")
    _ = riz.evaluate("while m > 10: m = m + 1")
    assert _rendered(riz.evaluate("m")) == "5"


def test_while_type_errors():
    riz = Runtime()
    result = riz.evaluate("while 1: 2")  # non-boolean condition
    assert isinstance(result, Err)
    assert isinstance(result.error, RizTypeError)


def test_while_widens_the_loop_variable_type():
    riz = Runtime()
    _ = riz.evaluate("n = 1")
    _ = riz.evaluate("while n > 1/100: n = n / 3")  # body rebinds n to Rational
    assert _rendered(riz.evaluate("n")) == "1/243"
    # The loop may have run, so n's type after is the join of Int (0 runs) and
    # Rational (≥1 run) = Rational. A bitwise op is now a clean type error, not
    # the host crash it used to be.
    result = riz.evaluate("n & 1")
    assert isinstance(result, Err)
    assert isinstance(result.error, RizTypeError)


def test_while_incompatible_rebind_is_a_type_error():
    riz = Runtime()
    _ = riz.evaluate("n = 5")
    # The body would change n from Int to Bool. The loop might not run, so n's
    # type can't be known at runtime — reject it rather than infer a union.
    result = riz.evaluate("while n > 0: n = True")
    assert isinstance(result, Err)
    assert isinstance(result.error, RizTypeError)


def test_sequencing():
    riz = Runtime()
    # A program can be several newline-separated statements; its value is the
    # last, and earlier bindings are visible to later statements.
    assert _rendered(riz.evaluate("x = 5\nx + 1")) == "6"
    assert _rendered(riz.evaluate("a = 2\nb = 3\na * b")) == "6"
    # Bindings from a multi-statement program persist into the session.
    assert _rendered(riz.evaluate("a")) == "2"
    assert _rendered(riz.evaluate("b")) == "3"


def test_conditional_merges_a_modified_variable():
    riz = Runtime()
    _ = riz.evaluate("n = 5")
    # Both branches rebind the pre-existing n; afterward it's the taken value,
    # typed as the join of the two paths (Int here).
    _ = riz.evaluate("if n > 0:\n  n = n + 1\nelse:\n  n = n - 1")
    assert _rendered(riz.evaluate("n")) == "6"


def test_conditional_merge_widens():
    riz = Runtime()
    _ = riz.evaluate("m = 6")
    # One branch makes m Rational, the other Int → the merge widens to Rational.
    _ = riz.evaluate("if m > 0:\n  m = m / 2\nelse:\n  m = m * 2")
    assert _rendered(riz.evaluate("m")) == "3"  # 6/2, a whole ratio


def test_conditional_new_binding_stays_local():
    riz = Runtime()
    _ = riz.evaluate("c = True")
    # `temp` is introduced inside the branches (both of them), but new bindings
    # don't escape — only pre-existing variables merge.
    _ = riz.evaluate("if c:\n  temp = 1\nelse:\n  temp = 2")
    after = riz.evaluate("temp")
    assert isinstance(after, Err)
    assert isinstance(after.error, RizNameError)


def test_conditional_incompatible_merge_is_a_type_error():
    riz = Runtime()
    _ = riz.evaluate("n = 5")
    # One branch makes n a Bool, the other keeps it Int — no join, so it can't
    # be known at runtime which: a type error.
    result = riz.evaluate("if n > 0:\n  n = True\nelse:\n  n = 0")
    assert isinstance(result, Err)
    assert isinstance(result.error, RizTypeError)


def test_while_with_block_body():
    riz = Runtime()
    # The accumulator loop: a multi-statement body updates two variables per
    # iteration (impossible with a single-expression body).
    program = "i = 1\nsum = 0\nwhile i <= 5:\n  sum = sum + i\n  i = i + 1\nsum"
    assert _rendered(riz.evaluate(program)) == "15"


def test_if_with_block_body():
    riz = Runtime()
    # A block branch evaluates to its last statement's value.
    program = "x = 5\nif x > 0:\n  y = 1\n  y + 10\nelse:\n  0"
    assert _rendered(riz.evaluate(program)) == "11"


def test_missing_block_body_is_an_error():
    riz = Runtime()
    # `while …:` then a newline with no indent — the block never opens.
    result = riz.evaluate("x = 1\nwhile x > 5:\ny")
    assert isinstance(result, Err)
    assert isinstance(result.error, RizParseError)


def test_unexpected_indent_is_a_parse_error():
    riz = Runtime()
    # Top level is column 0; a line that starts indented is an unexpected indent.
    result = riz.evaluate("  5")
    assert isinstance(result, Err)
    assert isinstance(result.error, RizParseError)


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


def test_function_definition_and_call():
    riz = Runtime()
    assert _rendered(riz.evaluate("fn square(n): n * n")) == "()"  # a def is Unit
    assert _rendered(riz.evaluate("square(5)")) == "25"
    assert _rendered(riz.evaluate("square(4) + 1")) == "17"  # a call composes
    assert _rendered(riz.evaluate("1 + square(square(2))")) == "17"  # 1 + 16, nested


def test_function_with_a_block_body():
    riz = Runtime()
    assert _rendered(riz.evaluate("fn double(n):\n  n + n")) == "()"
    assert _rendered(riz.evaluate("double(21)")) == "42"


def test_an_inferred_function_type_is_reused_at_calls():
    riz = Runtime()
    # The definition infers a numeric input and Rational output once. Calls
    # instantiate that stored relationship; they do not re-check the body.
    _ = riz.evaluate("fn half(n): n / 2")
    assert _rendered(riz.evaluate("half(5)")) == "5/2"
    assert _rendered(riz.evaluate("half(6)")) == "3"  # 6/2, a whole ratio


def test_a_bare_function_renders_as_itself():
    riz = Runtime()
    _ = riz.evaluate("fn square(n): n * n")
    assert _rendered(riz.evaluate("square")) == "<fn square>"


def test_closures_capture_free_variables_by_value():
    riz = Runtime()
    _ = riz.evaluate("k = 10")
    _ = riz.evaluate("fn addk(n): n + k")  # captures k = 10 by value
    _ = riz.evaluate("k = 99")  # rebinding k afterward can't reach the closure
    assert _rendered(riz.evaluate("addk(5)")) == "15"


def test_calling_a_non_function_is_a_type_error():
    riz = Runtime()
    for bad in ("5(3)", "(1 + 2)(3)", "True(1)"):
        result = riz.evaluate(bad)
        assert isinstance(result, Err), f"{bad!r} should be an error, got {result!r}"
        assert isinstance(result.error, RizTypeError)


def test_a_function_body_is_checked_at_its_definition():
    riz = Runtime()
    result = riz.evaluate("fn bad(): True + 1")
    assert isinstance(result, Err)
    assert isinstance(result.error, RizTypeError)
    # A failed definition never enters either persistent environment.
    after = riz.evaluate("bad")
    assert isinstance(after, Err)
    assert isinstance(after.error, RizNameError)


def test_inferred_generic_functions_are_instantiated_per_call():
    riz = Runtime()
    _ = riz.evaluate("fn identity(value): value")
    assert _rendered(riz.evaluate("identity(42)")) == "42"
    assert _rendered(riz.evaluate("identity(True)")) == "True"
    assert _rendered(riz.evaluate("identity((1, 2))")) == "(1, 2)"

    _ = riz.evaluate("fn double(value): value + value")
    assert _rendered(riz.evaluate("double(21)")) == "42"
    assert _rendered(riz.evaluate("double(1 / 4)")) == "1/2"
    wrong = riz.evaluate("double(True)")
    assert isinstance(wrong, Err)
    assert isinstance(wrong.error, RizTypeError)


def test_higher_order_function_type_is_inferred_at_definition():
    riz = Runtime()
    _ = riz.evaluate("fn apply(function, value): function(value)")
    _ = riz.evaluate("fn identity(value): value")
    assert _rendered(riz.evaluate("apply(identity, True)")) == "True"
    _ = riz.evaluate("fn increment(value): value + 1")
    assert _rendered(riz.evaluate("apply(increment, 41)")) == "42"
    _ = riz.evaluate("fn invert(value): !value")
    assert _rendered(riz.evaluate("apply(invert, True)")) == "False"


def test_self_recursion():
    riz = Runtime()
    # The classic: factorial calls itself. The return type is seeded from the
    # base case (Integer) and the recursive branch is checked against it.
    _ = riz.evaluate("fn factorial(n): if n <= 1: 1 else: n * factorial(n - 1)")
    assert _rendered(riz.evaluate("factorial(0)")) == "1"
    assert _rendered(riz.evaluate("factorial(1)")) == "1"
    assert _rendered(riz.evaluate("factorial(5)")) == "120"
    assert _rendered(riz.evaluate("factorial(6)")) == "720"


def test_recursion_whose_result_widens():
    riz = Runtime()
    # The base case is Integer but the recursive branch divides, so the whole
    # function's return type widens to Rational — the fixpoint must catch that.
    _ = riz.evaluate("fn shrink(n): if n <= 0: 1 else: shrink(n - 1) / 2")
    assert _rendered(riz.evaluate("shrink(0)")) == "1"
    assert _rendered(riz.evaluate("shrink(3)")) == "1/8"  # 1/2/2/2


def test_recursion_with_no_base_case_is_a_type_error():
    riz = Runtime()
    # Every path recurses, so the return type stays ⊥ — the function can never
    # return. The checker rejects it instead of letting eval spin forever.
    _ = riz.evaluate("fn loop(n): loop(n)")
    result = riz.evaluate("loop(5)")
    assert isinstance(result, Err)
    assert isinstance(result.error, RizTypeError)


def test_multi_parameter_function():
    riz = Runtime()
    _ = riz.evaluate("fn sumsq(a, b): a * a + b * b")
    assert _rendered(riz.evaluate("sumsq(3, 4)")) == "25"
    assert _rendered(riz.evaluate("sumsq(1, 1)")) == "2"
    # Arguments bind positionally; order matters.
    _ = riz.evaluate("fn diff(a, b): a - b")
    assert _rendered(riz.evaluate("diff(10, 3)")) == "7"
    assert _rendered(riz.evaluate("diff(3, 10)")) == "-7"


def test_multi_parameter_recursion():
    riz = Runtime()
    _ = riz.evaluate("fn power(base, exp): if exp <= 0: 1 else: base * power(base, exp - 1)")
    assert _rendered(riz.evaluate("power(2, 10)")) == "1024"
    assert _rendered(riz.evaluate("power(3, 4)")) == "81"
    # gcd by subtraction — two distinct recursive calls, both two-argument.
    _ = riz.evaluate(
        "fn gcd(a, b): if a == b: a else: if a > b: gcd(a - b, b) else: gcd(a, b - a)"
    )
    assert _rendered(riz.evaluate("gcd(12, 8)")) == "4"
    assert _rendered(riz.evaluate("gcd(21, 14)")) == "7"


def test_argument_arity_must_match():
    riz = Runtime()
    _ = riz.evaluate("fn add(a, b): a + b")
    for bad in ("add(3)", "add(1, 2, 3)"):  # too few, too many
        result = riz.evaluate(bad)
        assert isinstance(result, Err), f"{bad!r} should be an error, got {result!r}"
        assert isinstance(result.error, RizTypeError)


def test_snake_case_names():
    riz = Runtime()
    _ = riz.evaluate("fn add_one(n): n + 1")
    assert _rendered(riz.evaluate("add_one(41)")) == "42"
    _ = riz.evaluate("my_total = 6 * 7")
    assert _rendered(riz.evaluate("my_total + 1")) == "43"


def test_zero_parameter_function():
    riz = Runtime()
    _ = riz.evaluate("fn answer(): 6 * 7")
    assert _rendered(riz.evaluate("answer()")) == "42"
    # The function value and calling it are different things.
    assert _rendered(riz.evaluate("answer")) == "<fn answer>"
    assert _rendered(riz.evaluate("answer() + 1")) == "43"


def test_zero_parameter_function_captures_by_value():
    riz = Runtime()
    _ = riz.evaluate("k = 100")
    _ = riz.evaluate("fn get_k(): k + 1")  # captures k = 100
    _ = riz.evaluate("k = 0")  # a later rebind can't reach the closure
    assert _rendered(riz.evaluate("get_k()")) == "101"


def test_product_value_and_destructuring():
    riz = Runtime()
    _ = riz.evaluate("pair = (20, 22)")
    assert _rendered(riz.evaluate("pair")) == "(20, 22)"
    assert _rendered(riz.evaluate("(x, y) = pair")) == "()"
    assert _rendered(riz.evaluate("x + y")) == "42"


def test_nested_product_destructuring():
    riz = Runtime()
    _ = riz.evaluate("((a, b), c) = ((1, 2), 3)")
    assert _rendered(riz.evaluate("a + b + c")) == "6"


def test_product_pattern_in_function_parameter():
    riz = Runtime()
    _ = riz.evaluate("fn add_pair((x, y)): x + y")
    assert _rendered(riz.evaluate("add_pair((20, 22))")) == "42"


def test_product_pattern_shape_must_match():
    riz = Runtime()
    _ = riz.evaluate("fn first((x, y)): x")
    for bad in ("first(1)", "first((1, 2, 3))"):
        result = riz.evaluate(bad)
        assert isinstance(result, Err)
        assert isinstance(result.error, RizTypeError)

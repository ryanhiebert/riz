"""Evaluator: walk the syntax tree to a value, or an error that escaped."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import importlib
from typing import cast, override

from .boolean import Boolean
from .integer import Integer
from .check import (
    FunctionType,
    ModuleType,
    OptionType,
    ProductType,
    ResultType,
    RizTypeError,
    Type,
)
from .parse import (
    Add,
    And,
    Bind,
    Binding,
    Block,
    BoolLiteral,
    Call,
    Conditional,
    Divide,
    Equal,
    Expr,
    Function,
    GreaterOrEqual,
    GreaterThan,
    IntLiteral,
    LessOrEqual,
    LessThan,
    Match,
    Member,
    NamedPattern,
    Multiply,
    Negate,
    Not,
    NotEqual,
    Or,
    Pattern,
    ProductLiteral,
    ProductPattern,
    StringLiteral,
    Subtract,
    Use,
    Variable,
    VariantLiteral,
    WhileLoop,
)
from .ratio import Ratio
from .product import Product
from .result import Err, Ok, Result
from .unit import Unit
from .string import String
from .python import PythonError, PythonValue
from .variant import Failure, Nothing, Some, Success, VariantValue


# A function value: its parameters, its body, and a *value-captured* snapshot of
# the environment at definition (a copy, so a later rebind of a free name can't
# reach in). Identity equality (eq=False) — functions aren't compared by value.
@dataclass(frozen=True, eq=False)
class Closure:
    name: str
    signature: FunctionType
    parameter: ProductPattern
    body: Expr
    env: dict[str, Value]
    functions: dict[int, FunctionType]

    @override
    def __str__(self) -> str:
        return f"<fn {self.name}>"


@dataclass(frozen=True, eq=False)
class NativeFunction:
    name: str
    signature: FunctionType
    callback: Callable[[Product[Value]], Result[Value]]

    @override
    def __str__(self) -> str:
        return f"<fn {self.name}>"


@dataclass(eq=False)
class ModuleValue:
    name: str
    interface: ModuleType
    loader: Callable[[], Result[Mapping[str, Value]]]
    loaded: dict[str, Value] | None = None
    error: object | None = None
    projections: dict[str, ModuleValue] = field(default_factory=dict)

    @override
    def __str__(self) -> str:
        return f"<module {self.name}>"


type Value = Integer | Ratio | Boolean | String | Unit | PythonValue | PythonError | VariantValue[Value] | Product[Value] | Closure | NativeFunction | ModuleValue
type Numeric = Integer | Ratio


@dataclass(frozen=True)
class RizDivisionByZeroError: ...


def _variant_value(constructor: str, value: Value | None) -> VariantValue[Value]:
    if constructor == "None":
        return Nothing()
    assert value is not None
    if constructor == "Some":
        return Some(value)
    if constructor == "Ok":
        return Success(value)
    if constructor == "Err":
        return Failure(value)
    raise AssertionError("type checker should reject unknown constructors")


def eval(
    node: Expr,
    env: dict[str, Value],
    functions: dict[int, FunctionType] | None = None,
) -> Result[Value]:
    functions = {} if functions is None else functions
    match node:
        case Binding(target, value):
            evaluated = eval(value, env, functions)
            if isinstance(evaluated, Err):
                return evaluated  # a failed binding leaves the name untouched
            bound = _bind_pattern(target, evaluated.value, env)
            if isinstance(bound, Err):
                return bound
            return Ok(Unit())
        case Variable(name):
            if name not in env:
                raise AssertionError("type checker should reject unbound names")
            return Ok(env[name])
        case Use():
            return Ok(env["use"])
        case Member(value, name):
            evaluated = eval(value, env, functions)
            if isinstance(evaluated, Err):
                return evaluated
            return _member(evaluated.value, name)
        case VariantLiteral(constructor, value):
            if value is None:
                return Ok(_variant_value(constructor, None))
            evaluated = eval(value, env, functions)
            return (
                evaluated
                if isinstance(evaluated, Err)
                else Ok(_variant_value(constructor, evaluated.value))
            )
        case Match(value, cases):
            evaluated = eval(value, env, functions)
            if isinstance(evaluated, Err):
                return evaluated
            assert isinstance(evaluated.value, VariantValue)
            selected = next(
                case for case in cases if case.constructor == evaluated.value.constructor
            )
            frame = dict(env)
            pattern_names: set[str] = set()
            if selected.pattern is not None:
                assert evaluated.value.value is not None
                bound = _bind_pattern(selected.pattern, evaluated.value.value, frame)
                if isinstance(bound, Err):
                    return bound
                pattern_names = _pattern_names(selected.pattern)
            result = eval(selected.body, frame, functions)
            if isinstance(result, Err):
                return result
            env.update((name, frame[name]) for name in env if name not in pattern_names)
            return result
        case Function(name, parameter, body):
            # Capture the env by value (a copy), then tie the knot: bind the
            # function's own name to the closure *inside* its captured env, so the
            # body can call itself (self-recursion). The self-reference is to the
            # closure value, not the outer slot, so a later rebind of the name
            # can't change it — value-capture intact.
            signature = functions.get(id(node))
            if signature is None:
                raise AssertionError("type checker should type every function")
            closure = Closure(name, signature, parameter, body, dict(env), functions)
            closure.env[name] = closure
            env[name] = closure
            return Ok(Unit())
        case Call(callee, arguments):
            evaluated = eval(callee, env, functions)
            if isinstance(evaluated, Err):
                return evaluated
            function = evaluated.value
            if not isinstance(function, (Closure, NativeFunction, PythonValue)):
                raise AssertionError("type checker should reject calling a non-function")
            values: list[Value] = []
            for argument in arguments:
                evaluated_argument = eval(argument, env, functions)
                if isinstance(evaluated_argument, Err):
                    return evaluated_argument
                values.append(evaluated_argument.value)
            argument = Product(tuple(values))
            if isinstance(function, PythonValue):
                return _call_python(function, argument)
            return call(function, argument)
        case Conditional(condition, consequent, alternative):
            evaluated = eval(condition, env, functions)
            if isinstance(evaluated, Err):
                return evaluated
            # Lazy: only the taken branch runs (so the dead branch's errors, like
            # div-by-zero, never fire), in the shared env so its changes to
            # pre-existing variables persist (new branch vars are type-gated out).
            branch = consequent if _truth(evaluated.value) else alternative
            return eval(branch, env, functions)
        case WhileLoop(condition, body):
            # The body runs in the shared env, so a rebind like `n = n * 2`
            # persists and the next condition check sees it (loop progresses).
            while True:
                tested = eval(condition, env, functions)
                if isinstance(tested, Err):
                    return tested
                if not _truth(tested.value):
                    return Ok(Unit())
                ran = eval(body, env, functions)
                if isinstance(ran, Err):
                    return ran
        case Block(statements):
            # Statements run in order, sharing env so a binding is visible to
            # later statements; the block's value is its last statement's.
            result = eval(statements[0], env, functions)
            for statement in statements[1:]:
                if isinstance(result, Err):
                    return result
                result = eval(statement, env, functions)
            return result
        case IntLiteral(value):
            return Ok(Integer(value))
        case BoolLiteral(value):
            return Ok(Boolean(value))
        case StringLiteral(value):
            return Ok(String(value))
        case ProductLiteral(items):
            if not items:
                return Ok(Unit())
            product_values: list[Value] = []
            for item in items:
                evaluated = eval(item, env, functions)
                if isinstance(evaluated, Err):
                    return evaluated
                product_values.append(evaluated.value)
            return Ok(Product(tuple(product_values)))
        case Negate(operand):
            return _unary(eval(operand, env, functions), _negate)
        case Add(left, right):
            return _binary(eval(left, env, functions), eval(right, env, functions), _add)
        case Subtract(left, right):
            return _binary(eval(left, env, functions), eval(right, env, functions), _subtract)
        case Multiply(left, right):
            return _binary(eval(left, env, functions), eval(right, env, functions), _multiply)
        case Divide(left, right):
            return _binary(eval(left, env, functions), eval(right, env, functions), _divide)
        case LessThan(left, right):
            return _binary(eval(left, env, functions), eval(right, env, functions), _less_than)
        case GreaterThan(left, right):
            return _binary(eval(left, env, functions), eval(right, env, functions), _greater_than)
        case LessOrEqual(left, right):
            return _binary(eval(left, env, functions), eval(right, env, functions), _less_or_equal)
        case GreaterOrEqual(left, right):
            return _binary(eval(left, env, functions), eval(right, env, functions), _greater_or_equal)
        case Equal(left, right):
            return _binary_value(eval(left, env, functions), eval(right, env, functions), _equal)
        case NotEqual(left, right):
            return _binary_value(eval(left, env, functions), eval(right, env, functions), _not_equal)
        case And(left, right):
            return _binary_value(eval(left, env, functions), eval(right, env, functions), _and)
        case Or(left, right):
            return _binary_value(eval(left, env, functions), eval(right, env, functions), _or)
        case Not(operand):
            return _unary_value(eval(operand, env, functions), _logical_not)


def call(function: Closure | NativeFunction, argument: Product[Value]) -> Result[Value]:
    if isinstance(function, NativeFunction):
        return function.callback(argument)
    frame = dict(function.env)
    bound = _bind_pattern(function.parameter, argument, frame)
    if isinstance(bound, Err):
        return bound
    return eval(function.body, frame, function.functions)


def python_import_function() -> NativeFunction:
    signature = FunctionType(
        ProductType((Type.STRING,)),
        ResultType(Type.PYTHON_VALUE, Type.PYTHON_ERROR),
    )

    def invoke(arguments: Product[Value]) -> Result[Value]:
        (name,) = arguments.items
        assert isinstance(name, String)
        try:
            return Ok(Success(PythonValue(importlib.import_module(name.value))))
        except Exception as error:
            return Ok(Failure(PythonError(error)))

    return NativeFunction("python.import", signature, invoke)


def _python_attr_function(owner: PythonValue) -> NativeFunction:
    signature = FunctionType(
        ProductType((Type.STRING,)),
        ResultType(Type.PYTHON_VALUE, Type.PYTHON_ERROR),
    )

    def invoke(arguments: Product[Value]) -> Result[Value]:
        (name,) = arguments.items
        assert isinstance(name, String)
        try:
            return Ok(Success(PythonValue(cast(object, getattr(owner.value, name.value)))))
        except Exception as error:
            return Ok(Failure(PythonError(error)))

    return NativeFunction("PythonValue.attr", signature, invoke)


def _python_integer_function(owner: PythonValue) -> NativeFunction:
    signature = FunctionType(ProductType(()), OptionType(Type.INTEGER))

    def invoke(arguments: Product[Value]) -> Result[Value]:
        assert not arguments.items
        if type(owner.value) is not int:
            return Ok(Nothing())
        return Ok(Some(Integer(owner.value)))

    return NativeFunction("PythonValue.integer", signature, invoke)


def _python_boolean_function(owner: PythonValue) -> NativeFunction:
    signature = FunctionType(ProductType(()), OptionType(Type.BOOLEAN))

    def invoke(arguments: Product[Value]) -> Result[Value]:
        assert not arguments.items
        if type(owner.value) is not bool:
            return Ok(Nothing())
        return Ok(Some(Boolean(owner.value)))

    return NativeFunction("PythonValue.boolean", signature, invoke)


def _python_string_function(owner: PythonValue) -> NativeFunction:
    signature = FunctionType(ProductType(()), OptionType(Type.STRING))

    def invoke(arguments: Product[Value]) -> Result[Value]:
        assert not arguments.items
        if type(owner.value) is not str:
            return Ok(Nothing())
        return Ok(Some(String(owner.value)))

    return NativeFunction("PythonValue.string", signature, invoke)


def _python_unit_function(owner: PythonValue) -> NativeFunction:
    signature = FunctionType(ProductType(()), OptionType(ProductType(())))

    def invoke(arguments: Product[Value]) -> Result[Value]:
        assert not arguments.items
        if owner.value is not None:
            return Ok(Nothing())
        return Ok(Some(Unit()))

    return NativeFunction("PythonValue.unit", signature, invoke)


def _call_python(function: PythonValue, arguments: Product[Value]) -> Result[Value]:
    try:
        converted = tuple(_to_python(argument) for argument in arguments.items)
        if not callable(function.value):
            return Ok(Failure(PythonError(TypeError("Python value is not callable"))))
        return Ok(Success(PythonValue(function.value(*converted))))
    except Exception as error:
        return Ok(Failure(PythonError(error)))


def _to_python(value: Value) -> object:
    if isinstance(value, Integer):
        return value.value
    if isinstance(value, Boolean):
        return value.value
    if isinstance(value, String):
        return value.value
    if isinstance(value, PythonValue):
        return value.value
    raise AssertionError("type checker should reject this Python argument")


def _bind_pattern(pattern: Pattern, value: Value, env: dict[str, Value]) -> Result[None]:
    match pattern:
        case Bind(name):
            env[name] = value
            return Ok(None)
        case ProductPattern(items):
            if not items and isinstance(value, Unit):
                return Ok(None)
            if not isinstance(value, Product) or len(items) != len(value.items):
                return Err(RizTypeError())
            for item, item_value in zip(items, value.items):
                bound = _bind_pattern(item, item_value, env)
                if isinstance(bound, Err):
                    return bound
            return Ok(None)
        case NamedPattern(names):
            members: list[tuple[str, Value]] = []
            for name in names:
                member = _member(value, name)
                if isinstance(member, Err):
                    return member
                members.append((name, member.value))
            env.update(members)
            return Ok(None)


def _pattern_names(pattern: Pattern) -> set[str]:
    match pattern:
        case Bind(name):
            return {name}
        case ProductPattern(items):
            collected: set[str] = set()
            for item in items:
                collected.update(_pattern_names(item))
            return collected
        case NamedPattern(names):
            return set(names)


def _member(owner: Value, name: str) -> Result[Value]:
    if isinstance(owner, ModuleValue):
        member_type = dict(owner.interface.members)[name]
        if isinstance(member_type, ModuleType):
            if name not in owner.projections:
                def load_projection() -> Result[Mapping[str, Value]]:
                    loaded = _load_module(owner)
                    if isinstance(loaded, Err):
                        return loaded
                    child = loaded.value[name]
                    if not isinstance(child, ModuleValue):
                        return Err(RizTypeError())
                    return _load_module(child)

                owner.projections[name] = ModuleValue(
                    f"{owner.name}.{name}", member_type, load_projection
                )
            return Ok(owner.projections[name])
        loaded = _load_module(owner)
        if isinstance(loaded, Err):
            return loaded
        return Ok(loaded.value[name])
    if isinstance(owner, Ratio):
        if name == "numerator":
            return Ok(Integer(owner.numerator))
        if name == "denominator":
            return Ok(Integer(owner.denominator))
    if isinstance(owner, PythonValue) and name == "attr":
        return Ok(_python_attr_function(owner))
    if isinstance(owner, PythonValue) and name == "integer":
        return Ok(_python_integer_function(owner))
    if isinstance(owner, PythonValue) and name == "boolean":
        return Ok(_python_boolean_function(owner))
    if isinstance(owner, PythonValue) and name == "string":
        return Ok(_python_string_function(owner))
    if isinstance(owner, PythonValue) and name == "unit":
        return Ok(_python_unit_function(owner))
    raise AssertionError("type checker should reject unknown members")


def _load_module(module: ModuleValue) -> Result[dict[str, Value]]:
    if module.loaded is not None:
        return Ok(module.loaded)
    if module.error is not None:
        return Err(module.error)
    loaded = module.loader()
    if isinstance(loaded, Err):
        module.error = loaded.error
        return loaded
    module.loaded = dict(loaded.value)
    return Ok(module.loaded)


def _unary(
    operand: Result[Value], op: Callable[[Numeric], Result[Value]]
) -> Result[Value]:
    if isinstance(operand, Err):
        return operand
    return op(_number(operand.value))


def _binary(
    left: Result[Value],
    right: Result[Value],
    op: Callable[[Numeric, Numeric], Result[Value]],
) -> Result[Value]:
    if isinstance(left, Err):
        return left
    if isinstance(right, Err):
        return right
    return op(_number(left.value), _number(right.value))


def _binary_value(
    left: Result[Value],
    right: Result[Value],
    op: Callable[[Value, Value], Result[Value]],
) -> Result[Value]:
    # Like _binary, but passes full values (equality also applies to booleans).
    if isinstance(left, Err):
        return left
    if isinstance(right, Err):
        return right
    return op(left.value, right.value)


def _unary_value(
    operand: Result[Value], op: Callable[[Value], Result[Value]]
) -> Result[Value]:
    if isinstance(operand, Err):
        return operand
    return op(operand.value)


def _number(value: Value) -> Numeric:
    # The type checker rejects non-numbers in arithmetic before eval runs, so one
    # reaching here is a checker bug, not a user error — hence a hard failure.
    if isinstance(value, (Integer, Ratio)):
        return value
    raise AssertionError("type checker should reject non-numbers in arithmetic")


def _negate(value: Numeric) -> Result[Value]:
    if isinstance(value, Integer):
        return Ok(Integer(-value.value))
    return Ok(Ratio(-value.numerator, value.denominator))


def _add(left: Numeric, right: Numeric) -> Result[Value]:
    if isinstance(left, Integer) and isinstance(right, Integer):
        return Ok(Integer(left.value + right.value))
    a, b = _widen(left), _widen(right)
    return Ok(
        Ratio(
            a.numerator * b.denominator + b.numerator * a.denominator,
            a.denominator * b.denominator,
        )
    )


def _subtract(left: Numeric, right: Numeric) -> Result[Value]:
    if isinstance(left, Integer) and isinstance(right, Integer):
        return Ok(Integer(left.value - right.value))
    a, b = _widen(left), _widen(right)
    return Ok(
        Ratio(
            a.numerator * b.denominator - b.numerator * a.denominator,
            a.denominator * b.denominator,
        )
    )


def _multiply(left: Numeric, right: Numeric) -> Result[Value]:
    if isinstance(left, Integer) and isinstance(right, Integer):
        return Ok(Integer(left.value * right.value))
    a, b = _widen(left), _widen(right)
    return Ok(Ratio(a.numerator * b.numerator, a.denominator * b.denominator))


def _divide(left: Numeric, right: Numeric) -> Result[Value]:
    a, b = _widen(left), _widen(right)
    if b.numerator == 0:
        return Err(RizDivisionByZeroError())
    return Ok(Ratio(a.numerator * b.denominator, a.denominator * b.numerator))


def _ordering(left: Numeric, right: Numeric) -> tuple[int, int]:
    # Compare as fractions by cross-multiplying; denominators are positive, so
    # the inequality direction is preserved.
    a, b = _widen(left), _widen(right)
    return a.numerator * b.denominator, b.numerator * a.denominator


def _less_than(left: Numeric, right: Numeric) -> Result[Value]:
    lhs, rhs = _ordering(left, right)
    return Ok(Boolean(lhs < rhs))


def _greater_than(left: Numeric, right: Numeric) -> Result[Value]:
    lhs, rhs = _ordering(left, right)
    return Ok(Boolean(lhs > rhs))


def _less_or_equal(left: Numeric, right: Numeric) -> Result[Value]:
    lhs, rhs = _ordering(left, right)
    return Ok(Boolean(lhs <= rhs))


def _greater_or_equal(left: Numeric, right: Numeric) -> Result[Value]:
    lhs, rhs = _ordering(left, right)
    return Ok(Boolean(lhs >= rhs))


def _equal(left: Value, right: Value) -> Result[Value]:
    return Ok(Boolean(_equals(left, right)))


def _not_equal(left: Value, right: Value) -> Result[Value]:
    return Ok(Boolean(not _equals(left, right)))


def _equals(left: Value, right: Value) -> bool:
    if _is_unit(left) and _is_unit(right):
        return True
    if isinstance(left, String) and isinstance(right, String):
        return left.value == right.value
    if isinstance(left, Boolean) and isinstance(right, Boolean):
        return left.value == right.value
    if isinstance(left, Boolean) or isinstance(right, Boolean):
        raise AssertionError("type checker should reject == across number and boolean")
    # both numeric: equal iff equal as fractions
    a, b = _widen(_number(left)), _widen(_number(right))
    return a.numerator * b.denominator == b.numerator * a.denominator


def _is_unit(value: Value) -> bool:
    return isinstance(value, Unit) or (
        isinstance(value, Product) and not value.items
    )


def _and(left: Value, right: Value) -> Result[Value]:
    # Eager (no short-circuit). Logical on booleans, bitwise on integers.
    if isinstance(left, Boolean) and isinstance(right, Boolean):
        return Ok(Boolean(left.value and right.value))
    if isinstance(left, Integer) and isinstance(right, Integer):
        return Ok(Integer(left.value & right.value))
    raise AssertionError("type checker should reject & on these operand types")


def _or(left: Value, right: Value) -> Result[Value]:
    if isinstance(left, Boolean) and isinstance(right, Boolean):
        return Ok(Boolean(left.value or right.value))
    if isinstance(left, Integer) and isinstance(right, Integer):
        return Ok(Integer(left.value | right.value))
    raise AssertionError("type checker should reject | on these operand types")


def _logical_not(value: Value) -> Result[Value]:
    return Ok(Boolean(not _truth(value)))


def _truth(value: Value) -> bool:
    # The type checker guarantees &&/||/! operands are boolean; a non-boolean
    # here is a checker bug, not a user error.
    if isinstance(value, Boolean):
        return value.value
    raise AssertionError("type checker should reject non-boolean in &&/||/!")


def _widen(value: Numeric) -> Ratio:
    if isinstance(value, Integer):
        return Ratio(value.value, 1)
    return value

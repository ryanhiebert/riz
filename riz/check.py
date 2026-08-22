"""Definition-site type inference for Riz.

Functions are checked once where defined. Their stored type contains an input
product, an output, and polymorphic operator constraints. Calls instantiate
that type and never revisit the function body.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from .parse import (
    Add, And, Bind, Binding, Block, BoolLiteral, Call, Conditional, Divide,
    Equal, Expr, Function, GreaterOrEqual, GreaterThan, IntLiteral, LessOrEqual,
    LessThan, Multiply, Negate, Not, NotEqual, Or, Pattern, ProductLiteral,
    ProductPattern, Subtract, Variable, WhileLoop,
)
from .result import Err, Ok, Result


@dataclass(frozen=True)
class RizTypeError: ...


@dataclass(frozen=True)
class RizNameError: ...


class Type(Enum):
    INTEGER = auto()
    RATIONAL = auto()
    BOOLEAN = auto()
    UNIT = auto()


@dataclass(frozen=True, eq=False)
class TypeVariable: ...


@dataclass(frozen=True)
class _NeverReturns: ...


NEVER_RETURNS = _NeverReturns()


@dataclass(frozen=True)
class ProductType:
    items: tuple[RizType, ...]


@dataclass(frozen=True)
class Constraint:
    operation: str
    terms: tuple[RizType, ...]


@dataclass(frozen=True, eq=False)
class FunctionType:
    input: ProductType
    output: RizType
    constraints: tuple[Constraint, ...]
    variables: tuple[TypeVariable, ...]


type RizType = Type | TypeVariable | ProductType | FunctionType | _NeverReturns


@dataclass
class _State:
    substitutions: dict[TypeVariable, RizType] = field(default_factory=dict)
    constraints: list[Constraint] = field(default_factory=list)


_I, _R, _B, _U = Type.INTEGER, Type.RATIONAL, Type.BOOLEAN, Type.UNIT
_NUMERIC_PAIRS = ((_I, _I), (_I, _R), (_R, _I), (_R, _R))


def _arithmetic_signatures() -> tuple[tuple[RizType, ...], ...]:
    return tuple((a, b, _I if a is _I and b is _I else _R) for a, b in _NUMERIC_PAIRS)


_SIGNATURES: dict[str, tuple[tuple[RizType, ...], ...]] = {
    "negate": ((_I, _I), (_R, _R)),
    "add": _arithmetic_signatures(),
    "subtract": _arithmetic_signatures(),
    "multiply": _arithmetic_signatures(),
    "divide": tuple((a, b, _R) for a, b in _NUMERIC_PAIRS),
    "order": tuple((a, b, _B) for a, b in _NUMERIC_PAIRS),
    "equal": (
        (_I, _I, _B), (_I, _R, _B), (_R, _I, _B), (_R, _R, _B),
        (_B, _B, _B), (_U, _U, _B),
    ),
    "not": ((_B, _B),),
    "and_or": ((_B, _B, _B), (_I, _I, _I)),
}


def check(node: Expr, env: dict[str, RizType]) -> Result[RizType]:
    state = _State()
    result = _check(node, env, state)
    if isinstance(result, Err):
        return result
    if not _solve(state):
        return Err(RizTypeError())
    return Ok(_resolve(result.value, state))


def _check(node: Expr, env: dict[str, RizType], state: _State) -> Result[RizType]:
    match node:
        case Binding(target, value):
            inferred = _check(value, env, state)
            if isinstance(inferred, Err):
                return inferred
            if not _bind_pattern(target, inferred.value, env):
                return Err(RizTypeError())
            return Ok(_U)
        case Variable(name):
            return Err(RizNameError()) if name not in env else Ok(env[name])
        case Function(name, parameter, body):
            local = _State()
            input_type = _pattern_type(parameter)
            assert isinstance(input_type, ProductType)
            frame = dict(env)
            if not _bind_pattern(parameter, input_type, frame):
                return Err(RizTypeError())
            output_type = TypeVariable()
            frame[name] = FunctionType(input_type, output_type, (), ())
            checked_body = _check(body, frame, local)
            if isinstance(checked_body, Err):
                return checked_body
            if not _unify(output_type, checked_body.value, local) or not _solve(local):
                return Err(RizTypeError())
            normalized_input = _resolve(input_type, local)
            normalized_output = _resolve(output_type, local)
            assert isinstance(normalized_input, ProductType)
            constraints = tuple(_normalize_constraint(c, local) for c in local.constraints)
            # Pure self-recursion leaves a result variable unrelated to either
            # the input or an operation. Preserve the definition, but mark calls
            # as non-returning so evaluation can never recurse accidentally.
            if (
                isinstance(normalized_output, TypeVariable)
                and normalized_output not in _variables_in((normalized_input,), constraints)
            ):
                normalized_output = NEVER_RETURNS
            variables = _variables_in((normalized_input, normalized_output), constraints)
            env[name] = FunctionType(normalized_input, normalized_output, constraints, variables)
            return Ok(_U)
        case Call(callee, arguments):
            checked = _check(callee, env, state)
            if isinstance(checked, Err):
                return checked
            argument_types: list[RizType] = []
            for argument in arguments:
                argument_type = _check(argument, env, state)
                if isinstance(argument_type, Err):
                    return argument_type
                argument_types.append(argument_type.value)
            argument_product = ProductType(tuple(argument_types))
            function = _resolve(checked.value, state)
            if isinstance(function, TypeVariable):
                output = TypeVariable()
                inferred_function = FunctionType(argument_product, output, (), ())
                if not _unify(function, inferred_function, state):
                    return Err(RizTypeError())
                return Ok(output)
            if not isinstance(function, FunctionType):
                return Err(RizTypeError())
            instantiated = _instantiate(function)
            if instantiated.output is NEVER_RETURNS:
                return Err(RizTypeError())
            state.constraints.extend(instantiated.constraints)
            if not _unify(instantiated.input, argument_product, state):
                return Err(RizTypeError())
            if not _solve(state):
                return Err(RizTypeError())
            return Ok(_resolve(instantiated.output, state))
        case Conditional(condition, consequent, alternative):
            condition_type = _check(condition, env, state)
            if isinstance(condition_type, Err):
                return condition_type
            if not _unify(condition_type.value, _B, state):
                return Err(RizTypeError())
            then_env, else_env = dict(env), dict(env)
            then_type = _check(consequent, then_env, state)
            if isinstance(then_type, Err):
                return then_type
            else_type = _check(alternative, else_env, state)
            if isinstance(else_type, Err):
                return else_type
            for variable in list(env):
                joined = _join_types(then_env[variable], else_env[variable], state)
                if joined is None:
                    return Err(RizTypeError())
                env[variable] = joined
            joined = _join_types(then_type.value, else_type.value, state)
            return Err(RizTypeError()) if joined is None else Ok(joined)
        case WhileLoop(condition, body):
            condition_type = _check(condition, env, state)
            if isinstance(condition_type, Err):
                return condition_type
            if not _unify(condition_type.value, _B, state):
                return Err(RizTypeError())
            trial = dict(env)
            checked_body = _check(body, trial, state)
            if isinstance(checked_body, Err):
                return checked_body
            for variable in list(env):
                joined = _join_types(env[variable], trial[variable], state)
                if joined is None:
                    return Err(RizTypeError())
                env[variable] = joined
            return Ok(_U)
        case Block(statements):
            result = _check(statements[0], env, state)
            for statement in statements[1:]:
                if isinstance(result, Err):
                    return result
                result = _check(statement, env, state)
            return result
        case IntLiteral(): return Ok(_I)
        case BoolLiteral(): return Ok(_B)
        case ProductLiteral(items):
            types: list[RizType] = []
            for item in items:
                checked = _check(item, env, state)
                if isinstance(checked, Err):
                    return checked
                types.append(checked.value)
            return Ok(ProductType(tuple(types)))
        case Negate(operand): return _constrain("negate", (_check(operand, env, state),), state)
        case Add(left, right): return _binary_constraint("add", left, right, env, state)
        case Subtract(left, right): return _binary_constraint("subtract", left, right, env, state)
        case Multiply(left, right): return _binary_constraint("multiply", left, right, env, state)
        case Divide(left, right): return _binary_constraint("divide", left, right, env, state)
        case LessThan(left, right) | GreaterThan(left, right) | LessOrEqual(left, right) | GreaterOrEqual(left, right):
            return _binary_constraint("order", left, right, env, state)
        case Equal(left, right) | NotEqual(left, right): return _binary_constraint("equal", left, right, env, state)
        case Not(operand): return _constrain("not", (_check(operand, env, state),), state)
        case And(left, right) | Or(left, right): return _binary_constraint("and_or", left, right, env, state)


def _binary_constraint(operation: str, left: Expr, right: Expr, env: dict[str, RizType], state: _State) -> Result[RizType]:
    return _constrain(operation, (_check(left, env, state), _check(right, env, state)), state)


def _constrain(operation: str, operands: tuple[Result[RizType], ...], state: _State) -> Result[RizType]:
    terms: list[RizType] = []
    for operand in operands:
        if isinstance(operand, Err):
            return operand
        terms.append(operand.value)
    result = TypeVariable()
    state.constraints.append(Constraint(operation, (*terms, result)))
    if not _solve(state):
        return Err(RizTypeError())
    return Ok(_resolve(result, state))


def _pattern_type(pattern: Pattern) -> RizType:
    match pattern:
        case Bind(): return TypeVariable()
        case ProductPattern(items): return ProductType(tuple(_pattern_type(item) for item in items))


def _bind_pattern(pattern: Pattern, value: RizType, env: dict[str, RizType]) -> bool:
    match pattern:
        case Bind(name):
            env[name] = value
            return True
        case ProductPattern(items):
            if not isinstance(value, ProductType) or len(items) != len(value.items):
                return False
            return all(_bind_pattern(p, t, env) for p, t in zip(items, value.items))


def _resolve(value: RizType, state: _State) -> RizType:
    if isinstance(value, TypeVariable) and value in state.substitutions:
        resolved = _resolve(state.substitutions[value], state)
        state.substitutions[value] = resolved
        return resolved
    if isinstance(value, ProductType):
        return ProductType(tuple(_resolve(item, state) for item in value.items))
    if isinstance(value, FunctionType) and not value.variables:
        input_type = _resolve(value.input, state)
        assert isinstance(input_type, ProductType)
        return FunctionType(
            input_type,
            _resolve(value.output, state),
            tuple(_normalize_constraint(c, state) for c in value.constraints),
            (),
        )
    return value


def _occurs(variable: TypeVariable, value: RizType, state: _State) -> bool:
    value = _resolve(value, state)
    if value is variable: return True
    if isinstance(value, ProductType):
        return any(_occurs(variable, item, state) for item in value.items)
    if isinstance(value, FunctionType):
        return _occurs(variable, value.input, state) or _occurs(variable, value.output, state)
    return False


def _unify(left: RizType, right: RizType, state: _State) -> bool:
    left, right = _resolve(left, state), _resolve(right, state)
    if left is right: return True
    if isinstance(left, TypeVariable):
        if _occurs(left, right, state): return False
        state.substitutions[left] = right
        return True
    if isinstance(right, TypeVariable): return _unify(right, left, state)
    if isinstance(left, FunctionType) and isinstance(right, FunctionType):
        left_instance = _instantiate(left) if left.variables else left
        right_instance = _instantiate(right) if right.variables else right
        state.constraints.extend(left_instance.constraints)
        state.constraints.extend(right_instance.constraints)
        return _unify(left_instance.input, right_instance.input, state) and _unify(
            left_instance.output, right_instance.output, state
        )
    if isinstance(left, ProductType) and isinstance(right, ProductType):
        return len(left.items) == len(right.items) and all(_unify(a, b, state) for a, b in zip(left.items, right.items))
    return left is right


def _trial(constraint: Constraint, signature: tuple[RizType, ...], state: _State) -> _State | None:
    trial = _State(dict(state.substitutions), list(state.constraints))
    return trial if all(_unify(term, expected, trial) for term, expected in zip(constraint.terms, signature)) else None


def _solve(state: _State) -> bool:
    changed = True
    while changed:
        changed = False
        for constraint in state.constraints:
            viable = [trial for signature in _SIGNATURES[constraint.operation] if (trial := _trial(constraint, signature, state)) is not None]
            if not viable: return False
            for variable in _variables_in(constraint.terms, ()):
                resolutions = [_resolve(variable, trial) for trial in viable]
                first = resolutions[0]
                if all(_same_type(first, other) for other in resolutions[1:]):
                    before = _resolve(variable, state)
                    if not _unify(variable, first, state): return False
                    if before is not _resolve(variable, state): changed = True
    return True


def _same_type(left: RizType, right: RizType) -> bool:
    if left is right: return True
    return isinstance(left, ProductType) and isinstance(right, ProductType) and len(left.items) == len(right.items) and all(_same_type(a, b) for a, b in zip(left.items, right.items))


def _join_types(left: RizType, right: RizType, state: _State) -> RizType | None:
    left, right = _resolve(left, state), _resolve(right, state)
    if (left is _I and right is _R) or (left is _R and right is _I): return _R
    if isinstance(left, ProductType) and isinstance(right, ProductType):
        if len(left.items) != len(right.items): return None
        items: list[RizType] = []
        for a, b in zip(left.items, right.items):
            joined = _join_types(a, b, state)
            if joined is None: return None
            items.append(joined)
        return ProductType(tuple(items))
    return _resolve(left, state) if _unify(left, right, state) else None


def _normalize_constraint(constraint: Constraint, state: _State) -> Constraint:
    return Constraint(constraint.operation, tuple(_resolve(t, state) for t in constraint.terms))


def _collect_variables(value: RizType, found: list[TypeVariable]) -> None:
    if isinstance(value, TypeVariable):
        if value not in found: found.append(value)
    elif isinstance(value, ProductType):
        for item in value.items: _collect_variables(item, found)
    elif isinstance(value, FunctionType):
        _collect_variables(value.input, found)
        _collect_variables(value.output, found)
        for constraint in value.constraints:
            for term in constraint.terms: _collect_variables(term, found)


def _variables_in(values: tuple[RizType, ...], constraints: tuple[Constraint, ...]) -> tuple[TypeVariable, ...]:
    found: list[TypeVariable] = []
    for value in values: _collect_variables(value, found)
    for constraint in constraints:
        for term in constraint.terms: _collect_variables(term, found)
    return tuple(found)


def _replace(value: RizType, replacements: dict[TypeVariable, TypeVariable]) -> RizType:
    if isinstance(value, TypeVariable): return replacements.get(value, value)
    if isinstance(value, ProductType): return ProductType(tuple(_replace(item, replacements) for item in value.items))
    if isinstance(value, FunctionType):
        input_type = _replace(value.input, replacements)
        assert isinstance(input_type, ProductType)
        return FunctionType(
            input_type,
            _replace(value.output, replacements),
            tuple(Constraint(c.operation, tuple(_replace(t, replacements) for t in c.terms)) for c in value.constraints),
            tuple(replacements.get(v, v) for v in value.variables),
        )
    return value


def _instantiate(function: FunctionType) -> FunctionType:
    replacements = {variable: TypeVariable() for variable in function.variables}
    input_type = _replace(function.input, replacements)
    assert isinstance(input_type, ProductType)
    constraints = tuple(Constraint(c.operation, tuple(_replace(t, replacements) for t in c.terms)) for c in function.constraints)
    return FunctionType(input_type, _replace(function.output, replacements), constraints, tuple(replacements.values()))

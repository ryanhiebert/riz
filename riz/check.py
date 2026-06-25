"""Type checker: reject ill-typed programs before evaluation.

Runs between parse and eval. Synthesizes a type bottom-up (mirroring eval's
operation table, including the coercion law) and rejects illegal operand
combinations — `True + 1`, `1/2 & 3`, `1 == True` — as type errors *here*,
never at eval (Riz doesn't enforce type rules at runtime).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

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
    Multiply,
    Negate,
    Not,
    NotEqual,
    Or,
    Subtract,
    Variable,
    WhileLoop,
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


# A function's type carries its parameters, its body, and the type-env captured
# at definition. The body is re-checked against the concrete argument types at
# each call site, so a function's result type follows its actual arguments
# (`half(5)` is Rational, `half(6)` whole). The standalone "type this function in
# isolation" inference — bounds on un-called functions — is the next step.
@dataclass(frozen=True, eq=False)
class FunctionType:
    parameters: tuple[Bind, ...]
    body: Expr
    captured: dict[str, RizType]


type RizType = Type | FunctionType


_NUMERIC = (Type.INTEGER, Type.RATIONAL)


def check(node: Expr, env: dict[str, RizType]) -> Result[RizType]:
    match node:
        case Binding(Bind(name), value):
            # Infer the value's type, record it for the name, yield UNIT. The
            # name isn't in scope for its own right-hand side (`=` is
            # non-recursive), so `value` is checked against the current env.
            inferred = check(value, env)
            if isinstance(inferred, Err):
                return inferred
            env[name] = inferred.value
            return Ok(Type.UNIT)
        case Variable(name):
            if name not in env:
                return Err(RizNameError())
            return Ok(env[name])
        case Function(name, parameters, body):
            # Record the function's type (capturing the env by value, before the
            # name binds, so `fn` is non-recursive for now) and yield UNIT. The
            # body isn't checked here — it's checked against concrete arguments
            # at each call.
            env[name] = FunctionType(parameters, body, dict(env))
            return Ok(Type.UNIT)
        case Call(callee, arguments):
            checked = check(callee, env)
            if isinstance(checked, Err):
                return checked
            function = checked.value
            if not isinstance(function, FunctionType):
                return Err(RizTypeError())  # only functions are callable
            argument = check(arguments[0], env)
            if isinstance(argument, Err):
                return argument
            # Re-check the body with the parameter bound to the argument's type,
            # over the env captured at definition — so the result follows the
            # actual argument type.
            frame = dict(function.captured)
            frame[function.parameters[0].name] = argument.value
            return check(function.body, frame)
        case Conditional(condition, consequent, alternative):
            checked = check(condition, env)
            if isinstance(checked, Err):
                return checked
            if checked.value is not Type.BOOLEAN:
                return Err(RizTypeError())
            # Each branch is checked in its own copy, so a *new* binding stays
            # local. A pre-existing variable modified in either branch is then
            # merged back as the join of its type along the two paths (the φ-merge,
            # over names that already existed); an incompatible join is an error.
            then_env, else_env = dict(env), dict(env)
            consequent_type = check(consequent, then_env)
            if isinstance(consequent_type, Err):
                return consequent_type
            alternative_type = check(alternative, else_env)
            if isinstance(alternative_type, Err):
                return alternative_type
            for name in list(env):
                merged = _join_types(then_env[name], else_env[name])
                if merged is None:
                    return Err(RizTypeError())
                env[name] = merged
            # The conditional's own value is the join of the two branches' types.
            value_type = _join_types(consequent_type.value, alternative_type.value)
            if value_type is None:
                return Err(RizTypeError())
            return Ok(value_type)
        case WhileLoop(condition, body):
            # The body may run 0+ times, so each pre-existing name's type after
            # the loop is the JOIN of its entry type and its type after the body,
            # iterated to a fixpoint — a widening rebind like `n = n / 3`
            # (Int → Rational) must be reflected. An *incompatible* join (e.g.
            # Int vs Bool) is a type error: statically we can't know whether the
            # loop ran. The condition is re-checked as the env widens, so it must
            # stay BOOLEAN at every reachable type-state. (New names bound in the
            # body stay body-local — they vanish with each `trial` copy.)
            while True:
                cond = check(condition, env)
                if isinstance(cond, Err):
                    return cond
                if cond.value is not Type.BOOLEAN:
                    return Err(RizTypeError())
                trial = dict(env)
                body_type = check(body, trial)
                if isinstance(body_type, Err):
                    return body_type
                widened = False
                for name in list(env):
                    joined = _join_types(env[name], trial[name])
                    if joined is None:
                        return Err(RizTypeError())
                    if joined is not env[name]:
                        env[name] = joined
                        widened = True
                if not widened:
                    return Ok(Type.UNIT)
        case Block(statements):
            # Statements checked in order (threading env, so later ones see
            # earlier bindings); the block's type is its last statement's.
            result = check(statements[0], env)
            for statement in statements[1:]:
                if isinstance(result, Err):
                    return result
                result = check(statement, env)
            return result
        case IntLiteral():
            return Ok(Type.INTEGER)
        case BoolLiteral():
            return Ok(Type.BOOLEAN)
        case Negate(operand):
            return _numeric_unary(check(operand, env))
        case Add(left, right) | Subtract(left, right) | Multiply(left, right):
            return _arithmetic(check(left, env), check(right, env))
        case Divide(left, right):
            return _division(check(left, env), check(right, env))
        case (
            LessThan(left, right)
            | GreaterThan(left, right)
            | LessOrEqual(left, right)
            | GreaterOrEqual(left, right)
        ):
            return _ordering(check(left, env), check(right, env))
        case Equal(left, right) | NotEqual(left, right):
            return _equality(check(left, env), check(right, env))
        case Not(operand):
            return _logical_unary(check(operand, env))
        case And(left, right) | Or(left, right):
            return _and_or(check(left, env), check(right, env))


def _join_types(a: RizType, b: RizType) -> RizType | None:
    """Join two types under the widening lattice: two numbers widen (Int/Int →
    Int, else Rational); identical types join to themselves; otherwise there is
    no join — the types are incompatible (`None`)."""
    if isinstance(a, Type) and isinstance(b, Type) and a in _NUMERIC and b in _NUMERIC:
        if a is Type.INTEGER and b is Type.INTEGER:
            return Type.INTEGER
        return Type.RATIONAL
    if a is b:
        return a
    return None


def _number(operand: Result[RizType]) -> Type | Err:
    """Unwrap a numeric operand's type, or an Err if it isn't numeric."""
    if isinstance(operand, Err):
        return operand
    value = operand.value
    if isinstance(value, Type) and value in _NUMERIC:
        return value
    return Err(RizTypeError())


def _numbers(left: Result[RizType], right: Result[RizType]) -> tuple[Type, Type] | Err:
    a = _number(left)
    if isinstance(a, Err):
        return a
    b = _number(right)
    if isinstance(b, Err):
        return b
    return a, b


def _numeric_unary(operand: Result[RizType]) -> Result[RizType]:
    """`-`: numeric operand → the same numeric type."""
    a = _number(operand)
    return a if isinstance(a, Err) else Ok(a)


def _arithmetic(left: Result[RizType], right: Result[RizType]) -> Result[RizType]:
    """`+ - *`: both numeric; `Int op Int → Int`, else widen to `Rational`."""
    operands = _numbers(left, right)
    if isinstance(operands, Err):
        return operands
    a, b = operands
    if a is Type.INTEGER and b is Type.INTEGER:
        return Ok(Type.INTEGER)
    return Ok(Type.RATIONAL)


def _division(left: Result[RizType], right: Result[RizType]) -> Result[RizType]:
    """`/`: both numeric; always `Rational` (int / int → rational)."""
    operands = _numbers(left, right)
    if isinstance(operands, Err):
        return operands
    return Ok(Type.RATIONAL)


def _ordering(left: Result[RizType], right: Result[RizType]) -> Result[RizType]:
    """`< > <= >=`: both numeric; result BOOLEAN."""
    operands = _numbers(left, right)
    if isinstance(operands, Err):
        return operands
    return Ok(Type.BOOLEAN)


def _equality(left: Result[RizType], right: Result[RizType]) -> Result[RizType]:
    """`== !=`: same type, or both numeric (Int/Rational inter-compare); → BOOLEAN.

    Functions aren't comparable — a function-typed operand is a type error."""
    if isinstance(left, Err):
        return left
    if isinstance(right, Err):
        return right
    a, b = left.value, right.value
    if not (isinstance(a, Type) and isinstance(b, Type)):
        return Err(RizTypeError())
    both_numeric = a in _NUMERIC and b in _NUMERIC
    if both_numeric or a is b:
        return Ok(Type.BOOLEAN)
    return Err(RizTypeError())


def _logical_unary(operand: Result[RizType]) -> Result[RizType]:
    """`!`: boolean operand → BOOLEAN."""
    if isinstance(operand, Err):
        return operand
    if operand.value is not Type.BOOLEAN:
        return Err(RizTypeError())
    return Ok(Type.BOOLEAN)


def _and_or(left: Result[RizType], right: Result[RizType]) -> Result[RizType]:
    """`& |`: logical on booleans (→ BOOLEAN), bitwise on integers (→ INTEGER)."""
    if isinstance(left, Err):
        return left
    if isinstance(right, Err):
        return right
    if left.value is Type.BOOLEAN and right.value is Type.BOOLEAN:
        return Ok(Type.BOOLEAN)
    if left.value is Type.INTEGER and right.value is Type.INTEGER:
        return Ok(Type.INTEGER)
    return Err(RizTypeError())

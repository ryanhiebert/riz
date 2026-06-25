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


# A function's type carries its name, parameters, body, and the type-env captured
# at definition. The body is re-checked against the concrete argument types at
# each call site (see `_check_call`), so a function's result type follows its
# actual arguments (`half(5)` is Rational, `half(6)` whole).
@dataclass(frozen=True, eq=False)
class FunctionType:
    name: str
    parameters: tuple[Bind, ...]
    body: Expr
    captured: dict[str, RizType]


class _Bottom:
    """The recursion-pending type ⊥: the bottom of the lattice, used while a
    recursive function's return type is being solved by fixpoint. It propagates
    through every operation (⊥ op x = ⊥) and is the identity of the join
    (⊥ ∨ x = x), so a base case's type wins over a not-yet-known recursive one.
    Always resolved away before a call returns — never escapes the checker."""


BOTTOM = _Bottom()


# A recursive function, mid-check: a call to it yields the *current* assumed
# return type instead of re-checking its body (which would loop forever). The
# `_check_call` fixpoint widens `assumed` from ⊥ until it stabilizes.
@dataclass(frozen=True, eq=False)
class _Pending:
    assumed: RizType


type RizType = Type | FunctionType | _Pending | _Bottom


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
            # Record the function's type (capturing the env by value) and yield
            # UNIT. The body isn't checked here — it's checked against concrete
            # arguments at each call, where recursion is also resolved.
            env[name] = FunctionType(name, parameters, body, dict(env))
            return Ok(Type.UNIT)
        case Call(callee, arguments):
            checked = check(callee, env)
            if isinstance(checked, Err):
                return checked
            function = checked.value
            argument_types: list[RizType] = []
            for argument in arguments:
                argument_type = check(argument, env)
                if isinstance(argument_type, Err):
                    return argument_type
                argument_types.append(argument_type.value)
            if isinstance(function, _Pending):
                return Ok(function.assumed)  # a recursive call: the assumed return
            if not isinstance(function, FunctionType):
                return Err(RizTypeError())  # only functions are callable
            if len(arguments) != len(function.parameters):
                return Err(RizTypeError())  # wrong number of arguments
            return _check_call(function, tuple(argument_types))
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


def _check_call(function: FunctionType, arguments: tuple[RizType, ...]) -> Result[RizType]:
    """Type a call by checking the body with the parameters bound to the
    arguments' types, over the env captured at definition — so the result follows
    the actual arguments. Recursion is a return-type fixpoint: the function's own
    name binds to a `_Pending` carrying the current assumed return, seeded at ⊥
    and widened (via the body's joins) until it stabilizes. A result that stays ⊥
    means no base case was reached — the function can never return — so reject it.

    The lattice is finite (⊥ ⊏ Int ⊏ Rational, ⊥ ⊏ Boolean, …), so widening
    converges in a few passes; the second pass also *re-checks* the recursive
    branches against the seed, catching type errors that ⊥-propagation hid."""
    assumed: RizType = BOTTOM
    while True:
        frame = dict(function.captured)
        for parameter, argument in zip(function.parameters, arguments):
            frame[parameter.name] = argument
        frame[function.name] = _Pending(assumed)
        result = check(function.body, frame)
        if isinstance(result, Err):
            return result
        if result.value == assumed:
            break
        assumed = result.value
    if assumed is BOTTOM:
        return Err(RizTypeError())  # no base case: the function can't return
    return Ok(assumed)


def _short_binary(left: Result[RizType], right: Result[RizType]) -> Result[RizType] | None:
    """Short-circuit a binary operator on an `Err` (propagate it) or a ⊥ operand
    (the result is ⊥); `None` means both operands are ordinary types."""
    if isinstance(left, Err):
        return left
    if isinstance(right, Err):
        return right
    if left.value is BOTTOM or right.value is BOTTOM:
        return Ok(BOTTOM)
    return None


def _short_unary(operand: Result[RizType]) -> Result[RizType] | None:
    if isinstance(operand, Err):
        return operand
    if operand.value is BOTTOM:
        return Ok(BOTTOM)
    return None


def _join_types(a: RizType, b: RizType) -> RizType | None:
    """Join two types under the widening lattice: ⊥ is the identity (⊥ ∨ x = x);
    two numbers widen (Int/Int → Int, else Rational); identical types join to
    themselves; otherwise there is no join — the types are incompatible
    (`None`)."""
    if a is BOTTOM:
        return b
    if b is BOTTOM:
        return a
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
    short = _short_unary(operand)
    if short is not None:
        return short
    a = _number(operand)
    return a if isinstance(a, Err) else Ok(a)


def _arithmetic(left: Result[RizType], right: Result[RizType]) -> Result[RizType]:
    """`+ - *`: both numeric; `Int op Int → Int`, else widen to `Rational`."""
    short = _short_binary(left, right)
    if short is not None:
        return short
    operands = _numbers(left, right)
    if isinstance(operands, Err):
        return operands
    a, b = operands
    if a is Type.INTEGER and b is Type.INTEGER:
        return Ok(Type.INTEGER)
    return Ok(Type.RATIONAL)


def _division(left: Result[RizType], right: Result[RizType]) -> Result[RizType]:
    """`/`: both numeric; always `Rational` (int / int → rational)."""
    short = _short_binary(left, right)
    if short is not None:
        return short
    operands = _numbers(left, right)
    if isinstance(operands, Err):
        return operands
    return Ok(Type.RATIONAL)


def _ordering(left: Result[RizType], right: Result[RizType]) -> Result[RizType]:
    """`< > <= >=`: both numeric; result BOOLEAN."""
    short = _short_binary(left, right)
    if short is not None:
        return short
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
    if a is BOTTOM or b is BOTTOM:
        return Ok(BOTTOM)
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
    value = operand.value
    if value is BOTTOM:
        return Ok(BOTTOM)
    if value is not Type.BOOLEAN:
        return Err(RizTypeError())
    return Ok(Type.BOOLEAN)


def _and_or(left: Result[RizType], right: Result[RizType]) -> Result[RizType]:
    """`& |`: logical on booleans (→ BOOLEAN), bitwise on integers (→ INTEGER)."""
    if isinstance(left, Err):
        return left
    if isinstance(right, Err):
        return right
    a, b = left.value, right.value
    if a is BOTTOM or b is BOTTOM:
        return Ok(BOTTOM)
    if a is Type.BOOLEAN and b is Type.BOOLEAN:
        return Ok(Type.BOOLEAN)
    if a is Type.INTEGER and b is Type.INTEGER:
        return Ok(Type.INTEGER)
    return Err(RizTypeError())

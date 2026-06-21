"""Evaluator: walk the syntax tree to a value, or an error that escaped."""

from collections.abc import Callable
from dataclasses import dataclass

from .boolean import Boolean
from .integer import Integer
from .parse import (
    Add,
    And,
    Bind,
    Binding,
    BoolLiteral,
    Conditional,
    Divide,
    Equal,
    Expr,
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
)
from .ratio import Ratio
from .result import Err, Ok, Result
from .unit import Unit

type Value = Integer | Ratio | Boolean | Unit
type Numeric = Integer | Ratio


@dataclass(frozen=True)
class RizDivisionByZeroError: ...


def eval(node: Expr, env: dict[str, Value]) -> Result[Value]:
    match node:
        case Binding(Bind(name), value):
            evaluated = eval(value, env)
            if isinstance(evaluated, Err):
                return evaluated  # a failed binding leaves the name untouched
            env[name] = evaluated.value
            return Ok(Unit())
        case Variable(name):
            if name not in env:
                raise AssertionError("type checker should reject unbound names")
            return Ok(env[name])
        case Conditional(condition, consequent, alternative):
            evaluated = eval(condition, env)
            if isinstance(evaluated, Err):
                return evaluated
            # Lazy: only the selected branch runs (so the dead branch's errors,
            # like div-by-zero, never fire). Branches get their own env scope.
            branch = consequent if _truth(evaluated.value) else alternative
            return eval(branch, dict(env))
        case IntLiteral(value):
            return Ok(Integer(value))
        case BoolLiteral(value):
            return Ok(Boolean(value))
        case Negate(operand):
            return _unary(eval(operand, env), _negate)
        case Add(left, right):
            return _binary(eval(left, env), eval(right, env), _add)
        case Subtract(left, right):
            return _binary(eval(left, env), eval(right, env), _subtract)
        case Multiply(left, right):
            return _binary(eval(left, env), eval(right, env), _multiply)
        case Divide(left, right):
            return _binary(eval(left, env), eval(right, env), _divide)
        case LessThan(left, right):
            return _binary(eval(left, env), eval(right, env), _less_than)
        case GreaterThan(left, right):
            return _binary(eval(left, env), eval(right, env), _greater_than)
        case LessOrEqual(left, right):
            return _binary(eval(left, env), eval(right, env), _less_or_equal)
        case GreaterOrEqual(left, right):
            return _binary(eval(left, env), eval(right, env), _greater_or_equal)
        case Equal(left, right):
            return _binary_value(eval(left, env), eval(right, env), _equal)
        case NotEqual(left, right):
            return _binary_value(eval(left, env), eval(right, env), _not_equal)
        case And(left, right):
            return _binary_value(eval(left, env), eval(right, env), _and)
        case Or(left, right):
            return _binary_value(eval(left, env), eval(right, env), _or)
        case Not(operand):
            return _unary_value(eval(operand, env), _logical_not)


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
    if isinstance(left, Boolean) and isinstance(right, Boolean):
        return left.value == right.value
    if isinstance(left, Boolean) or isinstance(right, Boolean):
        raise AssertionError("type checker should reject == across number and boolean")
    # both numeric: equal iff equal as fractions
    a, b = _widen(_number(left)), _widen(_number(right))
    return a.numerator * b.denominator == b.numerator * a.denominator


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

"""The arithmetic check of derived claims: numbers, + - * / **, parentheses, round, abs, min, max. No names."""

import ast
import operator
from collections.abc import Callable
from typing import Any

from simpleeval import InvalidExpression, SimpleEval


class ArithmeticRejected(Exception):
    pass


FUNCTIONS: dict[str, Callable[..., Any]] = {"round": round, "abs": abs, "min": min, "max": max}
MAX_LENGTH = 300
MAX_EXPONENT = 100


def _div(a: float, b: float) -> float:
    return a / b


def _pow(a: float, b: float) -> float:
    if abs(b) > MAX_EXPONENT:
        raise ArithmeticRejected(f"exponent above {MAX_EXPONENT}")
    return float(a) ** b


OPERATORS: dict[type, Callable[..., Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: _div,
    ast.Pow: _pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _check(node: ast.AST) -> None:
    """Only the allowed shapes: anything else (a name, an attribute, a string, a keyword) is rejected."""
    match node:
        case ast.Expression(body=body):
            _check(body)
        case ast.BinOp(left=left, op=op, right=right) if type(op) in OPERATORS:
            _check(left)
            _check(right)
        case ast.UnaryOp(op=op, operand=operand) if type(op) in OPERATORS:
            _check(operand)
        case ast.Constant(value=value) if isinstance(value, int | float) and not isinstance(value, bool):
            pass
        case ast.Call(func=ast.Name(id=name), args=args, keywords=[]) if name in FUNCTIONS and args:
            for arg in args:
                _check(arg)
        case _:
            raise ArithmeticRejected(f"not allowed in an expression: {type(node).__name__}")


def evaluate(expression: str) -> float:
    """The value of the expression. Raises ArithmeticRejected for anything outside the allowed arithmetic."""
    if len(expression) > MAX_LENGTH:
        raise ArithmeticRejected("expression too long")
    try:
        _check(ast.parse(expression, mode="eval"))
        return float(SimpleEval(operators=OPERATORS, functions=FUNCTIONS, names={}).eval(expression))
    except ArithmeticRejected:
        raise
    except (SyntaxError, InvalidExpression, ArithmeticError, TypeError, ValueError) as error:
        raise ArithmeticRejected(f"{type(error).__name__}: {error}") from error


def within_tolerance(computed: float, stated: float) -> bool:
    return abs(computed - stated) <= 0.005 * max(1.0, abs(stated))

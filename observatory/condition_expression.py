from __future__ import annotations

import ast
import inspect
from dataclasses import dataclass
from typing import Any

from observatory.condition_registry import ConditionRegistry


class ConditionExpressionError(ValueError):
    pass


@dataclass(frozen=True)
class ConditionResult:
    value: bool
    reason: str | None = None


class _ExpressionValidator(ast.NodeVisitor):
    _comparison_operators = (
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        ast.In,
        ast.NotIn,
    )

    def generic_visit(self, node):
        raise ConditionExpressionError(
            f"Unsupported condition syntax: {type(node).__name__}"
        )

    def visit_Expression(self, node: ast.Expression):
        self.visit(node.body)

    def visit_Name(self, node: ast.Name):
        if node.id.startswith("_"):
            raise ConditionExpressionError("Private names are not allowed")

    def visit_Constant(self, node: ast.Constant):
        if not isinstance(node.value, (str, int, float, bool, type(None))):
            raise ConditionExpressionError(
                f"Unsupported condition literal: {type(node.value).__name__}"
            )

    def visit_List(self, node: ast.List):
        for item in node.elts:
            self.visit(item)

    def visit_Tuple(self, node: ast.Tuple):
        for item in node.elts:
            self.visit(item)

    def visit_Attribute(self, node: ast.Attribute):
        if node.attr.startswith("_"):
            raise ConditionExpressionError("Private attributes are not allowed")
        self.visit(node.value)

    def visit_Subscript(self, node: ast.Subscript):
        self.visit(node.value)
        if isinstance(node.slice, ast.Slice):
            raise ConditionExpressionError("Slices are not allowed in conditions")
        self.visit(node.slice)

    def visit_BoolOp(self, node: ast.BoolOp):
        if not isinstance(node.op, (ast.And, ast.Or)):
            raise ConditionExpressionError("Only 'and' and 'or' are allowed")
        for value in node.values:
            self.visit(value)

    def visit_UnaryOp(self, node: ast.UnaryOp):
        if not isinstance(node.op, ast.Not):
            raise ConditionExpressionError("Only boolean 'not' is allowed")
        self.visit(node.operand)

    def visit_Compare(self, node: ast.Compare):
        if any(not isinstance(op, self._comparison_operators) for op in node.ops):
            raise ConditionExpressionError("Unsupported comparison operator")
        self.visit(node.left)
        for comparator in node.comparators:
            self.visit(comparator)

    def visit_Call(self, node: ast.Call):
        if not (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "conditions"
        ):
            raise ConditionExpressionError(
                "Only calls under the 'conditions' namespace are allowed"
            )
        if node.func.attr.startswith("_"):
            raise ConditionExpressionError("Private condition names are not allowed")
        try:
            ConditionRegistry.get_condition(node.func.attr)
        except ValueError as error:
            raise ConditionExpressionError(str(error)) from error
        for argument in node.args:
            if isinstance(argument, ast.Starred):
                raise ConditionExpressionError("Starred arguments are not allowed")
            self.visit(argument)
        for keyword in node.keywords:
            if keyword.arg is None:
                raise ConditionExpressionError("Expanded keyword arguments are not allowed")
            self.visit(keyword.value)


@dataclass(frozen=True)
class ConditionExpression:
    source: str
    tree: ast.Expression

    @classmethod
    def parse(cls, source: str) -> "ConditionExpression":
        try:
            parsed = ast.parse(source, mode="eval")
        except SyntaxError as error:
            raise ConditionExpressionError(
                f"Invalid condition expression: {source}"
            ) from error

        _ExpressionValidator().visit(parsed)
        return cls(source=source, tree=parsed)

    async def evaluate(self, context) -> ConditionResult:
        evaluator = _ExpressionEvaluator(context)
        try:
            value = await evaluator.evaluate(self.tree.body)
        except ConditionExpressionError:
            raise
        except Exception as error:
            raise ConditionExpressionError(
                f"Failed to evaluate condition '{self.source}': {error}"
            ) from error

        truthy = bool(value)
        return ConditionResult(
            value=truthy,
            reason=None if truthy else evaluator.last_false_reason,
        )


class _ExpressionEvaluator:
    def __init__(self, context):
        self.context = context
        self.last_false_reason: str | None = None
        self._snapshot = None

    async def evaluate(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return self._resolve_name(node.id)
        if isinstance(node, ast.Attribute):
            value = await self.evaluate(node.value)
            return self._get_field(value, node.attr)
        if isinstance(node, ast.Subscript):
            value = await self.evaluate(node.value)
            key = await self.evaluate(node.slice)
            try:
                return value[key]
            except (KeyError, IndexError, TypeError) as error:
                raise ConditionExpressionError(
                    f"Cannot resolve index {key!r}"
                ) from error
        if isinstance(node, ast.List):
            return [await self.evaluate(item) for item in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple([await self.evaluate(item) for item in node.elts])
        if isinstance(node, ast.BoolOp):
            return await self._evaluate_bool_op(node)
        if isinstance(node, ast.UnaryOp):
            return not bool(await self.evaluate(node.operand))
        if isinstance(node, ast.Compare):
            return await self._evaluate_comparison(node)
        if isinstance(node, ast.Call):
            return await self._evaluate_condition_call(node)

        raise ConditionExpressionError(
            f"Unsupported condition syntax: {type(node).__name__}"
        )

    def _resolve_name(self, name: str) -> Any:
        if name == "args":
            return getattr(self.context, "args", {})
        if name == "observatory":
            observatory = getattr(self.context, "observatory", None)
            if observatory is None or not hasattr(observatory, "state"):
                raise ConditionExpressionError(
                    "Observatory state is unavailable in this execution context"
                )
            if self._snapshot is None:
                self._snapshot = observatory.state.snapshot()
            return self._snapshot
        if name == "conditions":
            raise ConditionExpressionError(
                "The 'conditions' namespace may only be used for calls"
            )

        results = getattr(self.context, "results", {})
        if name in results:
            return results[name]
        raise ConditionExpressionError(f"Unknown condition variable: {name}")

    @staticmethod
    def _get_field(value: Any, field: str) -> Any:
        if field.startswith("_"):
            raise ConditionExpressionError("Private attributes are not allowed")
        try:
            if isinstance(value, dict):
                return value[field]
            return getattr(value, field)
        except (KeyError, AttributeError) as error:
            raise ConditionExpressionError(
                f"Unknown condition field: {field}"
            ) from error

    async def _evaluate_bool_op(self, node: ast.BoolOp) -> bool:
        if isinstance(node.op, ast.And):
            for value_node in node.values:
                if not bool(await self.evaluate(value_node)):
                    return False
            return True

        for value_node in node.values:
            if bool(await self.evaluate(value_node)):
                return True
        return False

    async def _evaluate_comparison(self, node: ast.Compare) -> bool:
        left = await self.evaluate(node.left)
        for operator, comparator_node in zip(node.ops, node.comparators):
            right = await self.evaluate(comparator_node)
            if not self._compare(operator, left, right):
                return False
            left = right
        return True

    @staticmethod
    def _compare(operator: ast.cmpop, left: Any, right: Any) -> bool:
        try:
            if isinstance(operator, ast.Eq):
                return left == right
            if isinstance(operator, ast.NotEq):
                return left != right
            if isinstance(operator, ast.Lt):
                return left < right
            if isinstance(operator, ast.LtE):
                return left <= right
            if isinstance(operator, ast.Gt):
                return left > right
            if isinstance(operator, ast.GtE):
                return left >= right
            if isinstance(operator, ast.In):
                return left in right
            if isinstance(operator, ast.NotIn):
                return left not in right
        except (TypeError, ValueError) as error:
            raise ConditionExpressionError(
                f"Invalid comparison between {left!r} and {right!r}"
            ) from error
        raise ConditionExpressionError("Unsupported comparison operator")

    async def _evaluate_condition_call(self, node: ast.Call) -> bool:
        condition_name = node.func.attr
        condition = ConditionRegistry.get_condition(condition_name)
        args = [await self.evaluate(argument) for argument in node.args]
        kwargs = {
            keyword.arg: await self.evaluate(keyword.value)
            for keyword in node.keywords
        }

        signature = inspect.signature(inspect.unwrap(condition))
        public_signature = signature.replace(
            parameters=[
                parameter
                for parameter in signature.parameters.values()
                if parameter.name != "observatory"
            ]
        )
        try:
            bound = public_signature.bind(*args, **kwargs)
        except TypeError as error:
            raise ConditionExpressionError(
                f"Invalid arguments for condition '{condition_name}': {error}"
            ) from error

        if "observatory" in signature.parameters:
            observatory = getattr(self.context, "observatory", None)
            if observatory is None:
                raise ConditionExpressionError(
                    f"Condition '{condition_name}' requires an observatory"
                )
            bound.arguments["observatory"] = observatory

        result = condition(**bound.arguments)
        if inspect.isawaitable(result):
            result = await result

        reason = None
        if isinstance(result, tuple) and len(result) == 2:
            result, reason = result
        if not isinstance(result, bool):
            raise ConditionExpressionError(
                f"Condition '{condition_name}' must return bool or (bool, reason)"
            )
        if not result and reason:
            self.last_false_reason = str(reason)
        return result

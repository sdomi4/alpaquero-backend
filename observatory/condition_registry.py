import inspect
from typing import Any, Callable, Dict


class ConditionRegistry:
    """Registry for condition functions that may be used by sequence expressions."""

    _conditions: Dict[str, tuple[Callable, list[dict[str, Any]]]] = {}

    @classmethod
    def register(cls, name: str):
        def decorator(func: Callable):
            cls._conditions[name] = (func, cls._signature_args(func))
            return func

        return decorator

    @staticmethod
    def _signature_args(func: Callable) -> list[dict[str, Any]]:
        signature = inspect.signature(inspect.unwrap(func))
        args: list[dict[str, Any]] = []

        for parameter in signature.parameters.values():
            if parameter.name in {"self", "cls", "observatory"}:
                continue

            arg: dict[str, Any] = {
                "name": parameter.name,
                "required": parameter.default is inspect.Parameter.empty,
            }
            if parameter.annotation is not inspect.Parameter.empty:
                annotation = parameter.annotation
                arg["type"] = (
                    annotation
                    if isinstance(annotation, str)
                    else inspect.formatannotation(annotation)
                )
            if parameter.default is not inspect.Parameter.empty:
                arg["default"] = parameter.default
            args.append(arg)

        return args

    @classmethod
    def get_condition(cls, name: str) -> Callable:
        try:
            return cls._conditions[name][0]
        except KeyError:
            raise ValueError(f"Unknown condition: {name}") from None

    @classmethod
    def list_conditions(cls) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "args": [arg.copy() for arg in args],
            }
            for name, (_func, args) in cls._conditions.items()
        ]

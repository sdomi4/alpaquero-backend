import inspect
from typing import Any, Callable, Dict

class ActionRegistry:
    _actions: Dict[str, tuple[Callable, bool, str | None, list[dict[str, Any]]]] = {}

    @classmethod
    def register(cls, name, observatory_arg=False, action_type=None, primary=None):
        """Decorator to register a function"""
        def decorator(func):
            args = cls._signature_args(func, primary)
            cls._actions[name] = (func, observatory_arg, action_type, args)
            return func
        return decorator

    @staticmethod
    def _signature_args(func, primary):
        signature = inspect.signature(inspect.unwrap(func))
        args = []

        for parameter in signature.parameters.values():
            if parameter.name in {"self", "cls", "observatory"}:
                continue

            arg = {"name": parameter.name}
            if parameter.annotation is not inspect.Parameter.empty:
                annotation = parameter.annotation
                arg["type"] = (
                    annotation
                    if isinstance(annotation, str)
                    else inspect.formatannotation(annotation)
                )
            if parameter.name == primary:
                arg["primary"] = True
            args.append(arg)

        if primary is not None and not any(arg["name"] == primary for arg in args):
            raise ValueError(
                f"Primary argument '{primary}' is not exposed by action "
                f"'{func.__name__}'"
            )

        return args

    @classmethod
    def get_action(cls, name):
        if name not in cls._actions:
            raise ValueError(f"Unknown action: {name}")
        return cls._actions[name]
    
    @classmethod
    def list_actions(cls):
        return [
            {
                "name": name,
                "action_type": action_type,
                "args": [arg.copy() for arg in args],
                "primary": next(
                    (
                        arg["name"]
                        for arg in args
                        if arg.get("primary")
                    ),
                    None,
                ),
            }
            for name, (_func, _observatory_arg, action_type, args)
            in cls._actions.items()
        ]

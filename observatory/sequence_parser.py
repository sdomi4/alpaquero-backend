import yaml
from observatory.observation_engine import Sequence, ParallelGroup, Task, SequenceBuilder, Lifecycle
from observatory.action_registry import ActionRegistry
from observatory.observatory import Observatory
import asyncio
import inspect
import re


TEMPLATE_PATTERN = re.compile(r"{{\s*([^{}]+?)\s*}}")
IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_]\w*")
UNTIL_PATTERN = re.compile(r"\d{1,2}:\d{2}(:\d{2})?")

class SequenceParser(SequenceBuilder):
    def __init__(self, yaml_string: str, observatory: Observatory, context=None):
        self.yaml_string = yaml_string
        self.observatory = observatory
        
        data = yaml.safe_load(yaml_string)
        name = data.get("name", "Unnamed Sequence")
        description = data.get("description", name)
        
        super().__init__(name, description)
        self.context = context
        
    def build(self, yaml_string = None, context = None, observatory = None, **kwargs):
        if not yaml_string:
            yaml_string = self.yaml_string
        data = yaml.safe_load(yaml_string)

        return self._recursive_build(data, context)

    def _recursive_build(self, data: dict, context):
        name = data.get("name", "Unnamed")

        lifecycle = Lifecycle()
        if "delay" in data:
            lifecycle.hooks["delay"] = data["delay"]
        if "until" in data:
            if not UNTIL_PATTERN.match(data["until"]):
                raise ValueError(f"Invalid 'until' format: {data['until']}. Expected HH:MM[:SS]")
            lifecycle.hooks["until"] = data["until"]
        #if "before" in data:
        #     lifecycle.hooks["before"].append(partial(self._run_hook, data["before"], context))
        # if "after" in data:
        #     lifecycle.hooks["after"].append(partial(self._run_hook, data["after"], context))
        # if "finally" in data:
        #     lifecycle.hooks["finally"].append(partial(self._run_hook, data["finally"], context))
        # if "on_error" in data:
        #     lifecycle.hooks["on_error"].append(partial(self._run_hook, data["on_error"], context))
        # if "when" in data:
        #     lifecycle.hooks["when"].append(partial(self._evaluate_condition, data["when"], context))
        if "repeat" in data:
            lifecycle.hooks["repeat"] = data["repeat"]

        if "sequence" in data:
            sequence = Sequence(name, context, hooks=lifecycle)
            for step_data in data["sequence"]:
                child = self._recursive_build(step_data, context)
                sequence.add_step(child)
            return sequence
        
        elif "parallel" in data:
            parallel_group = ParallelGroup(name, context, hooks=lifecycle)
            for step_data in data["parallel"]:
                child = self._recursive_build(step_data, context)
                parallel_group.add_task(child)
            return parallel_group
        
        elif "action" in data:
            # explicitly False out observatory_arg because i'm confused
            _observatory_arg = False
            action_name = data["action"]
            args = dict(data.get("args", {}))
            register = data.get("register")

            func, _observatory_arg, action_type = ActionRegistry.get_action(action_name)

            original = inspect.unwrap(func)
            original_signature = inspect.signature(original)

            bound = self._make_bound_action(
                func,
                original_signature,
                action_name,
                action_type,
                args,
                data,
                context,
            )

            return Task(action_name, bound, context, lifecycle, register=register)

        else:
            raise ValueError("Unknown node type")

    def _make_bound_action(
        self,
        func,
        original_signature,
        action_name: str,
        action_type: str,
        args: dict,
        data: dict,
        context,
    ):
        def call_action():
            accepted_args = self._accepted_args(args, original_signature, context)
            if action_type != "observatory" and "observatory" in original_signature.parameters:
                print("Adding observatory to accepted args for action:", action_name)
                accepted_args["observatory"] = self.observatory

            if action_type == "device":
                device_id = self._device_id(data, args, context)
                if not device_id:
                    raise ValueError(f"Device action '{action_name}' requires 'device' argument")
                device = self.observatory.get_device(device_id)
                return func(device, **accepted_args)

            if action_type == "observatory":
                accepted_args.pop("observatory", None)
                return func(self.observatory, **accepted_args)

            return func(**accepted_args)

        if asyncio.iscoroutinefunction(func):
            async def async_bound():
                result = call_action()
                if asyncio.iscoroutine(result):
                    return await result
                return result

            async_bound.__name__ = action_name
            return async_bound

        def bound():
            return call_action()

        bound.__name__ = action_name
        return bound

    def _accepted_args(self, args: dict, original_signature: inspect.Signature, context):
        resolved_args = self._resolve_templates(args, context)
        return {
            key: value for key, value in resolved_args.items()
            if key in original_signature.parameters
        }

    def _device_id(self, data: dict, args: dict, context):
        device_id = data.get("device") or data.get("device_id") or args.get("device") or args.get("device_id")
        return self._resolve_templates(device_id, context)

    def _resolve_templates(self, value, context):
        if isinstance(value, dict):
            return {
                key: self._resolve_templates(item, context)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                self._resolve_templates(item, context)
                for item in value
            ]
        if isinstance(value, tuple):
            return tuple(
                self._resolve_templates(item, context)
                for item in value
            )
        if not isinstance(value, str):
            return value

        matches = list(TEMPLATE_PATTERN.finditer(value))
        if not matches:
            return value

        if len(matches) == 1 and matches[0].span() == (0, len(value)):
            return self._resolve_reference(matches[0].group(1), context)

        resolved = value
        for match in reversed(matches):
            replacement = str(self._resolve_reference(match.group(1), context))
            resolved = resolved[:match.start()] + replacement + resolved[match.end():]
        return resolved

    def _resolve_reference(self, expression: str, context):
        if context is None or not hasattr(context, "results"):
            raise ValueError(f"Cannot resolve '{expression}' without an execution context")

        expression = expression.strip()
        root_match = IDENTIFIER_PATTERN.match(expression)
        if not root_match:
            raise ValueError(f"Invalid template reference: {expression}")

        root_name = root_match.group(0)
        if root_name not in context.results:
            raise KeyError(f"Unknown registered result: {root_name}")

        value = context.results[root_name]
        index = root_match.end()

        while index < len(expression):
            char = expression[index]
            if char == ".":
                index += 1
                field_match = IDENTIFIER_PATTERN.match(expression, index)
                if not field_match:
                    raise ValueError(f"Invalid template reference: {expression}")
                value = self._get_field(value, field_match.group(0))
                index = field_match.end()
            elif char == "[":
                end_index = expression.find("]", index)
                if end_index == -1:
                    raise ValueError(f"Invalid template reference: {expression}")
                key = self._parse_index(expression[index + 1:end_index])
                value = value[key]
                index = end_index + 1
            elif char.isspace():
                index += 1
            else:
                raise ValueError(f"Invalid template reference: {expression}")

        return value

    def _get_field(self, value, field: str):
        if isinstance(value, dict):
            return value[field]
        return getattr(value, field)

    def _parse_index(self, raw_index: str):
        raw_index = raw_index.strip()
        if (
            len(raw_index) >= 2
            and raw_index[0] == raw_index[-1]
            and raw_index[0] in ("'", '"')
        ):
            return raw_index[1:-1]
        try:
            return int(raw_index)
        except ValueError:
            return raw_index

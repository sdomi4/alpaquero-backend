import concurrent
import asyncio, random, string
import logging
from asyncio import TaskGroup
from abc import ABC, abstractmethod
import inspect
from observatory.condition_expression import ConditionExpression, ConditionResult
from observatory.error_handler import handle_error_async
from typing import TYPE_CHECKING
from datetime import datetime, timedelta
if TYPE_CHECKING:
    from observatory.observatory import Observatory

logger = logging.getLogger(__name__)

class GracefulCancellation(asyncio.CancelledError):
    pass

class AwaitConditionTimeout(TimeoutError):
    pass

def generate_context_id():
    """Generate a random alphanumeric ID for execution contexts."""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))

class ExecutionContext:
    def __init__(self, observatory: 'Observatory' = None, args: dict | None = None):
        self._gate = asyncio.Event()
        self._gate.set()
        self._abort = asyncio.Event()
        self.id = generate_context_id()
        self.results = {}
        self.args = dict(args or {})
        self.observatory = observatory
        self.start_time = None

    def request_pause(self):
        self._gate.clear()

    def resume(self):
        self._gate.set()

    def abort(self):
        self._abort.set()
        self._gate.set()

    def register_result(self, name: str, result):
        self.results[name] = {
            "result": result,
            "ok": True,
        }

    def gate_is_set(self):
        return self._gate.is_set()

    async def checkpoint(self):
        if self._abort.is_set():
            logger.info("Sequence aborted")
            raise GracefulCancellation()
        if not self._gate.is_set():
            logger.info("Sequence paused, waiting to resume")
        await self._gate.wait()
        if self._abort.is_set():
            logger.info("Sequence aborted")
            raise GracefulCancellation()

async def sleep_with_checkpoints(duration: float, context: ExecutionContext):
    for _ in range(int(duration)):
        await asyncio.sleep(1)
        logger.info("Sequence sleep checkpoint")
        await context.checkpoint()

async def sleep_active_with_checkpoints(duration: float, context: ExecutionContext):
    """Sleep for active runtime only, excluding time spent manually paused."""
    remaining = max(float(duration), 0.0)
    loop = asyncio.get_running_loop()
    while remaining > 0:
        await context.checkpoint()
        interval = min(remaining, 0.1)
        started = loop.time()
        await asyncio.sleep(interval)
        if context.gate_is_set():
            remaining -= loop.time() - started

class Step(ABC):
    def __init__(self, name: str, context: ExecutionContext):
        self.name = name
        self.context = context

    @abstractmethod
    async def run(self):
        raise NotImplementedError

    async def _evaluate_condition(self, condition) -> ConditionResult:
        if isinstance(condition, ConditionExpression):
            return await condition.evaluate(self.context)

        if isinstance(condition, list):
            values = []
            for hook in condition:
                value = hook()
                if inspect.isawaitable(value):
                    value = await value
                values.append(bool(value))
            return ConditionResult(all(values))

        value = condition()
        if inspect.isawaitable(value):
            value = await value
        return ConditionResult(bool(value))

    def _until_deadline(self):
        until = self.lifecycle.hooks.get("until")
        if not isinstance(until, str):
            return None

        parts = list(map(int, until.split(":")))
        hour = parts[0]
        minute = parts[1]
        second = parts[2] if len(parts) == 3 else 0
        end_time = self.context.start_time.replace(
            hour=hour,
            minute=minute,
            second=second,
            microsecond=0,
        )
        if end_time <= self.context.start_time:
            end_time += timedelta(days=1)
        return end_time

    async def _until_satisfied(self, deadline) -> bool:
        until = self.lifecycle.hooks.get("until")
        if until is None:
            return False
        if isinstance(until, str):
            return datetime.now() >= deadline
        return (await self._evaluate_condition(until)).value

    def _set_sequence_info(self, text: str) -> None:
        observatory = getattr(self.context, "observatory", None)
        if observatory is None:
            return
        try:
            observatory.state.set_sequence_info(self.context.id, text)
        except ValueError:
            pass

    async def _await_start_condition(self, deadline) -> bool:
        condition = self.lifecycle.hooks.get("await")
        if condition is None:
            return True

        timeout = self.lifecycle.hooks.get("await_timeout")
        active_elapsed = 0.0

        while True:
            await self.context.checkpoint()
            if await self._until_satisfied(deadline):
                return False

            result = await self._evaluate_condition(condition)
            if result.value:
                return True

            info = f"Awaiting: {condition.source}" if isinstance(
                condition, ConditionExpression
            ) else "Awaiting condition"
            if result.reason:
                info += f" ({result.reason})"
            self._set_sequence_info(info)

            if timeout is not None and active_elapsed >= timeout:
                detail = (
                    f"Await condition timed out after {timeout:g}s "
                    f"for node '{self.name}'"
                )
                if isinstance(condition, ConditionExpression):
                    detail += f": {condition.source}"
                if result.reason:
                    detail += f" ({result.reason})"
                raise AwaitConditionTimeout(detail)

            interval = 1.0
            if timeout is not None:
                interval = min(interval, timeout - active_elapsed)
            await sleep_active_with_checkpoints(interval, self.context)
            active_elapsed += interval

    async def _run_lifecycle(self, execute_iteration):
        deadline = self._until_deadline()
        if await self._until_satisfied(deadline):
            return
        if not await self._await_start_condition(deadline):
            return

        while True:
            if await self._until_satisfied(deadline):
                break

            executed_in_batch = False
            for index in range(self.lifecycle.hooks.get("repeat", 1)):
                await self.context.checkpoint()
                logger.info(
                    "Repeating %s: %s",
                    type(self).__name__,
                    index,
                )
                logger.info(
                    "Delaying %s for %s",
                    type(self).__name__,
                    self.lifecycle.hooks.get("delay", 0),
                )
                await sleep_with_checkpoints(
                    self.lifecycle.hooks.get("delay", 0),
                    self.context,
                )
                await self.context.checkpoint()

                when = self.lifecycle.hooks.get("when")
                if when:
                    condition = await self._evaluate_condition(when)
                    logger.info("When condition: %s", condition.value)
                    if not condition.value:
                        continue

                await self.context.checkpoint()
                logger.info("Running %s before hooks", type(self).__name__)
                await self.lifecycle.run("before")
                await self.context.checkpoint()
                await execute_iteration(index)
                executed_in_batch = True
                await self.context.checkpoint()
                logger.info("Running %s after hooks", type(self).__name__)
                await self.lifecycle.run("after")
                await self.context.checkpoint()

            if not self.lifecycle.hooks.get("until"):
                break
            if not executed_in_batch:
                await sleep_active_with_checkpoints(1, self.context)

# Utility class for lifecycle hooks in Sequences/ParallelGroups/Tasks
class Lifecycle:
    def __init__(self):
        self.hooks = {
            "delay": 0,
            "before": [],
            "after": [],
            "finally": [],
            "on_error": [],
            "when": [],
            "await": None,
            "await_timeout": None,
            "repeat": 1,
            "update": False,
            "until": None
        }

    def __str__(self):
        hooks_str = ""
        defaults = {
            "delay": 0,
            "before": [],
            "after": [],
            "finally": [],
            "on_error": [],
            "when": [],
            "await": None,
            "await_timeout": None,
            "repeat": 1,
            "update": False,
            "until": None,
        }
        active_hooks = {
            key: value
            for key, value in self.hooks.items()
            if value != defaults.get(key)
        }
        
        if active_hooks:
            hooks_str = "\n  hooks:"
            for hook_type, value in active_hooks.items():
                if isinstance(value, list):
                    if value:
                        hooks_str += f"\n    {hook_type}:"
                        for item in value:
                            hooks_str += f"\n      - {getattr(item, 'name', str(item))}"
                else:
                    hooks_str += f"\n    {hook_type}: {value}"
        
        return f"lifecycle:{hooks_str}" if hooks_str else "lifecycle: {}"

    def add_hook(self, hook_type: str, *actions: 'Task'):
        if hook_type in self.hooks and isinstance(self.hooks[hook_type], list):
            self.hooks[hook_type].extend(actions)
        else:
            raise ValueError(f"Invalid hook type: {hook_type}")
    
    async def run(self, hook_type: str):
        if hook_type in self.hooks:
            for action in self.hooks.get(hook_type, []):
                if inspect.iscoroutinefunction(action):
                    await action()
                else:
                    action()


class PauseStep(Step):
    def __init__(self, name: str, context: ExecutionContext, reason: str | None = None):
        super().__init__(name, context)
        self.reason = reason

    def __str__(self):
        result = f"pause:\n  name: {self.name}"
        if self.reason:
            result += f"\n  reason: {self.reason}"
        return result

    async def run(self):
        if self.context.start_time is None:
            self.context.start_time = datetime.now()

        self.context.request_pause()

        if self.context.observatory is not None:
            self.context.observatory.state.set_sequence_status(
                self.context.id,
                "paused",
            )
            if self.reason:
                self.context.observatory.state.set_sequence_info(
                    self.context.id,
                    self.reason,
                )

        await self.context.checkpoint()

        if self.context.observatory is not None:
            self.context.observatory.state.set_sequence_status(
                self.context.id,
                "running",
            )


class Sequence(Step):
    def __init__(self, name: str, context: ExecutionContext, hooks: Lifecycle = None, parameters: dict = None):
        super().__init__(name, context)
        self.description = ""
        self.steps = []
        self.lifecycle = hooks if hooks else Lifecycle()
        self.parameters = parameters if parameters else {}

    def __str__(self):
        result = f"sequence:\n  name: {self.name}"
        if self.description:
            result += f"\n  description: {self.description}"
        
        # Add hooks if any are active
        lifecycle_str = str(self.lifecycle)
        if lifecycle_str != "lifecycle: {}":
            result += f"\n  {lifecycle_str.replace(chr(10), chr(10) + '  ')}"
        
        if self.steps:
            result += "\n  steps:"
            for step in self.steps:
                step_str = str(step).replace('\n', '\n    ')
                result += f"\n    - {step_str}"
        
        return result

    def add_step(self, *items: Step):
        self.steps.extend(items)

    async def run(self):
        if self.context.start_time is None:
            self.context.start_time = datetime.now()

        async def execute_iteration(index: int):
            for step in self.steps:
                await self.context.checkpoint()
                assert isinstance(step, Step), "Sequence children must implement Step"
                logger.info("Running step: %s", step.name)
                if self.lifecycle.hooks.get("update", True):
                    info_text = f"Step: {step.name}"
                    if self.lifecycle.hooks.get("repeat", 1) > 1:
                        info_text += f" (repeat {index + 1})"
                    self._set_sequence_info(info_text)
                await step.run()

        try:
            await self._run_lifecycle(execute_iteration)
        except Exception as e:
            await handle_error_async(e, f"Error occurred in sequence {self.name}", level="error")
            await self.lifecycle.run("on_error")
            raise
        finally:
            logger.info("Running Sequence finally hooks")
            await self.lifecycle.run("finally")

class ParallelGroup(Step):
    def __init__(self, name: str, context: ExecutionContext, *tasks: Step, hooks: Lifecycle = None, parameters: dict = None):
        super().__init__(name, context)
        self.description = ""
        self.tasks = list(tasks)
        self.lifecycle = hooks if hooks else Lifecycle()
        self.parameters = parameters if parameters else {}

    def __str__(self):
        result = f"parallel_group:\n  name: {self.name}"
        if self.description:
            result += f"\n  description: {self.description}"
        
        # Add hooks if any are active
        lifecycle_str = str(self.lifecycle)
        if lifecycle_str != "lifecycle: {}":
            result += f"\n  {lifecycle_str.replace(chr(10), chr(10) + '  ')}"
        
        if self.tasks:
            result += "\n  tasks:"
            for task in self.tasks:
                task_str = str(task).replace('\n', '\n    ')
                result += f"\n    - {task_str}"
        
        return result

    def add_task(self, *tasks: Step):
        self.tasks.extend(tasks)

    async def run(self):
        if self.context.start_time is None:
            self.context.start_time = datetime.now()

        async def execute_iteration(index: int):
            logger.info("Task list: %s", self.tasks)
            if self.lifecycle.hooks.get("update", True):
                info_text = f"ParallelGroup: {self.name}"
                if self.lifecycle.hooks.get("repeat", 1) > 1:
                    info_text += f" (repeat {index + 1})"
                self._set_sequence_info(info_text)
            try:
                async with TaskGroup() as tg:
                    for task in self.tasks:
                        tg.create_task(task.run())
            except* GracefulCancellation:
                logger.info("ParallelGroup aborted due to graceful cancellation")

        logger.info("Running ParallelGroup: %s", self.name)
        try:
            await self._run_lifecycle(execute_iteration)
        except Exception as e:
            await handle_error_async(e, f"Error occurred in parallel group {self.name}", level="error")
            await self.lifecycle.run("on_error")
            raise
        finally:
            logger.info("Running ParallelGroup finally hooks")
            await self.lifecycle.run("finally")
        

class Task(Step):
    def __init__(self, name: str, action: callable, context: ExecutionContext, hooks: Lifecycle = None, parameters: dict = None, kind: str = "auto", timeout: float = None, executor: concurrent.futures.Executor | None = None, register: str | None = None):
        super().__init__(name, context)
        self.action = action
        self.lifecycle = hooks if hooks else Lifecycle()
        self.parameters = parameters if parameters else {}
        self.kind = kind  # "auto", "sync", "async", "cpu"
        self.timeout = timeout  # in seconds
        self.executor = executor  # Optional executor for CPU-bound tasks
        self.register = register

    def __str__(self):
        result = f"task:\n  name: {self.name}"
        
        # Add action info with better lambda handling
        if hasattr(self.action, '__name__'):
            action_name = self.action.__name__
            if action_name == '<lambda>':
                # Try to get more info about lambda
                try:
                    source = inspect.getsource(self.action).strip()
                    # Extract just the lambda part, remove surrounding whitespace/assignments
                    if 'lambda:' in source:
                        # Find the lambda: part and extract everything after it until the end of the expression
                        lambda_start = source.find('lambda:') + 7  # 7 = len('lambda:')
                        lambda_body = source[lambda_start:].strip()
                        
                        # Handle cases where lambda is part of a larger expression (like in a list or assignment)
                        # Look for common terminators, but be careful with nested parentheses
                        terminators = [',', ')', '\n']
                        paren_count = 0
                        end_pos = len(lambda_body)
                        
                        for i, char in enumerate(lambda_body):
                            if char == '(':
                                paren_count += 1
                            elif char == ')':
                                paren_count -= 1
                                # If we're at the top level and hit a closing paren, this might be the end
                                if paren_count < 0:
                                    end_pos = i
                                    break
                            elif char in [',', '\n'] and paren_count == 0:
                                end_pos = i
                                break
                        
                        lambda_body = lambda_body[:end_pos].strip()
                        result += f"\n  action: lambda: {lambda_body}"
                    else:
                        result += f"\n  action: <lambda>"
                except:
                    result += f"\n  action: <lambda>"
            else:
                result += f"\n  action: {action_name}"
        else:
            result += f"\n  action: <callable>"
        
        # Add hooks if any are active
        lifecycle_str = str(self.lifecycle)
        if lifecycle_str != "lifecycle: {}":
            result += f"\n  {lifecycle_str.replace(chr(10), chr(10) + '  ')}"
        
        return result
    
    async def _exec(self):
        kind = self.kind
        if kind == "auto":
            kind = "async" if asyncio.iscoroutinefunction(self.action) else "sync"

        async def _await_with_timeout(coro):
            return await (asyncio.wait_for(coro, self.timeout) if self.timeout else coro)
        
        if kind == "async":
            return await _await_with_timeout(self.action())
        elif kind == "sync":
            return await asyncio.to_thread(self.action)
        elif kind == "cpu":
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(self.executor, self.action)
        else:
            raise RuntimeError(f"Unknown task kind: {kind}")

    async def run(self):
        if self.context.start_time is None:
            self.context.start_time = datetime.now()

        async def execute_iteration(index: int):
            logger.info("Executing action for Task: %s", self.name)
            if self.lifecycle.hooks.get("update", True):
                info_text = f"Task: {self.name}"
                if self.lifecycle.hooks.get("repeat", 1) > 1:
                    info_text += f" (repeat {index + 1})"
                self._set_sequence_info(info_text)
            result = await self._exec()
            if asyncio.iscoroutine(result):
                result = await result
            if self.register:
                self.context.register_result(self.register, result)

        logger.info("Running Task: %s", self.name)
        try:
            await self._run_lifecycle(execute_iteration)
        except Exception as e:
            await handle_error_async(e, f"Error occurred in task {self.name}", level="error")
            await self.lifecycle.run("on_error")
            raise
        finally:
            logger.info("Running Task finally hooks: %s", self.name)
            await self.lifecycle.run("finally")

class SequenceBuilder(ABC):
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    @abstractmethod
    def build(self, context: ExecutionContext, **params) -> Sequence:
        raise NotImplementedError("Subclasses must implement build method")

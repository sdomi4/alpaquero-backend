import concurrent
import asyncio, random, string
from asyncio import TaskGroup
from typing import Union
from abc import ABC, abstractmethod
import inspect, traceback
from observatory.error_handler import handle_error_async
from typing import TYPE_CHECKING
from datetime import datetime, timedelta
if TYPE_CHECKING:
    from observatory.observatory import Observatory

class GracefulCancellation(asyncio.CancelledError):
    pass

def generate_context_id():
    """Generate a random alphanumeric ID for execution contexts."""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))

class ExecutionContext:
    def __init__(self, observatory: 'Observatory' = None):
        self._gate = asyncio.Event()
        self._gate.set()
        self._abort = asyncio.Event()
        self.id = generate_context_id()
        self.results = {}
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
        #print("checkpoint")
        if self._abort.is_set():
            print("Sequence aborted")
            raise GracefulCancellation()
        if not self._gate.is_set():
            print("Sequence paused, waiting to resume...")
        await self._gate.wait()

async def sleep_with_checkpoints(duration: float, context: ExecutionContext):
    try:
        for _ in range(int(duration)):
            await asyncio.sleep(1)
            print("Sleeping...")
            await context.checkpoint()
    except asyncio.CancelledError:
        pass

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
            "repeat": 1,
            "update": False,
            "until": None
        }

    def __str__(self):
        hooks_str = ""
        active_hooks = {k: v for k, v in self.hooks.items() 
                       if (isinstance(v, list) and v) or (not isinstance(v, list) and v != (0 if k == "delay" else 1 if k == "repeat" else []))}
        
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
        if hook_type in self.hooks:
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


class Sequence:
    def __init__(self, name: str, context: ExecutionContext, hooks: Lifecycle = None, parameters: dict = None):
        self.name = name
        self.description = ""
        self.steps = []
        self.lifecycle = hooks if hooks else Lifecycle()
        self.context = context
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

    def add_step(self, *items: Union['ParallelGroup', 'Sequence', 'Task']):
        self.steps.extend(items)

    async def run(self):
        if self.context.start_time is None:
            self.context.start_time = datetime.now()
        # Run sequence with pre-execution hooks, sequential execution of steps, and post-execution hooks
        try:
            if self.lifecycle.hooks.get("until"):       
                until_time = self.lifecycle.hooks.get("until")
                parts = list(map(int, until_time.split(":")))
                hour = parts[0]
                minute = parts[1]
                second = parts[2] if len(parts) == 3 else 0
                end_time = self.context.start_time.replace(hour=hour, minute=minute, second=second, microsecond=0)
                if end_time <= self.context.start_time:
                    end_time += timedelta(days=1)

            while True:
                if self.lifecycle.hooks.get("until") and datetime.now() >= end_time:
                    break
                for i in range(self.lifecycle.hooks.get("repeat", 1)):
                    await self.context.checkpoint()
                    print("Repeating Sequence:", i)
                    print("Delaying Sequence for", self.lifecycle.hooks.get("delay", 0))
                    await sleep_with_checkpoints(self.lifecycle.hooks.get("delay", 0), self.context)
                    await self.context.checkpoint()
                    condition = True
                    if self.lifecycle.hooks["when"]:
                        condition = all(await asyncio.gather(*(hook() for hook in self.lifecycle.hooks["when"])))
                        print("When condition:", condition)
                    if not condition:
                        continue
                    await self.context.checkpoint()
                    print("Running Sequence before hooks")
                    await self.lifecycle.run("before")
                    await self.context.checkpoint()
                    for step in self.steps:
                        await self.context.checkpoint()
                        assert isinstance(step, (Sequence, ParallelGroup, Task)), "Step must be a Sequence, ParallelGroup, or Task"
                        print("Running step:", step.name)
                        if self.lifecycle.hooks.get("update", True):
                            info_text = f"Step: {step.name}"
                            if self.lifecycle.hooks.get("repeat", 1) > 1:
                                info_text += f" (repeat {i + 1})"
                            self.context.observatory.state.set_sequence_info(
                                self.context.id,
                                info_text
                            )
                        await step.run()
                    await self.context.checkpoint()
                    print("Running Sequence after hooks")
                    await self.lifecycle.run("after")
                    await self.context.checkpoint()
                if not self.lifecycle.hooks.get("until"):
                    break
                
        except Exception as e:
            await handle_error_async(e, f"Error occurred in sequence {self.name}", level="error")
            await self.lifecycle.run("on_error")
            raise e
        finally:
            print("Running Sequence finally hooks")
            await self.lifecycle.run("finally")

class ParallelGroup:
    def __init__(self, name: str, context: ExecutionContext, *tasks: Union['Task', 'ParallelGroup', 'Sequence'], hooks: Lifecycle = None, parameters: dict = None):
        self.name = name
        self.description = ""
        self.tasks = list(tasks)
        self.lifecycle = hooks if hooks else Lifecycle()
        self.context = context
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

    def add_task(self, *tasks: Union['Task', 'ParallelGroup', 'Sequence']):
        self.tasks.extend(tasks)

    async def run(self):
        if self.context.start_time is None:
            self.context.start_time = datetime.now()
        # Run parallel group with pre-execution hooks, concurrent execution of tasks, and post-execution hooks
        print("Running ParallelGroup:", self.name)
        try:
            if self.lifecycle.hooks.get("until"):       
                until_time = self.lifecycle.hooks.get("until")
                parts = list(map(int, until_time.split(":")))

                hour = parts[0]
                minute = parts[1]
                second = parts[2] if len(parts) == 3 else 0
                end_time = self.context.start_time.replace(hour=hour, minute=minute, second=second, microsecond=0)
                if end_time <= self.context.start_time:
                    end_time += timedelta(days=1)

            while True:
                if self.lifecycle.hooks.get("until") and datetime.now() >= end_time:
                    break
                for i in range(self.lifecycle.hooks.get("repeat", 1)):
                    await self.context.checkpoint()
                    print("Repeating ParallelGroup:", i)
                    print("Delaying ParallelGroup for", self.lifecycle.hooks.get("delay", 0))
                    await sleep_with_checkpoints(self.lifecycle.hooks.get("delay", 0), self.context)
                    condition = True
                    if self.lifecycle.hooks["when"]:
                        condition = all(await asyncio.gather(*(hook() for hook in self.lifecycle.hooks["when"])))
                        print("When condition:", condition)
                    if not condition:
                        continue
                    await self.context.checkpoint()
                    print("Running ParallelGroup before hooks")
                    await self.lifecycle.run("before")
                    try:
                        print(f"Task List: {self.tasks}")
                        if self.lifecycle.hooks.get("update", True):
                            info_text = f"ParallelGroup: {self.name}"
                            if self.lifecycle.hooks.get("repeat", 1) > 1:
                                info_text += f" (repeat {i + 1})"
                            self.context.observatory.state.set_sequence_info(
                                self.context.id,
                                info_text
                            )
                        async with TaskGroup() as tg:
                            for task in self.tasks:
                                tg.create_task(task.run())
                    except* GracefulCancellation:
                        print("ParallelGroup aborted due to GracefulCancellation")
                    await self.context.checkpoint()
                    print("Running ParallelGroup after hooks")
                    await self.lifecycle.run("after")
                    await self.context.checkpoint()
                if not self.lifecycle.hooks.get("until"):
                    break   
        except Exception as e:
            await handle_error_async(e, f"Error occurred in parallel group {self.name}", level="error")
            traceback.print_exc()
            await self.lifecycle.run("on_error")
            raise e
        finally:
            print("Running ParallelGroup finally hooks")
            await self.lifecycle.run("finally")
        

class Task:
    def __init__(self, name: str, action: callable, context: ExecutionContext, hooks: Lifecycle = None, parameters: dict = None, kind: str = "auto", timeout: float = None, executor: concurrent.futures.Executor | None = None, register: str | None = None):
        self.name = name
        self.action = action
        self.lifecycle = hooks if hooks else Lifecycle()
        self.context = context
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
        print("Running Task:", self.name)
        try:
            if self.lifecycle.hooks.get("until"):       
                until_time = self.lifecycle.hooks.get("until")
                parts = list(map(int, until_time.split(":")))

                hour = parts[0]
                minute = parts[1]
                second = parts[2] if len(parts) == 3 else 0
                end_time = self.context.start_time.replace(hour=hour, minute=minute, second=second, microsecond=0)
                if end_time <= self.context.start_time:
                    end_time += timedelta(days=1)

            while True:
                if self.lifecycle.hooks.get("until") and datetime.now() >= end_time:
                    break
                for i in range(self.lifecycle.hooks.get("repeat", 1)):
                    await self.context.checkpoint()
                    print("Repeating Task:", i)
                    print("Delaying Task for", self.lifecycle.hooks.get("delay", 0))
                    await sleep_with_checkpoints(self.lifecycle.hooks.get("delay", 0), self.context)
                    await self.context.checkpoint()
                    condition = True
                    if self.lifecycle.hooks["when"]:
                        condition = all(await asyncio.gather(*(hook() for hook in self.lifecycle.hooks["when"])))
                        print("When condition:", condition)
                    if not condition:
                        continue
                    await self.context.checkpoint()
                    print("Running Task before hooks")
                    await self.lifecycle.run("before")
                    await self.context.checkpoint()
                    print("Executing action for Task:", self.name)
                    if self.lifecycle.hooks.get("update", True):
                        info_text = f"Task: {self.name}"
                        if self.lifecycle.hooks.get("repeat", 1) > 1:
                            info_text += f" (repeat {i + 1})"
                        self.context.observatory.state.set_sequence_info(
                            self.context.id,
                            info_text
                        )
                    result = await self._exec()
                    if asyncio.iscoroutine(result):
                        result = await result
                    if self.register:
                        self.context.register_result(self.register, result)
                    await self.context.checkpoint()
                    print("Running Task after hooks:", self.name)
                    await self.lifecycle.run("after")
                    await self.context.checkpoint()
                if not self.lifecycle.hooks.get("until"):
                    break
        except Exception as e:
            await handle_error_async(e, f"Error occurred in task {self.name}", level="error")
            await self.lifecycle.run("on_error")
            raise e
        finally:
            print("Running Task finally hooks:", self.name)
            await self.lifecycle.run("finally")

class SequenceBuilder(ABC):
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    @abstractmethod
    def build(self, context: ExecutionContext, **params) -> Sequence:
        raise NotImplementedError("Subclasses must implement build method")

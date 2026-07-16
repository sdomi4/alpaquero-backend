import asyncio
from contextlib import suppress
from observatory.observation_engine import Sequence, ParallelGroup, Task, Lifecycle, ExecutionContext, SequenceBuilder

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from observatory.observatory import Observatory

class SequenceRegistry:
    def __init__(self):
        self.sequences = {} # key = builder name, value = builder instance
        self.registry = {} # key = context id, value = (sequence name, context instance)
        self._tasks: dict[str, asyncio.Task] = {}

    def clear(self):
        self.sequences.clear()

    def add_sequence(self, builder: SequenceBuilder):
        self.sequences[builder.name] = builder

    def list_sequences(self):
        return list(self.sequences.keys())

    def run_sequence(self, observatory: 'Observatory', builder: SequenceBuilder, **params):
        context = ExecutionContext(observatory=observatory)
        # regenerate context if id is taken
        while context.id in self.registry:
            context = ExecutionContext(observatory=observatory)
        self.registry[context.id] = (builder.name, context) # state tuple (name, context instance)
        observatory.state.add_sequence(context.id, builder.name)
        # Execute the sequence with the new context
        async def _runner():
            observatory.state.add_action("Sequence: " + builder.name)
            try:
                sequence = builder.build(context=context, observatory=observatory, **params)
                await sequence.run()
            finally:
                self.registry.pop(context.id, None)
                self._tasks.pop(context.id, None)
                observatory.state.remove_sequence(context.id)
                observatory.state.remove_action("Sequence: " + builder.name)
                print("cleaned up", self.registry)
        
        task = asyncio.create_task(_runner())
        self._tasks[context.id] = task
        task.add_done_callback(self._handle_sequence_result)

        return context.id

    def _handle_sequence_result(self, task: asyncio.Task) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Sequence task failed: {e}")

    async def shutdown(self, *, timeout: float = 10) -> None:
        for _, context in list(self.registry.values()):
            context.abort()

        pending_tasks = [task for task in self._tasks.values() if not task.done()]
        for task in pending_tasks:
            task.cancel()

        if pending_tasks:
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(
                    asyncio.gather(*pending_tasks, return_exceptions=True),
                    timeout=timeout,
                )

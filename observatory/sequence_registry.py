import asyncio
from contextlib import suppress
import logging
from observatory.observation_engine import ExecutionContext, SequenceBuilder

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from observatory.observatory import Observatory

logger = logging.getLogger(__name__)

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
        context = ExecutionContext(observatory=observatory, args=params)
        # regenerate context if id is taken
        while context.id in self.registry:
            context = ExecutionContext(observatory=observatory, args=params)
        self.registry[context.id] = (builder.name, context) # state tuple (name, context instance)
        observatory.state.add_sequence(context.id, builder.name, context.current_steps)
        # Execute the sequence with the new context
        async def _runner():
            observatory.state.add_action("Sequence: " + builder.name)
            try:
                build_params = (
                    {}
                    if getattr(builder, "context_args_only", False)
                    else params
                )
                sequence = builder.build(
                    context=context,
                    observatory=observatory,
                    **build_params,
                )
                context.root_sequence = sequence
                await sequence.run()
            finally:
                self.registry.pop(context.id, None)
                self._tasks.pop(context.id, None)
                observatory.state.remove_sequence(context.id)
                observatory.state.remove_action("Sequence: " + builder.name)
                logger.info("Cleaned up sequence registry: %s", self.registry)
        
        task = asyncio.create_task(_runner())
        self._tasks[context.id] = task
        task.add_done_callback(self._handle_sequence_result)

        return context.id

    def _handle_sequence_result(self, task: asyncio.Task) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Sequence task failed")

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

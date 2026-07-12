import asyncio
from observatory.observation_engine import Sequence, ParallelGroup, Task, Lifecycle, ExecutionContext, SequenceBuilder

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from observatory.observatory import Observatory

class SequenceRegistry:
    def __init__(self):
        self.sequences = {} # key = builder name, value = builder instance
        self.registry = {} # key = context id, value = (sequence name, context instance)

    def clear(self):
        self.sequences.clear()
        self.registry.clear()

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
                observatory.state.remove_sequence(context.id)
                observatory.state.remove_action("Sequence: " + builder.name)
                print("cleaned up", self.registry)
        
        task = asyncio.create_task(_runner())

        return context.id

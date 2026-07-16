from observatory.devices.base import ObservatoryDevice
from observatory.action_registry import ActionRegistry
from alpaquero.alpaquero import Alpaquero
from alpaca import focuser
from observatory.errors import FocuserError
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from observatory.observatory import Observatory

class AlpaqueroFocuser(ObservatoryDevice[focuser.Focuser]):
    def __init__(self, observatory: "Observatory", factory: Callable[[], focuser.Focuser], updater: Callable[[], None], id: str, name: str = None, poll_time: float = 1):
        alpaquero = Alpaquero(
            factory,
            updater,
            poll_time=poll_time,
            name=name or id,
        )
        super().__init__(observatory, alpaquero, id=id, name=name)

    def halt(self):
        try:
            self.alpaca.Halt()
        except Exception as e:
            raise FocuserError(f"Error halting focuser {self.name}: {e}")
        
    def move(self, position: int):
        try:
            if position < 0 or position > self.alpaca.MaxStep:
                raise FocuserError(f"Position {position} is out of bounds (0, {self.alpaca.MaxStep}) for focuser {self.name}")
            if self.alpaca.Position is None:
                raise FocuserError(f"Focuser {self.name} can't read position")
            if abs(self.alpaca.Position - position) > self.alpaca.MaxIncrement:
                raise FocuserError(f"Move from {self.alpaca.Position} to {position} exceeds MaxIncrement {self.alpaca.MaxIncrement} for focuser {self.name}")
            self.alpaca.Move(position)
        except Exception as e:
            raise FocuserError(f"Error moving focuser {self.name} to position {position}: {e}")
        
    def move_by(self, increment: int):
        try:
            if abs(increment) > self.alpaca.MaxIncrement:
                raise FocuserError(f"Increment {increment} is greater than MaxIncrement {self.alpaca.MaxIncrement} for focuser {self.name}")
            position = self.alpaca.Position
            if position is None:
                raise FocuserError(f"Focuser {self.name} can't read position")
            if position + increment < 0 or position + increment > self.alpaca.MaxStep:
                raise FocuserError(f"Increment {increment} would move focuser {self.name} out of bounds (0, {self.alpaca.MaxStep})")
            self.alpaca.Move(position + increment)
        except Exception as e:
            raise FocuserError(f"Error moving focuser {self.name} to increment {increment}: {e}")
        
    async def trigger_move(self, position: int):
        self.dispatch_trigger(self.move, position=position)

    async def trigger_move_by(self, increment: int):
        self.dispatch_trigger(self.move_by, increment=increment)
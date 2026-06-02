from abc import ABC
import asyncio
from typing import Any, TypeVar, Generic, TYPE_CHECKING, Callable

from observatory.action_registry import ActionRegistry
from observatory.error_handler import handle_error

if TYPE_CHECKING:
    from observatory.observatory import Observatory
    from alpaquero.alpaquero import Alpaquero

TAlpaca = TypeVar("TAlpaca")

class ObservatoryDevice(ABC, Generic[TAlpaca]):
    def __init__(self, observatory: "Observatory", alpaquero: "Alpaquero[TAlpaca]", id: str, name: str = None):
        self.observatory: "Observatory" = observatory
        self.alpaquero: "Alpaquero[TAlpaca]" = alpaquero
        self.id = id
        self.name = name or id
        self.alpaquero.set_on_destroy(self._mark_disconnected)

    @property
    def alpaca(self) -> TAlpaca:
        return self.alpaquero.alpaca
    
    @ActionRegistry.register("connect_device", observatory_arg=False, action_type="device")
    def connect(self):
        return self.alpaquero.create()
    
    @ActionRegistry.register("disconnect_device", observatory_arg=False, action_type="device")
    def disconnect(self):
        self.alpaquero.destroy()

    def _mark_disconnected(self) -> None:
        try:
            self.observatory.state.set_device_connected(self.id, False)
        except ValueError:
            return

    def dispatch_trigger(self, action: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        task = asyncio.create_task(asyncio.to_thread(action, *args, **kwargs))
        task.add_done_callback(self._handle_trigger_result)

    def _handle_trigger_result(self, task: "asyncio.Task[Any]") -> None:
        try:
            task.result()
        except Exception as e:
            handle_error(e, "Trigger task failed", level="error")

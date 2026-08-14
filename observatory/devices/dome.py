from observatory.devices.base import ObservatoryDevice
from observatory.action_registry import ActionRegistry
from alpaquero.alpaquero import Alpaquero
from alpaca import dome
from observatory.errors import DomeError
from time import sleep
from typing import TYPE_CHECKING, Callable
from observatory.safety import require_conditions
from observatory.safety_conditions import weather_is_safe, telescope_is_parked

if TYPE_CHECKING:
    from observatory.observatory import Observatory

class AlpaqueroDome(ObservatoryDevice[dome.Dome]):
    def __init__(self, observatory: "Observatory", factory: Callable[[], dome.Dome], updater: Callable[[], None], id: str, name: str = None, poll_time: float = 1):
        alpaquero = Alpaquero(
            factory,
            updater,
            poll_time=poll_time,
            name=name or id,
        )
        super().__init__(observatory, alpaquero, id=id, name=name)

    @ActionRegistry.register("open_dome", observatory_arg=False, action_type="device")
    @require_conditions(weather_is_safe)
    def open(self, override: bool = False):
        state_device = self.observatory.state.get_device(self.id)
        state_device.shutter_status = self.alpaca.ShutterStatus
        if state_device.shutter_status == 0:
            return
        self.observatory.state.add_action(f"Opening {self.alpaquero.name} dome")

        try:
            self.alpaca.OpenShutter()
        except Exception as e:
            self.observatory.state.remove_action(f"Opening {self.alpaquero.name} dome")
            raise DomeError(f"Error opening dome {self.alpaquero.name}: {e}")
        
        while True:
            try:
                status = self.alpaca.ShutterStatus
                state_device.shutter_status = status
                if status == 0:
                    self.observatory.state.remove_action(f"Opening {self.alpaquero.name} dome")
                    break
                sleep(1)
            except Exception as e:
                self.observatory.state.remove_action(f"Opening {self.alpaquero.name} dome")
                raise DomeError(f"Error monitoring dome {self.alpaquero.name} while opening: {e}")
            
    @ActionRegistry.register("close_dome", observatory_arg=False, action_type="device")
    @require_conditions(telescope_is_parked)
    def close(self, override: bool = False):
        state_device = self.observatory.state.get_device(self.id)
        state_device.shutter_status = self.alpaca.ShutterStatus
        if state_device.shutter_status == 1:
            return
        self.observatory.state.add_action(f"Closing {self.alpaquero.name} dome")

        try:
            self.alpaca.CloseShutter()
        except Exception as e:
            self.observatory.state.remove_action(f"Closing {self.alpaquero.name} dome")
            raise DomeError(f"Error closing dome {self.alpaquero.name}: {e}")
        
        while True:
            try:
                status = self.alpaca.ShutterStatus
                state_device.shutter_status = status
                if status == 1:
                    self.observatory.state.remove_action(f"Closing {self.alpaquero.name} dome")
                    break
                sleep(1)
            except Exception as e:
                self.observatory.state.remove_action(f"Closing {self.alpaquero.name} dome")
                raise DomeError(f"Error monitoring dome {self.alpaquero.name} while closing: {e}")
            
    async def trigger_open(self, override: bool = False):
        self.dispatch_trigger(self.open, override=override)
    
    async def trigger_close(self, override: bool = False):
        self.dispatch_trigger(self.close, override=override)

from observatory.devices.base import ObservatoryDevice
from alpaquero.alpaquero import Alpaquero
from alpaca import telescope
from observatory.errors import TelescopeError
from time import sleep
from typing import TYPE_CHECKING, Callable
from observatory.safety import require_conditions
from observatory.safety_conditions import *

from observatory.action_registry import ActionRegistry

if TYPE_CHECKING:
    from observatory.observatory import Observatory

class AlpaqueroTelescope(ObservatoryDevice[telescope.Telescope]):
    def __init__(self, observatory: "Observatory", factory: Callable[[], telescope.Telescope], updater: Callable[[], None], id: str, name: str = None, poll_time: float = 1):
        alpaquero = Alpaquero(
            factory,
            updater,
            poll_time=poll_time,
            name=name or id,
        )
        super().__init__(observatory, alpaquero, id=id, name=name)

    @ActionRegistry.register("park_telescope", observatory_arg=False, action_type="device")
    @require_conditions(dome_is_open)
    def park(self, override: bool = False):
        state_device = self.observatory.state.get_device(self.id)
        try:
            if self.alpaca.AtPark:
                return
            
            self.observatory.state.add_action(f"Parking {self.alpaquero.name}")
            self.alpaca.Park()
            
            for _ in range(60):
                parked = self.alpaca.AtPark
                state_device.parked = parked
                if parked:
                    self.observatory.state.remove_action(f"Parking {self.alpaquero.name}")
                    return
                sleep(1)
            
            self.observatory.state.remove_action(f"Parking {self.alpaquero.name}")
            raise TelescopeError(code="telescope_park_timeout", message=f"Parking telescope {self.alpaquero.name} timed out")
        except Exception as e:
            self.observatory.state.remove_action(f"Parking {self.alpaquero.name}")
            raise TelescopeError(code="telescope_park_failed", message=f"Error parking telescope {self.alpaquero.name}: {e}")

    @ActionRegistry.register("unpark_telescope", observatory_arg=False, action_type="device")
    @require_conditions(weather_is_safe, dome_is_open)
    def unpark(self, override: bool = False):
        state_device = self.observatory.state.get_device(self.id)
        try:
            if not self.alpaca.AtPark:
                return
            
            self.observatory.state.add_action(f"Unparking {self.alpaquero.name}")
            self.alpaca.Unpark()
            
            for _ in range(60):
                parked = self.alpaca.AtPark
                state_device.parked = parked
                if not parked:
                    self.observatory.state.remove_action(f"Unparking {self.alpaquero.name}")
                    return
                sleep(1)
            
            self.observatory.state.remove_action(f"Unparking {self.alpaquero.name}")
            raise TelescopeError(code="telescope_unpark_timeout", message=f"Unparking telescope {self.alpaquero.name} timed out")
        except Exception as e:
            self.observatory.state.remove_action(f"Unparking {self.alpaquero.name}")
            raise TelescopeError(code="telescope_unpark_failed", message=f"Error unparking telescope {self.alpaquero.name}: {e}")

    @ActionRegistry.register("slew_telescope", observatory_arg=False, action_type="device")
    @require_conditions(weather_is_safe, dome_is_open)
    def slew(self, ra: float, dec: float, tracking_rate: int = None, override: bool = False):
        state_device = self.observatory.state.get_device(self.id)
        try:
            if self.alpaca.AtPark:
                self.alpaca.Unpark()
            
            self.alpaca.TargetRightAscension = ra
            self.alpaca.TargetDeclination = dec
            self.alpaca.Tracking = True
            if tracking_rate:
                self.tracking_rate(tracking_rate=tracking_rate)
            self.alpaca.SlewToTargetAsync()
            
            self.observatory.state.add_action(f"Slewing {self.alpaquero.name} to target")
            
            for _ in range(60):
                slewing = self.alpaca.Slewing
                state_device.slewing = slewing
                if not slewing:
                    self.observatory.state.remove_action(f"Slewing {self.alpaquero.name} to target")
                    return
                sleep(1)
            
            self.observatory.state.remove_action(f"Slewing {self.alpaquero.name} to target")
            raise TelescopeError(code="telescope_slew_timeout", message=f"Slewing telescope {self.alpaquero.name} timed out")
        except Exception as e:
            self.observatory.state.remove_action(f"Slewing {self.alpaquero.name} to target")
            raise TelescopeError(code="telescope_slew_failed", message=f"Error slewing telescope {self.alpaquero.name}: {e}")

    async def trigger_park(self, override: bool = False):
        self.dispatch_trigger(self.park, override=override)
    
    async def trigger_unpark(self, override: bool = False):
        self.dispatch_trigger(self.unpark, override=override)

    async def trigger_slew(self, ra: float, dec: float, override: bool = False):
        self.dispatch_trigger(self.slew, ra, dec, override=override)

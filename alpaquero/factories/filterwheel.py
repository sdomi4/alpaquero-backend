import logging
from alpaca import filterwheel
from time import sleep

from typing import TYPE_CHECKING

from observatory.state import StateManager, FilterwheelState

logger = logging.getLogger(__name__)

class FilterWheelConnectionError(RuntimeError):
    pass

if TYPE_CHECKING:
    from observatory.state import StateManager

def filterwheel_factory(
        address: str,
        id: str,
        device_number: int = 0,
        state: "StateManager" = None,
    ) -> filterwheel.FilterWheel:
    try:
        logger.info("Connecting to filter wheel %s at %s", id, address)
        fw = filterwheel.FilterWheel(address, device_number)
        
        timeout = 0
        fw.Connected = True
        while fw.Connecting:
            timeout += 1
            if timeout > 10:
                raise FilterWheelConnectionError(f"Filter wheel {id} connection timed out")
            sleep(1)
        state.add_device(FilterwheelState(
            id=id,
            connected=True,
            position=fw.Position,
            names=list(fw.Names) if hasattr(fw, 'Names') else None
        ))
        return fw
    except Exception as e:
        logger.exception("Error connecting to filter wheel %s", id)
        raise FilterWheelConnectionError(f"Error connecting to filter wheel {id}: {e}") from e

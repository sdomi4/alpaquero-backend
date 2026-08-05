import logging
from alpaca import dome
from time import sleep

from observatory.state import StateManager, DomeState

logger = logging.getLogger(__name__)

class DomeConnectionError(RuntimeError):
    pass


def dome_factory(
        address: str,
        id: str,
        device_number: int = 0,
        state: "StateManager" = None,
    ) -> dome.Dome:
    try:
        logger.info("Connecting to dome %s at %s", id, address)
        d = dome.Dome(address, device_number)
        timeout = 0
        d.Connect()
        while d.Connecting:
                timeout += 1
                if timeout > 10:
                    raise DomeConnectionError("Dome connection timed out")
                sleep(1)
        state.add_device(DomeState(id=id, connected=True, status=d.ShutterStatus))
        return d
    except Exception as e:
        logger.exception("Error connecting to dome %s", id)
        raise DomeConnectionError(f"Error connecting to dome: {e}") from e

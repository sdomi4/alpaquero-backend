import logging
from alpaca import telescope
from time import sleep

from observatory.state import StateManager, TelescopeState

logger = logging.getLogger(__name__)

class TelescopeConnectionError(RuntimeError):
    pass


def telescope_factory(
        address: str,
        id: str,
        device_number: int = 0,
        state: "StateManager" = None,
    ) -> telescope.Telescope:
    try:
        logger.info("Connecting to telescope %s at %s", id, address)
        t = telescope.Telescope(address, device_number)
        timeout = 0
        t.Connect()
        while t.Connecting:
                timeout += 1
                if timeout > 10:
                    raise TelescopeConnectionError("Telescope connection timed out")
                sleep(1)
        state.add_device(TelescopeState(id=id, connected=True))
        return t
    except Exception as e:
        logger.exception("Error connecting to telescope %s", id)
        raise TelescopeConnectionError(f"Error connecting to telescope: {e}") from e

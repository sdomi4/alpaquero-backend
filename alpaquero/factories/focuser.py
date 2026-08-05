import logging
from alpaca import focuser
from time import sleep

from observatory.state import StateManager, FocuserState

logger = logging.getLogger(__name__)

class FocuserConnectionError(RuntimeError):
    pass

def focuser_factory(
        address: str,
        id: str,
        device_number: int = 0,
        state: "StateManager" = None,
    ) -> focuser.Focuser:
    try:
        logger.info("Connecting to focuser %s at %s", id, address)
        f = focuser.Focuser(address, device_number)
        timeout = 0
        f.Connect()
        while f.Connecting:
                timeout += 1
                if timeout > 10:
                    raise FocuserConnectionError("Focuser connection timed out")
                sleep(1)
        state.add_device(FocuserState(id=id, connected=True, position=f.Position))
        return f
    except Exception as e:
        logger.exception("Error connecting to focuser %s", id)
        raise FocuserConnectionError(f"Error connecting to focuser: {e}") from e

import logging
from alpaca import covercalibrator
from time import sleep

from observatory.state import StateManager, CoverState

logger = logging.getLogger(__name__)

class CoverConnectionError(RuntimeError):
    pass


def cover_factory(
        address: str,
        id: str,
        device_number: int = 0,
        state: "StateManager" = None,
    ) -> covercalibrator.CoverCalibrator:
    try:
        logger.info("Connecting to cover calibrator %s at %s", id, address)
        c = covercalibrator.CoverCalibrator(address, device_number)
        timeout = 0
        c.Connect()
        while c.Connecting:
                timeout += 1
                if timeout > 10:
                    raise CoverConnectionError("Cover calibrator connection timed out")
                sleep(1)
        state.add_device(CoverState(id=id, connected=True))
        return c
    except Exception as e:
        logger.exception("Error connecting to cover calibrator %s", id)
        raise CoverConnectionError(f"Error connecting to cover calibrator: {e}") from e

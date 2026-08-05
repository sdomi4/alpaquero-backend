import logging
from alpaca import observingconditions
from time import sleep

from observatory.state import StateManager, ObservingConditionsState

logger = logging.getLogger(__name__)

class ObservingConditionsConnectionError(RuntimeError):
    pass


def observing_conditions_factory(
        address: str,
        id: str,
        device_number: int = 0,
        state: "StateManager" = None,
    ) -> observingconditions.ObservingConditions:
    try:
        logger.info("Connecting to observing conditions %s at %s", id, address)
        oc = observingconditions.ObservingConditions(address, device_number)
        timeout = 0
        oc.Connect()
        while oc.Connecting:
                timeout += 1
                if timeout > 10:
                    raise ObservingConditionsConnectionError("Observing conditions connection timed out")
                sleep(1)
        state.add_device(ObservingConditionsState(id=id, connected=True))
        return oc
    except Exception as e:
        logger.exception("Error connecting to observing conditions %s", id)
        raise ObservingConditionsConnectionError(f"Error connecting to observing conditions: {e}") from e

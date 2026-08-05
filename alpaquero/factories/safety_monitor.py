import logging
from alpaca import safetymonitor
from time import sleep

from observatory.state import StateManager, SafetyMonitorState

logger = logging.getLogger(__name__)

class SafetyMonitorConnectionError(RuntimeError):
    pass


def safety_monitor_factory(
        address: str,
        id: str,
        device_number: int = 0,
        state: "StateManager" = None,
    ) -> safetymonitor.SafetyMonitor:
    try:
        logger.info("Connecting to safety monitor %s at %s", id, address)
        sm = safetymonitor.SafetyMonitor(address, device_number)
        timeout = 0
        sm.Connect()
        while sm.Connecting:
                timeout += 1
                if timeout > 10:
                    raise SafetyMonitorConnectionError("Safety monitor connection timed out")
                sleep(1)
        state.add_device(SafetyMonitorState(id=id, connected=True))
        return sm
    except Exception as e:
        logger.exception("Error connecting to safety monitor %s", id)
        raise SafetyMonitorConnectionError(f"Error connecting to safety monitor: {e}") from e

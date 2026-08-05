import logging
from time import sleep
from alpaca import camera
from typing import TYPE_CHECKING

from observatory.state import StateManager, CameraState

logger = logging.getLogger(__name__)

class CameraConnectionError(RuntimeError):
    pass

if TYPE_CHECKING:
    from observatory.state import StateManager

def camera_factory(
        address: str,
        id: str,
        device_number: int = 0,
        state: "StateManager" = None,
    ) -> camera.Camera:
    try:
        logger.info("Connecting to camera %s at %s", id, address)
        cam = camera.Camera(address, device_number)
        
        timeout = 0
        cam.Connected = True
        while cam.Connecting:
            timeout += 1
            if timeout > 10:
                raise CameraConnectionError(f"Camera {id} connection timed out")
            sleep(1)
        state.add_device(CameraState(id=id, connected=True))
        return cam
    except Exception as e:
        logger.exception("Error connecting to camera %s", id)
        raise CameraConnectionError(f"Error connecting to camera {id}: {e}") from e

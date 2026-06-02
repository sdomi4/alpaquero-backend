from typing import TYPE_CHECKING
from observatory.state import StateManager, CoverState
from observatory.devices.cover import AlpaqueroCover
from observatory.error_handler import handle_error

if TYPE_CHECKING:
    from observatory.state import StateManager

def cover_updater(cover: "AlpaqueroCover", id, state: "StateManager" = None):
    if not cover.alpaca.Connected:
        raise ConnectionError("Cover calibrator not connected")
    
    try:
        device = state.get_device(id)
        device.connected = cover.alpaca.Connected
        device.cover_status = cover.alpaca.CoverState
        device.calibrator_status = cover.alpaca.CalibratorState
        device.brightness = cover.alpaca.Brightness
    except Exception as e:
        handle_error(e, "Error updating cover calibrator state", level="warning")

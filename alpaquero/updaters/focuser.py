from observatory.state import StateManager, FocuserState
from observatory.devices.focuser import AlpaqueroFocuser
from observatory.error_handler import handle_error

def focuser_updater(focuser: "AlpaqueroFocuser", id, state: "StateManager" = None):
    if not focuser.alpaca.Connected:
        raise ConnectionError("Focuser not connected")
    
    try:
        device = state.get_device(id)
        device.connected = focuser.alpaca.Connected
        device.position = focuser.alpaca.Position
        device.is_moving = focuser.alpaca.IsMoving
        try:
            device.temperature = focuser.alpaca.Temperature
        except Exception as e:
            pass
    except Exception as e:
        handle_error(e, "Error updating focuser state", level="warning")
from observatory.state import StateManager, DomeState
from observatory.devices.dome import AlpaqueroDome
from observatory.error_handler import handle_error

def dome_updater(dome: "AlpaqueroDome", id, state: "StateManager" = None):
    if not dome.alpaca.Connected:
        raise ConnectionError("Dome not connected")
    
    try:
        device = state.get_device(id)
        device.connected = dome.alpaca.Connected
        device.shutter_status = dome.alpaca.ShutterStatus

        if device.shutter_status == 4:
            handle_error("Dome reported an error", level="error")
    except Exception as e:
        handle_error(e, "Error updating dome state", level="warning")

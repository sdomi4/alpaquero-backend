from observatory.state import StateManager, FilterwheelState
from observatory.devices.filterwheel import AlpaqueroFilterWheel
from observatory.error_handler import handle_error

def filterwheel_updater(filterwheel: "AlpaqueroFilterWheel", id, state: "StateManager" = None):
    if not filterwheel.alpaca.Connected:
        raise ConnectionError(f"Filter wheel {id} not connected")
    
    try:
        device = state.get_device(id)
        device.connected = filterwheel.alpaca.Connected
        device.position = filterwheel.alpaca.Position
        
        if hasattr(filterwheel.alpaca, 'Names') and device.names is None:
            device.names = list(filterwheel.alpaca.Names)
    except Exception as e:
        handle_error(e, "Error updating filterwheel state", level="warning")

from observatory.state import StateManager, SafetyMonitorState
from observatory.devices.safety_monitor import AlpaqueroSafetyMonitor
from observatory.error_handler import handle_error

def safety_monitor_updater(safety_monitor: "AlpaqueroSafetyMonitor", id, state: "StateManager" = None):
    if not safety_monitor.alpaca.Connected:
        raise ConnectionError("Safety monitor not connected")
    
    try:
        device = state.get_device(id)
        device.connected = safety_monitor.alpaca.Connected
        device.safe = safety_monitor.alpaca.IsSafe
    except Exception as e:
        handle_error(e, "Error updating safety monitor state", level="warning")

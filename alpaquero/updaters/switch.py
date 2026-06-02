from typing import TYPE_CHECKING
from observatory.state import StateManager, SwitchState, ToggleControl, RangeControl
from observatory.devices.switch import AlpaqueroSwitch
from observatory.error_handler import handle_error
from alpaquero.factories.switch import enumerate_switch_controls

if TYPE_CHECKING:
    from observatory.state import StateManager

def switch_updater(switch_device: "AlpaqueroSwitch", id, state: "StateManager" = None):
    if not switch_device.alpaca.Connected:
        raise ConnectionError("Switch not connected")
    
    try:
        device = state.get_device(id)
        device.connected = switch_device.alpaca.Connected
        if isinstance(device, SwitchState) and len(device.controls) != switch_device.alpaca.MaxSwitch:
            device.controls = enumerate_switch_controls(switch_device.alpaca)
        
        # Update each control
        for control_name, control in device.controls.items():
            if isinstance(control, ToggleControl):
                control.value = switch_device.alpaca.GetSwitch(control.id)
            elif isinstance(control, RangeControl):
                control.value = switch_device.alpaca.GetSwitchValue(control.id)
    except Exception as e:
        handle_error(e, "Error updating switch state", level="warning")

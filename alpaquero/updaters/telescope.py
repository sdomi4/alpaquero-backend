from typing import TYPE_CHECKING
from observatory.state import StateManager, TelescopeState
from observatory.devices.telescope import AlpaqueroTelescope
from observatory.error_handler import handle_error

if TYPE_CHECKING:
    from observatory.state import StateManager

def telescope_updater(telescope: "AlpaqueroTelescope", id, state: "StateManager" = None):
    if not telescope.alpaca.Connected:
        raise ConnectionError("Telescope not connected")
    
    try:
        device = state.get_device(id)
        device.connected = telescope.alpaca.Connected
        device.tracking = telescope.alpaca.Tracking
        device.slewing = telescope.alpaca.Slewing
        device.parked = telescope.alpaca.AtPark
        device.position = {"ra": telescope.alpaca.RightAscension, "dec": telescope.alpaca.Declination}
        device.side_of_pier = telescope.alpaca.SideOfPier
        
        if hasattr(telescope.alpaca, 'TargetRightAscension'):
            device.target = {
                "ra": telescope.alpaca.TargetRightAscension,
                "dec": telescope.alpaca.TargetDeclination
            }
    except Exception as e:
        handle_error(e, "Error updating telescope state", level="warning")

from observatory.state import StateManager, CameraState
from observatory.devices.camera import AlpaqueroCamera
from observatory.error_handler import handle_error

def camera_updater(camera: "AlpaqueroCamera", id, state: "StateManager" = None):
    if not camera.alpaca.Connected:
        raise ConnectionError(f"Camera {id} not connected")
    
    try:
        device = state.get_device(id)
        device.connected = camera.alpaca.Connected
        device.camera_state = camera.alpaca.CameraState
        device.cooler_on = camera.alpaca.CoolerOn
        device.cooler_power = camera.alpaca.CoolerPower
        device.ccd_temperature = camera.alpaca.CCDTemperature
        device.set_ccd_temperature = camera.alpaca.SetCCDTemperature
        device.bin_x = camera.alpaca.BinX
        device.bin_y = camera.alpaca.BinY
        device.x_size = camera.alpaca.CameraXSize
        device.y_size = camera.alpaca.CameraYSize
        device.gain = camera.alpaca.Gain if hasattr(camera.alpaca, 'Gain') else None
        device.image_ready = camera.alpaca.ImageReady
        
        if hasattr(camera.alpaca, 'LastExposureDuration'):
            device.last_exposure_duration = camera.alpaca.LastExposureDuration
        if hasattr(camera.alpaca, 'LastExposureStartTime'):
            device.last_exposure_start_time = camera.alpaca.LastExposureStartTime
    except Exception as e:
        handle_error(e, "Error updating camera state", level="warning")

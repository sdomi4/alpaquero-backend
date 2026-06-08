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
        try:
            device.set_ccd_temperature = camera.alpaca.SetCCDTemperature
        except Exception as e:
            pass
        device.bin_x = camera.alpaca.BinX
        device.bin_y = camera.alpaca.BinY
        device.x_size = camera.alpaca.CameraXSize
        device.y_size = camera.alpaca.CameraYSize
        try:
            device.gain = camera.alpaca.Gain
        except Exception as e:
            pass
        device.image_ready = camera.alpaca.ImageReady
        
        try:
            device.last_exposure_duration = camera.alpaca.LastExposureDuration
        except Exception as e:
            pass
        try:
            device.last_exposure_start_time = camera.alpaca.LastExposureStartTime
        except Exception as e:
            pass
        try:
            device.percent_completed = camera.alpaca.PercentCompleted
        except Exception as e:
            pass
    except Exception as e:
        handle_error(e, "Error updating camera state", level="warning")

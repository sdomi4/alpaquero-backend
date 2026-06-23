from observatory.action_registry import ActionRegistry
from observatory.devices.base import ObservatoryDevice
from alpaquero.alpaquero import Alpaquero
from alpaca import camera
from observatory.errors import CameraError
from time import sleep
import time
from typing import TYPE_CHECKING, Callable
import numpy as np
import astropy.io.fits as fits
from pathlib import Path


if TYPE_CHECKING:
    from observatory.observatory import Observatory

class AlpaqueroCamera(ObservatoryDevice[camera.Camera]):
    def __init__(self, observatory: "Observatory", factory: Callable[[], camera.Camera], updater: Callable[[], None], id: str, name: str = None, poll_time: float = 1):
        alpaquero = Alpaquero(
            factory,
            updater,
            poll_time=poll_time,
            name=name or id,
        )
        super().__init__(observatory, alpaquero, id=id, name=name)

    @ActionRegistry.register("cool_camera", observatory_arg=False, action_type="device")
    def cool(self, target_temp: float):
        try:
            if not self.alpaca.CoolerOn:
                self.alpaca.CoolerOn = True
            self.alpaca.SetCCDTemperature = target_temp
        except Exception as e:
            raise CameraError(code="camera_cool_failed", message=f"Error setting camera {self.alpaquero.name} temperature: {e}")

    @ActionRegistry.register("wait_for_camera_temperature", observatory_arg=False, action_type="device")
    def wait_for_temperature(self, timeout: int = 600):
        try:
            if not self.alpaca.CoolerOn:
                raise CameraError(code="cooler_not_on", message=f"Camera {self.alpaquero.name} cooler is not on")
            
            start_time = time.time()
            while True:
                current_temp = self.alpaca.CCDTemperature
                target_temp = self.alpaca.SetCCDTemperature
                self.observatory.state.add_action(f"Cooling {self.alpaquero.name}: {current_temp:.1f}C / {target_temp:.1f}C")
                
                if abs(current_temp - target_temp) < 1:
                    self.observatory.state.remove_action(f"Cooling {self.alpaquero.name}: {current_temp:.1f}C / {target_temp:.1f}C")
                    return
                
                if time.time() - start_time > timeout:
                    self.observatory.state.remove_action(f"Cooling {self.alpaquero.name}: {current_temp:.1f}C / {target_temp:.1f}C")
                    raise CameraError(code="camera_cooling_timeout", message=f"Timeout waiting for camera {self.alpaquero.name} to reach target temperature")
                
                sleep(10)
        except Exception as e:
            raise CameraError(code="camera_temperature_wait_failed", message=f"Error waiting for camera {self.alpaquero.name} temperature: {e}")
    
    @ActionRegistry.register("warm_camera", observatory_arg=False, action_type="device")
    def warm_up(self):
        try:
            if not self.alpaca.CoolerOn:
                return
            
            # gradually warm up by increasing the temperature setpoint in steps
            current_temp = self.alpaca.CCDTemperature
            conditions_devices = self.observatory.observing_conditions.keys()
            conditions_device = self.observatory.state.get_device(conditions_devices[0]) if conditions_devices else None
            if conditions_device:
                env_temp = conditions_device.ambient
            else:
                env_temp = 15  # default to 15C if no conditions device available

            step = 5

            while current_temp < env_temp:
                next_temp = min(current_temp + step, env_temp)
                self.alpaca.SetCCDTemperature = next_temp
                self.observatory.state.add_action(f"Warming up {self.alpaquero.name}: {current_temp:.1f}C -> {next_temp:.1f}C")
                
                while True:
                    current_temp = self.alpaca.CCDTemperature
                    if abs(current_temp - next_temp) < 10:
                        break
                    sleep(10)
                
                self.observatory.state.remove_action(f"Warming up {self.alpaquero.name}: {current_temp:.1f}C -> {next_temp:.1f}C")
            self.alpaca.CoolerOn = False
        except Exception as e:
            raise CameraError(code="camera_warmup_failed", message=f"Error warming up camera {self.alpaquero.name}: {e}")

    @ActionRegistry.register("expose_camera", observatory_arg=False, action_type="device")
    def expose(self, exposure: float, binX: int = 1, binY: int = 1, startX: int = 0, startY: int = 0):
        try:
            self.alpaca.BinX = binX
            self.alpaca.BinY = binY
            self.alpaca.StartX = startX
            self.alpaca.StartY = startY
            self.alpaca.NumX = self.alpaca.CameraXSize // self.alpaca.BinX
            self.alpaca.NumY = self.alpaca.CameraYSize // self.alpaca.BinY

            self.alpaca.StartExposure(exposure, True)

            state_device = self.observatory.state.get_device(self.id)
            state_device.last_exposure_duration = exposure
            state_device.last_exposure_start_time = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())

            while not self.alpaca.ImageReady:
                sleep(0.5)
            
            img = self.alpaca.ImageArray
            imginfo = self.alpaca.ImageArrayInfo

            from alpaca.camera import ImageArrayElementTypes
            if imginfo.ImageElementType == ImageArrayElementTypes.Int32:
                if self.alpaca.MaxADU <= 65535:
                    imgDataType = np.uint16
                else:
                    imgDataType = np.int32
            elif imginfo.ImageElementType == ImageArrayElementTypes.Double:
                imgDataType = np.float64
            else:
                imgDataType = np.uint16

            if imginfo.Rank == 2:
                nda = np.array(img, dtype=imgDataType).transpose()
            else:
                nda = np.array(img, dtype=imgDataType).transpose(2, 1, 0)

            hdr = fits.Header()
            if imgDataType == np.uint16:
                hdr['BZERO'] = 32768.0
                hdr['BSCALE'] = 1.0
            hdr['EXPOSURE'] = exposure
            hdr['EXPTIME'] = exposure
            hdr['DATE-OBS'] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
            hdr['TIMESYS'] = 'UTC'
            hdr['XBINNING'] = self.alpaca.BinX
            hdr['YBINNING'] = self.alpaca.BinY
            hdr['INSTRUME'] = self.name
            try:
                hdr['GAIN'] = self.alpaca.Gain
            except:
                pass
            try:
                hdr['OFFSET'] = self.alpaca.Offset
                if type(self.alpaca.Offset) == int:
                    hdr['PEDESTAL'] = self.alpaca.Offset
            except:
                pass
            hdr['HISTORY'] = 'Created using Alpaquero'
            # hdr['OBJECT'] = sun ?
            # hdr['TELESCOP'] = Solar HRSS
            # hdr['OBSERVER'] = 'patrol'
            hdr['CCDTEMP'] = self.alpaca.CCDTemperature

            return nda, hdr
        except Exception as e:
            raise CameraError(code="camera_expose_failed", message=f"Error exposing with camera {self.alpaquero.name}: {e}")

    @ActionRegistry.register("create_fits", observatory_arg=False, action_type="device")
    def create_fits(
        self,
        nda,
        hdr,
        additional_headers: dict,
        base_path: str,
        file_suffix: str | None = None,
        folder: str | None = None,
    ):
        try:
            for k, v in additional_headers.items():
                hdr[k] = v

            timestamp = time.strftime('%Y%m%d_%H%M%S', time.gmtime())
            date_folder = time.strftime('%Y-%m-%d', time.gmtime())

            output_dir = Path(base_path) / date_folder

            if folder:
                # Optional: avoids accidental nested/absolute paths if folder is user-supplied
                folder = Path(folder).name
                output_dir = output_dir / folder

            output_dir.mkdir(parents=True, exist_ok=True)

            instrument = hdr['INSTRUME']

            if file_suffix:
                filename = output_dir / f"{instrument}_{timestamp}_{file_suffix}.fits"
            else:
                filename = output_dir / f"{instrument}_{timestamp}.fits"

            hdu = fits.PrimaryHDU(nda, header=hdr)
            hdu.writeto(filename, overwrite=True)

            return str(filename)

        except Exception as e:
            raise CameraError(
                code="fits_creation_failed",
                message=f"Error creating FITS file for camera {self.alpaquero.name}: {e}"
            )

    @ActionRegistry.register("expose_and_save_camera", observatory_arg=False, action_type="device")
    def expose_and_save(self, exposure: float, base_path: str = None, binX: int = 1, binY: int = 1, additional_headers: dict = None, file_suffix: str = None, folder: str = None):
        if base_path is None:
            base_path = self.observatory.base_path
        nda, hdr = self.expose(exposure, binX, binY)
        filename = self.create_fits(nda, hdr, additional_headers or {}, base_path, file_suffix, folder)
        self.observatory.state.set_message(
            f"camera_capture:{self.id}",
            f"Image captured and saved to {filename}",
        )
        return filename

    async def trigger_expose_and_save(self, exposure: float, base_path: str, binX: int = 1, binY: int = 1, additional_headers: dict = None, file_suffix: str = None, folder: str = None):
        self.dispatch_trigger(
            self.expose_and_save,
            exposure,
            base_path,
            binX,
            binY,
            additional_headers,
            file_suffix,
            folder
        )

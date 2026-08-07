import logging
from observatory.action_registry import ActionRegistry
from observatory.devices.base import ObservatoryDevice
from alpaquero.alpaquero import Alpaquero
from alpaca import camera
from observatory.errors import CameraError
from time import sleep
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable
import numpy as np
import astropy.io.fits as fits
from pathlib import Path
from observatory.error_handler import handle_error

logger = logging.getLogger(__name__)


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
            current_temp = self.alpaca.CCDTemperature
            conditions_device_id = next(iter(self.observatory.observing_conditions), None)
            conditions_device = (
                self.observatory.state.get_device(conditions_device_id)
                if conditions_device_id else None
            )
            env_temp = conditions_device.ambient if conditions_device else 15
            step = 5
            while current_temp < env_temp:
                next_temp = min(current_temp + step, env_temp)
                action = (
                    f"Warming up {self.alpaquero.name}: "
                    f"{current_temp:.1f}C -> {next_temp:.1f}C"
                )
                self.observatory.state.add_action(action)
                self.alpaca.SetCCDTemperature = next_temp

                while True:
                    current_temp = self.alpaca.CCDTemperature
                    if current_temp >= next_temp - 1:
                        break
                    sleep(10)

                self.observatory.state.remove_action(action)
            self.alpaca.CoolerOn = False

        except Exception as e:
            raise CameraError(
                code="camera_warmup_failed",
                message=f"Error warming up camera {self.alpaquero.name}: {e}"
            )

    @ActionRegistry.register(
        "expose_camera",
        observatory_arg=False,
        action_type="device",
        primary="exposure",
    )
    def expose(self, exposure: float, binX: int = 1, binY: int = 1, startX: int = 0, startY: int = 0):
        try:

            self.alpaca.BinX = binX
            self.alpaca.BinY = binY
            self.alpaca.StartX = startX
            self.alpaca.StartY = startY
            self.alpaca.NumX = self.alpaca.CameraXSize // self.alpaca.BinX
            self.alpaca.NumY = self.alpaca.CameraYSize // self.alpaca.BinY

            timestamp_before = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")
            logger.info("Time before exposure start: %s", timestamp_before)
            self.alpaca.StartExposure(exposure, True)
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")
            logger.info("Time after exposure start: %s", timestamp)

            state_device = self.observatory.state.get_device(self.id)
            state_device.last_exposure_duration = exposure
            state_device.last_exposure_start_time = timestamp

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
            else:
                hdr['BZERO'] = 0.0
                hdr['BSCALE'] = 1.0
            hdr['EXPOSURE'] = exposure
            hdr['EXPTIME'] = exposure
            hdr['DATE-OBS'] = timestamp
            hdr['TIMESYS'] = 'UTC'
            hdr['XBINNING'] = self.alpaca.BinX
            hdr['YBINNING'] = self.alpaca.BinY
            hdr['INSTRUME'] = self.name
            try:
                hdr['GAIN'] = self.alpaca.Gain
                hdr['EGAIN'] = self.alpaca.ElectronsPerADU
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
            hdr['TELESCOP'] = self.observatory.instrument_registry.get_by_device(self.id)[0].telescope if self.observatory.instrument_registry.get_by_device(self.id) else "Unknown"
            # hdr['OBSERVER'] = 'patrol' -> from user management
            hdr['OBSERVAT'] = self.observatory.name
            hdr['SITELAT'] = self.observatory.latitude
            hdr['SITELON'] = self.observatory.longitude
            hdr['SETTEMP'] = self.alpaca.SetCCDTemperature
            hdr['CCDTEMP'] = self.alpaca.CCDTemperature
            hdr['XPIXSZ'] = self.alpaca.PixelSizeX
            hdr['YPIXSZ'] = self.alpaca.PixelSizeY
            hdr['XORGSUBF'] = self.alpaca.StartX
            hdr['YORGSUBF'] = self.alpaca.StartY
            hdr['READOUTM'] = self.alpaca.ReadoutModes[self.alpaca.ReadoutMode]

            instrument = self.observatory.instrument_registry.get_by_device(self.id)[0] if self.observatory.instrument_registry.get_by_device(self.id) else None
            if instrument:
                devices = {
                    device_type: device_id
                    for device in instrument.devices
                    for device_type, device_id in device.items()
                }

                filterwheel_id = devices.get("filterwheel")
                if filterwheel_id:
                    filterwheel = self.observatory.filterwheels[filterwheel_id]
                    try:
                        filter_position = filterwheel.alpaca.Position
                        hdr['FILTNAME'] = filterwheel.name
                        hdr['FILTER'] = filterwheel.alpaca.Names[filter_position]
                    except Exception as e:
                        handle_error(e, f"{instrument.name} filterwheel {filterwheel.name} error, omitting FITS header values", level="warning")

                # ['IMAGETYP'] = str: Lightframe / Dark / Flat -> google for standard
                hdr['FOCALLEN'] = instrument.focal_length if instrument else "Unknown"
                hdr['APTDIA'] = instrument.aperture_diameter if instrument else "Unknown"
                hdr['APTAREA'] = instrument.aperture_area if instrument else "Unknown"

                
            # ['EGAIN'] = from camera driver electric
            
                if "telescope" in devices:
                    try:
                        telescope_device = self.observatory.telescopes[devices["telescope"]]
                        hdr['OBJCTRA'] = telescope_device.alpaca.RightAscension
                        hdr['OBJCTDEC'] = telescope_device.alpaca.Declination
                        hdr['OBJCTALT'] = telescope_device.alpaca.Altitude
                        hdr['OBJCTAZ'] = telescope_device.alpaca.Azimuth
                        # ['OBJCTHA'] = str: from telescope?

                        hdr['PIERSIDE'] = telescope_device.alpaca.SideOfPier
                    except Exception as e:
                        handle_error(e, f"{instrument.name} telescope {devices['telescope']} error, omitting FITS header values", level="warning")
            
            # ['FOCUSPOS'] = number (if focuser present)
            # ['FOCUSSSZ'] = step size
            # ['FOCUSTEM'] = focuser temp
            # ['JD'] = julianisches datum
            # ['FLIPSTAT']

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
        preview: bool = True,
        night_folder: bool = True
    ):
        try:
            for k, v in additional_headers.items():
                hdr[k] = v

            timestamp = time.strftime('%Y%m%d_%H%M%S', time.gmtime())

            # roll over date timestamp at noon UTC next day
            if night_folder:
                # If current time is before noon UTC, use previous day
                now = time.gmtime()
                if now.tm_hour < 12:
                    previous_day = time.gmtime(time.mktime(now) - 86400)  # subtract one day
                    date_folder = time.strftime('%Y-%m-%d', previous_day)
                else:
                    date_folder = time.strftime('%Y-%m-%d', now)
            else:
                date_folder = time.strftime('%Y-%m-%d', time.gmtime())

            output_dir = Path(base_path) / date_folder

            if folder:
                output_dir = output_dir / folder

            output_dir.mkdir(parents=True, exist_ok=True)

            instrument = hdr['INSTRUME']

            if file_suffix:
                filename = output_dir / f"{instrument}_{timestamp}_{file_suffix}.fits"
            else:
                filename = output_dir / f"{instrument}_{timestamp}.fits"

            hdu = fits.PrimaryHDU(nda, header=hdr)
            hdu.writeto(filename, overwrite=True)

            if preview:
                self.observatory.add_capture_preview(
                    name=filename.name,
                    img=nda,
                    timestamp=timestamp
                )

            return str(filename)

        except Exception as e:
            raise CameraError(
                code="fits_creation_failed",
                message=f"Error creating FITS file for camera {self.alpaquero.name}: {e}"
            )

    @ActionRegistry.register(
        "expose_and_save_camera",
        observatory_arg=False,
        action_type="device",
        primary="exposure",
    )
    def expose_and_save(self, exposure: float, base_path: str = None, binX: int = 1, binY: int = 1, additional_headers: dict = None, file_suffix: str = None, folder: str = None, preview: bool = True, night_folder: bool = True):
        if base_path is None:
            base_path = self.observatory.base_path
        nda, hdr = self.expose(exposure, binX, binY)
        filename = self.create_fits(nda, hdr, additional_headers or {}, base_path, file_suffix, folder, preview=preview, night_folder=night_folder)
        self.observatory.state.set_message(
            f"camera_capture:{self.id}",
            f"Image captured and saved to {filename}",
        )
        return filename

    async def trigger_expose_and_save(self, exposure: float, base_path: str, binX: int = 1, binY: int = 1, additional_headers: dict = None, file_suffix: str = None, folder: str = None, preview: bool = True, night_folder: bool = True):
        self.dispatch_trigger(
            self.expose_and_save,
            exposure,
            base_path,
            binX,
            binY,
            additional_headers,
            file_suffix,
            folder,
            preview,
            night_folder=night_folder
        )

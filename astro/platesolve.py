from observatory.action_registry import ActionRegistry
from pathlib import Path
import pythoncom, gc
import win32com.client

@ActionRegistry.register("pinpoint", observatory_arg=False, action_type="analysis")
def pinpoint(
        fits_path: str | Path,
        catalog: int,
        catalog_path: str,
        ra: float,
        dec: float,
        arcsec_per_pixel: float | None = None,
):
    pythoncom.CoInitialize()

    plate = win32com.client.Dispatch("PinPoint.Plate")

    try:
        plate.AttachFITS(str(fits_path))

        # plate.SigmaAboveMean = 4.0
        # plate.MinimumBrightness = 200
        # plate.MinimumStarSize = 2

        plate.ArcsecPerPixelHoriz = arcsec_per_pixel or 1.0
        plate.ArcsecPerPixelVert = arcsec_per_pixel or 1.0

        plate.RightAscension = ra
        plate.Declination = dec

        plate.Catalog = catalog
        plate.CatalogPath = str(catalog_path)

        plate.Solve()

        plate.UpdateFITS()

        result = {
            "ra_hours": float(plate.RightAscension),
            "dec_degrees": float(plate.Declination),
            "position_angle": float(plate.PositionAngle),
            "arcsec_per_pixel_x": float(plate.ArcsecPerPixelHoriz),
            "arcsec_per_pixel_y": float(plate.ArcsecPerPixelVert),
        }

        try:
            result["stars_detected"] = int(plate.ImageStars.Count)
        except Exception:
            result["stars_detected"] = None

        return result
    
    finally:
        try:
            plate.DetachFITS()
        except Exception:
            pass
        del plate
        gc.collect()
        pythoncom.CoUninitialize()
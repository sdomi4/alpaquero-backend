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

@ActionRegistry.register("pinpoint_folder", observatory_arg=False, action_type="analysis")
def pinpoint_folder(
        folder_path: str | Path,
        catalog: int,
        catalog_path: str,
        ra: float,
        dec: float,
        arcsec_per_pixel: float | None = None,
        glob: str = "*.fits"
):
    folder_path = Path(folder_path)
    print("looking for files in", folder_path, "with glob", glob)
    print("files in folder", list(folder_path.glob(".fit")))
    fits_files = list(folder_path.glob(glob))

    print("pinpointing files:", fits_files)
    results = []

    for fits_file in fits_files:
        result = pinpoint(
            fits_path=fits_file,
            catalog=catalog,
            catalog_path=catalog_path,
            ra=ra,
            dec=dec,
            arcsec_per_pixel=arcsec_per_pixel
        )
        print(result)
        results.append({
            "file": str(fits_file),
            "result": result
        })
    return results
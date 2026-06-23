from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from observatory.observatory import Observatory
from observatory.action_registry import ActionRegistry
from pathlib import Path

from astropy.nddata import CCDData
from astropy.stats import mad_std
import os, time
import ccdproc as ccdp
import numpy as np
from astropy import units as u

def _inv_median(a):
    return 1 / np.median(a)

@ActionRegistry.register("create_master_dark", observatory_arg=True, action_type="calibration")
def create_mdark(
        calibrated_path: Path | str,
        output_filename: str,
        base_path: Path | str = None,
        output_folder: str = None,
        dark_glob: str = None,
        method: str = "average",
        sigma_clip: bool = False,
        sigma_clip_low_thresh: float = 5,
        sigma_clip_high_thresh: float = 5,
        observatory: 'Observatory' = None
    ):
    print("calibrated path:", calibrated_path)
    if type(calibrated_path) == str:
        calibrated_path = Path(os.path.dirname(calibrated_path))
        print("fixed path?", calibrated_path)

    if base_path is None:
        base_path = observatory.base_path

    date_folder = time.strftime('%Y-%m-%d', time.gmtime())

    output_path = Path(base_path) / date_folder / output_folder
    output_path.mkdir(parents=True, exist_ok=True)

    dark_images = ccdp.ImageFileCollection(location=calibrated_path, glob_include=dark_glob)
    print(dark_images.files)
    dark_ccds = []
    
    for ccd, file_name in dark_images.ccds(ccd_kwargs={"unit": "adu"}, return_fname=True):
        dark_ccds.append(ccd)

    combined_dark = ccdp.combine(
        dark_ccds,
        method=method,
        sigma_clip=sigma_clip,
        sigma_clip_low_thresh=sigma_clip_low_thresh,
        sigma_clip_high_thresh=sigma_clip_high_thresh,
    )

    combined_dark.meta["combined"] = True

    combined_dark.write(output_path / output_filename, overwrite=True)

    return str(output_path) + "/" + output_filename

@ActionRegistry.register("calibrate_flats", observatory_arg=True, action_type="calibration")
def calibrate_flats(
        raw_flats_path: Path | str,
        master_dark_path: Path | str,
        output_filename: str,
        raw_flat_glob: str = None,
        base_path: Path | str = None,
        output_folder: str = None,
        method: str = "average",
        sigma_clip: bool = True,
        sigma_clip_low_thresh: float = 5,
        sigma_clip_high_thresh: float = 5,
        save_subtracted_flats: bool = False,
        observatory: 'Observatory' = None
    ):
    print(raw_flats_path)
    if type(raw_flats_path) == str:
        raw_flats_path = Path(os.path.dirname(raw_flats_path))
    if base_path is None:
        base_path = observatory.base_path
    
    date_folder = time.strftime('%Y-%m-%d', time.gmtime())
    output_path = Path(base_path) / date_folder / output_folder
    output_path.mkdir(parents=True, exist_ok=True)
    
    if type(master_dark_path) == str:
        master_dark_path = Path(master_dark_path)

    masterdark_filename = os.path.basename(master_dark_path)

    raw_flats = ccdp.ImageFileCollection(location=raw_flats_path, glob_include=raw_flat_glob)

    subtracted_flats = []
    for ccd, file_name in raw_flats.ccds(ccd_kwargs={"unit": "adu"}, return_fname=True):

        ccd = ccdp.subtract_dark(ccd=ccd, master=CCDData.read(master_dark_path, unit=u.adu), exposure_time="exptime", exposure_unit=u.second)
        subtracted_flats.append(ccd)
        if save_subtracted_flats:
            subtracted_filename = f"subtracted_{file_name}"
            ccd.meta["HISTORY"] = f"Subtracted master dark {masterdark_filename}"
            ccd.write(output_path / subtracted_filename, overwrite=True)

    combined_flat = ccdp.combine(
        subtracted_flats,
        method=method,
        scale=_inv_median,
        sigma_clip=sigma_clip,
        sigma_clip_low_thresh=sigma_clip_low_thresh,
        sigma_clip_high_thresh=sigma_clip_high_thresh,
        sigma_clip_func=np.ma.median,
        sigma_clip_dev_func=mad_std
    )

    combined_flat.meta["combined"] = True
    combined_flat.meta["HISTORY"] = f"Calibrated with master dark {masterdark_filename}"

    combined_flat.write(output_path / output_filename, overwrite=True)
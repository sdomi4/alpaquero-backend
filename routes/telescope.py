from fastapi import APIRouter, HTTPException, Depends
from observatory.error_handler import handle_error
from observatory.safety import safety_override
from observatory.observatory import Observatory
from routes import get_observatory
from astro.astro_catalog import get_sun_position, get_moon_position

router = APIRouter(prefix="/telescope", tags=["telescope"])

@router.post("/{telescope_id}/startup")
async def telescope_startup(
    telescope_id: str,
    observatory: Observatory = Depends(get_observatory)
):
    try:
        observatory.telescopes[telescope_id].connect()
    except Exception as e:
        message = handle_error(e, f"Error connecting to telescope {telescope_id}", level="error")
        raise HTTPException(status_code=500, detail=message)
    
@router.post("/{telescope_id}/shutdown")
async def telescope_shutdown(
    telescope_id: str,
    observatory: Observatory = Depends(get_observatory)
):
    try:
        observatory.telescopes[telescope_id].disconnect()
    except Exception as e:
        message = handle_error(e, f"Error disconnecting from telescope {telescope_id}", level="error")
        raise HTTPException(status_code=500, detail=message)
    
@router.post("/{telescope_id}/park")
async def telescope_park(
    telescope_id: str,
    override: bool = Depends(safety_override),
    observatory: Observatory = Depends(get_observatory)
):
    try:
        await observatory.telescopes[telescope_id].trigger_park(override=override)
    except Exception as e:
        message = handle_error(e, f"Error parking telescope {telescope_id}", level="error")
        raise HTTPException(status_code=500, detail=message)
    
@router.post("/{telescope_id}/unpark")
async def telescope_unpark(
    telescope_id: str,
    override: bool = Depends(safety_override),
    observatory: Observatory = Depends(get_observatory)
):
    try:
        await observatory.telescopes[telescope_id].trigger_unpark(override=override)
    except Exception as e:
        message = handle_error(e, f"Error unparking telescope {telescope_id}", level="error")
        raise HTTPException(status_code=500, detail=message)
    
@router.post("/{telescope_id}/slew/{ra}/{dec}")
async def telescope_slew(
    telescope_id: str,
    ra: float,
    dec: float,
    override: bool = Depends(safety_override),
    observatory: Observatory = Depends(get_observatory)
):
    try:
        await observatory.telescopes[telescope_id].trigger_slew(ra, dec, override=override)
    except Exception as e:
        message = handle_error(e, f"Error slewing telescope {telescope_id}", level="error")
        raise HTTPException(status_code=500, detail=message)

@router.post("/{telescope_id}/slew/sun")
async def slew_to_sun(
    telescope_id: str,
    override: bool = Depends(safety_override),
    observatory: Observatory = Depends(get_observatory)
):
    try:
        position = get_sun_position()
        await observatory.telescopes[telescope_id].trigger_slew(position["ra"], position["dec"], override=override)
        return
    except Exception as e:
        message = handle_error(e, f"Error slewing to sun with telescope {telescope_id}", level="error")
        raise HTTPException(status_code=500, detail=message)
    
@router.post("/{telescope_id}/trackingrate/{rate}")
async def set_tracking_rate(
    telescope_id: str,
    rate: int,
    override: bool = Depends(safety_override),
    observatory: Observatory = Depends(get_observatory)
):
    try:
        observatory.telescopes[telescope_id].tracking_rate(rate)
    except Exception as e:
        message = handle_error(e, f"Error setting tracking rate for {telescope_id}", level="error")
        raise HTTPException(status_code=500, detail=message)
from fastapi import APIRouter, HTTPException, Depends
from observatory.error_handler import handle_error
from observatory.safety import safety_override
from observatory.observatory import Observatory
from routes import get_observatory

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

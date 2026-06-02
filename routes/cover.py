from fastapi import APIRouter, HTTPException, Depends
from observatory.error_handler import handle_error
from observatory.safety import safety_override
from observatory.observatory import Observatory
from routes import get_observatory

router = APIRouter(prefix="/cover", tags=["cover"])

@router.post("/{cover_id}/startup")
async def cover_startup(
    cover_id: str,
    observatory: Observatory = Depends(get_observatory)
):
    try:
        observatory.covers[cover_id].connect()
    except Exception as e:
        message = handle_error(e, f"Error connecting to cover {cover_id}", level="error")
        raise HTTPException(status_code=500, detail=message)
    
@router.post("/{cover_id}/shutdown")
async def cover_shutdown(
    cover_id: str,
    observatory: Observatory = Depends(get_observatory)
):
    try:
        observatory.covers[cover_id].disconnect()
    except Exception as e:
        message = handle_error(e, f"Error disconnecting from cover {cover_id}", level="error")
        raise HTTPException(status_code=500, detail=message)
    
@router.post("/{cover_id}/open")
async def cover_open(
    cover_id: str,
    override: bool = Depends(safety_override),
    observatory: Observatory = Depends(get_observatory)
):
    try:
        await observatory.covers[cover_id].trigger_open(override=override)
    except Exception as e:
        message = handle_error(e, f"Error opening cover {cover_id}", level="error")
        raise HTTPException(status_code=500, detail=message)
    
@router.post("/{cover_id}/close")
async def cover_close(
    cover_id: str,
    override: bool = Depends(safety_override),
    observatory: Observatory = Depends(get_observatory)
):
    try:
        await observatory.covers[cover_id].trigger_close(override=override)
    except Exception as e:
        message = handle_error(e, f"Error closing cover {cover_id}", level="error")
        raise HTTPException(status_code=500, detail=message)

@router.post("/{cover_id}/calibrator/on/{brightness}")
async def cover_calibrator_on(
    cover_id: str,
    brightness: int,
    observatory: Observatory = Depends(get_observatory)
):
    try:
        observatory.covers[cover_id].enable_calibrator(brightness=brightness)
    except Exception as e:
        message = handle_error(e, f"Error enabling calibrator on cover {cover_id}", level="error")
        raise HTTPException(status_code=500, detail=message)
    
@router.post("/{cover_id}/calibrator/off")
async def cover_calibrator_off(
    cover_id: str,
    observatory: Observatory = Depends(get_observatory)
):
    try:
        observatory.covers[cover_id].disable_calibrator()
    except Exception as e:
        message = handle_error(e, f"Error disabling calibrator on cover {cover_id}", level="error")
        raise HTTPException(status_code=500, detail=message)

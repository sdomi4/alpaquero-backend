from fastapi import APIRouter, HTTPException, Depends
from observatory.error_handler import handle_error
from observatory.safety import safety_override
from observatory.observatory import Observatory
from routes import get_observatory

router = APIRouter(prefix="/dome", tags=["dome"])

@router.post("/{dome_id}/startup")
async def dome_startup(
    dome_id: str,
    observatory: Observatory = Depends(get_observatory)
):
    try:
        observatory.domes[dome_id].connect()
    except Exception as e:
        message = handle_error(e, f"Error connecting to dome {dome_id}", level="error")
        raise HTTPException(status_code=500, detail=message)
    
@router.post("/{dome_id}/shutdown")
async def dome_shutdown(
    dome_id: str,
    observatory: Observatory = Depends(get_observatory)
):
    try:
        observatory.domes[dome_id].disconnect()
    except Exception as e:
        message = handle_error(e, f"Error disconnecting from dome {dome_id}", level="error")
        raise HTTPException(status_code=500, detail=message)
    
@router.post("/{dome_id}/open")
async def dome_open(
    dome_id: str,
    override: bool = Depends(safety_override),
    observatory: Observatory = Depends(get_observatory)
):
    try:
        await observatory.domes[dome_id].trigger_open(override=override)
    except Exception as e:
        message = handle_error(e, f"Error opening dome {dome_id}", level="error")
        raise HTTPException(status_code=500, detail=message)
    
@router.post("/{dome_id}/close")
async def dome_close(
    dome_id: str,
    override: bool = Depends(safety_override),
    observatory: Observatory = Depends(get_observatory)
):
    try:
        await observatory.domes[dome_id].trigger_close(override=override)
    except Exception as e:
        message = handle_error(e, f"Error closing dome {dome_id}", level="error")
        raise HTTPException(status_code=500, detail=message)

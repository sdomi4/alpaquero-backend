from fastapi import APIRouter, HTTPException, Depends
from observatory.error_handler import handle_error
from observatory.observatory import Observatory
from routes import get_observatory

router = APIRouter(prefix="/safety", tags=["safety"])

@router.post("/{safety_id}/startup")
async def safety_startup(
    safety_id: str,
    observatory: Observatory = Depends(get_observatory)
):
    try:
        observatory.safety_monitors[safety_id].connect()
    except Exception as e:
        message = handle_error(e, f"Error connecting to safety monitor {safety_id}", level="error")
        raise HTTPException(status_code=500, detail=message)
    
@router.post("/{safety_id}/shutdown")
async def safety_shutdown(
    safety_id: str,
    observatory: Observatory = Depends(get_observatory)
):
    try:
        observatory.safety_monitors[safety_id].disconnect()
    except Exception as e:
        message = handle_error(e, f"Error disconnecting from safety monitor {safety_id}", level="error")
        raise HTTPException(status_code=500, detail=message)

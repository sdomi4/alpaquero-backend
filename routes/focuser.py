from fastapi import APIRouter, HTTPException, Depends
from observatory.observatory import Observatory
from observatory.error_handler import handle_error
from routes import get_observatory

router = APIRouter(prefix="/focuser", tags=["focuser"])

@router.post("/{focuser_id}/startup")
async def focuser_startup(
    focuser_id: str,
    observatory: Observatory = Depends(get_observatory)
):
    try:
        observatory.focusers[focuser_id].connect()
    except Exception as e:
        message = handle_error(e, f"Error connecting to focuser {focuser_id}", level="error")
        raise HTTPException(status_code=500, detail=message)
    
@router.post("/{focuser_id}/shutdown")
async def focuser_shutdown(
    focuser_id: str,
    observatory: Observatory = Depends(get_observatory)
):
    try:
        observatory.focusers[focuser_id].disconnect()
    except Exception as e:
        message = handle_error(e, f"Error disconnecting from focuser {focuser_id}", level="error")
        raise HTTPException(status_code=500, detail=message)
    
@router.post("/{focuser_id}/move/{position}")
async def focuser_move(
    focuser_id: str,
    position: int,
    observatory: Observatory = Depends(get_observatory)
):
    try:
        observatory.focusers[focuser_id].move(position)
    except Exception as e:
        message = handle_error(e, f"Error moving focuser {focuser_id} to position {position}", level="error")
        raise HTTPException(status_code=500, detail=message)
    
@router.post("/{focuser_id}/stop")
async def focuser_stop(
    focuser_id: str,
    observatory: Observatory = Depends(get_observatory)
):
    try:
        observatory.focusers[focuser_id].halt()
    except Exception as e:
        message = handle_error(e, f"Error stopping focuser {focuser_id}", level="error")
        raise HTTPException(status_code=500, detail=message)
    
@router.post("/{focuser_id}/move_increment/{increment}")
async def focuser_move_increment(
    focuser_id: str,
    increment: int,
    observatory: Observatory = Depends(get_observatory)
):
    try:
        observatory.focusers[focuser_id].move_by(increment)
    except Exception as e:
        message = handle_error(e, f"Error moving focuser {focuser_id} by increment {increment}", level="error")
        raise HTTPException(status_code=500, detail=message)
from fastapi import APIRouter, HTTPException, Depends
from observatory.error_handler import handle_error
from observatory.observatory import Observatory
from routes import get_observatory

router = APIRouter(prefix="/filterwheel", tags=["filterwheel"])

@router.post("/{filterwheel_id}/startup")
async def filterwheel_startup(
    filterwheel_id: str,
    observatory: Observatory = Depends(get_observatory)
):
    try:
        observatory.filterwheels[filterwheel_id].connect()
    except Exception as e:
        message = handle_error(e, f"Error connecting to filterwheel {filterwheel_id}", level="error")
        raise HTTPException(status_code=500, detail=message)
    
@router.post("/{filterwheel_id}/shutdown")
async def filterwheel_shutdown(
    filterwheel_id: str,
    observatory: Observatory = Depends(get_observatory)
):
    try:
        observatory.filterwheels[filterwheel_id].disconnect()
    except Exception as e:
        message = handle_error(e, f"Error disconnecting from filterwheel {filterwheel_id}", level="error")
        raise HTTPException(status_code=500, detail=message)

@router.post("/{filterwheel_id}/move/{position}")
async def move_filterwheel(
    filterwheel_id: str,
    position: int,
    observatory: Observatory = Depends(get_observatory)
):
    try:
        await observatory.filterwheels[filterwheel_id].trigger_move(position)
        return {"message": f"Filter wheel {filterwheel_id} moved to position {position}"}
    except Exception as e:
        message = handle_error(e, f"Error moving filterwheel {filterwheel_id}", level="error")
        raise HTTPException(status_code=500, detail=message)

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from observatory.error_handler import handle_error
from observatory.observatory import Observatory
from routes import get_observatory

router = APIRouter(prefix="/camera", tags=["camera"])

class CameraExposureRequest(BaseModel):
    exposure: float
    binX: int = 1
    binY: int = 1
    additional_headers: dict = {}
    file_suffix: str = None

@router.post("/{camera_id}/startup")
async def camera_startup(
    camera_id: str,
    observatory: Observatory = Depends(get_observatory)
):
    try:
        observatory.cameras[camera_id].connect()
    except Exception as e:
        message = handle_error(e, f"Error connecting to camera {camera_id}", level="error")
        raise HTTPException(status_code=500, detail=message)
    
@router.post("/{camera_id}/shutdown")
async def camera_shutdown(
    camera_id: str,
    observatory: Observatory = Depends(get_observatory)
):
    try:
        observatory.cameras[camera_id].disconnect()
    except Exception as e:
        message = handle_error(e, f"Error disconnecting from camera {camera_id}", level="error")
        raise HTTPException(status_code=500, detail=message)

@router.post("/{camera_id}/set_temperature/{target_temp}")
async def set_camera_temperature(
    camera_id: str,
    target_temp: float,
    observatory: Observatory = Depends(get_observatory)
):
    try:
        observatory.cameras[camera_id].cool(target_temp)
        return {"message": f"Camera {camera_id} cooling to {target_temp}C"}
    except Exception as e:
        message = handle_error(e, f"Error setting temperature for camera {camera_id}", level="error")
        raise HTTPException(status_code=500, detail=message)
    
@router.post("/{camera_id}/capture")
async def capture_image(
    camera_id: str,
    body: CameraExposureRequest,
    observatory: Observatory = Depends(get_observatory)
):
    try:
        await observatory.cameras[camera_id].trigger_expose_and_save(
            body.exposure,
            observatory.base_path,
            body.binX,
            body.binY,
            body.additional_headers,
            file_suffix=body.file_suffix,
            folder="alpaquero"
        )
        return {"message": f"Capture started for camera {camera_id}"}
    except Exception as e:
        message = handle_error(e, f"Error capturing image for camera {camera_id}", level="error")
        raise HTTPException(status_code=500, detail=message)

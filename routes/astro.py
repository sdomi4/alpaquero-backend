from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from observatory.error_handler import handle_error
from observatory.observatory import Observatory
from routes import get_observatory


router = APIRouter(prefix="/astro", tags=["astro"])

class PinpointRequest(BaseModel):
    folder_path: str
    glob: str = "*.fits"
    catalog: int = 11
    catalog_path: str = "C:\\Users\\thoma\\Documents\\Phoranso\\UCAC4"
    ra: float
    dec: float
    arcsec_per_pixel: float | None = None

@router.post("/pinpoint")
async def pinpoint_folder_endpoint(
    request: PinpointRequest,
    observatory: Observatory = Depends(get_observatory)
):
    try:
        result = observatory.astro.pinpoint_folder(
            folder_path=request.folder_path,
            catalog=request.catalog,
            catalog_path=request.catalog_path,
            ra=request.ra,
            dec=request.dec,
            arcsec_per_pixel=request.arcsec_per_pixel
        )
        return result
    except Exception as e:
        message = handle_error(e, "Error in pinpoint_folder", level="error")
        raise HTTPException(status_code=500, detail=message)
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from astro.pinpoint_jobs import pinpoint_job_manager
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


class PinpointJobCreated(BaseModel):
    job_id: str
    status: Literal[
        "queued", "running", "completed", "completed_with_errors", "failed"
    ]
    status_url: str
    total_files: int


class PinpointJobStatus(BaseModel):
    job_id: str
    status: Literal[
        "queued", "running", "completed", "completed_with_errors", "failed"
    ]
    folder_path: str
    glob: str
    total_files: int
    processed_files: int
    successful_files: int
    failed_files: int
    remaining_files: int
    current_file: str | None
    average_solve_time_seconds: float | None = Field(
        description="Mean duration of all file solve attempts completed so far."
    )
    estimated_remaining_seconds: float | None
    estimated_completion_at: datetime | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    results: list[dict[str, Any]]
    errors: list[dict[str, str]]
    error: str | None


@router.post(
    "/pinpoint",
    response_model=PinpointJobCreated,
    status_code=status.HTTP_202_ACCEPTED,
)
async def pinpoint_folder_endpoint(
    request: PinpointRequest,
    observatory: Observatory = Depends(get_observatory),
):
    try:
        job = pinpoint_job_manager.submit(
            folder_path=request.folder_path,
            glob=request.glob,
            catalog=request.catalog,
            catalog_path=request.catalog_path,
            ra=request.ra,
            dec=request.dec,
            arcsec_per_pixel=request.arcsec_per_pixel,
        )
        return {
            "job_id": job["job_id"],
            "status": job["status"],
            "status_url": f"/astro/pinpoint/{job['job_id']}",
            "total_files": job["total_files"],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        message = handle_error(e, "Error starting pinpoint job", level="error")
        raise HTTPException(status_code=500, detail=message)


@router.get("/pinpoint/{job_id}", response_model=PinpointJobStatus)
async def pinpoint_job_status(job_id: str):
    job = pinpoint_job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="PinPoint job not found")
    return job

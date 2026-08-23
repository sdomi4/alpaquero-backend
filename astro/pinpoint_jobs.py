import copy
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable
from uuid import uuid4

logger = logging.getLogger(__name__)

PinpointSolver = Callable[..., dict[str, Any]]


def _default_solver(**kwargs: Any) -> dict[str, Any]:
    # Keep the Windows-only COM dependency out of this module's import path so
    # the job bookkeeping can be tested independently.
    from astro.platesolve import pinpoint

    return pinpoint(**kwargs)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class PinpointJobParameters:
    folder_path: str
    glob: str
    catalog: int
    catalog_path: str
    ra: float
    dec: float
    arcsec_per_pixel: float | None


@dataclass
class PinpointJob:
    job_id: str
    parameters: PinpointJobParameters
    files: list[Path]
    status: str = "queued"
    created_at: datetime = field(default_factory=_utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    current_file: str | None = None
    processed_files: int = 0
    successful_files: int = 0
    failed_files: int = 0
    total_solve_time_seconds: float = 0.0
    results: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    error: str | None = None


class PinpointJobManager:
    """Runs PinPoint folder jobs without blocking API request handlers.

    PinPoint is a COM application, so jobs are deliberately serialized through a
    single worker. Progress is kept in memory and is therefore reset when the API
    process restarts.
    """

    def __init__(
        self,
        solver: PinpointSolver = _default_solver,
        *,
        max_retained_jobs: int = 100,
    ) -> None:
        self._solver = solver
        self._max_retained_jobs = max_retained_jobs
        self._jobs: dict[str, PinpointJob] = {}
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="pinpoint-job",
        )

    def submit(
        self,
        *,
        folder_path: str | Path,
        glob: str,
        catalog: int,
        catalog_path: str,
        ra: float,
        dec: float,
        arcsec_per_pixel: float | None,
    ) -> dict[str, Any]:
        folder = Path(folder_path)
        if not folder.is_dir():
            raise ValueError(f"Folder does not exist or is not a directory: {folder}")

        files = sorted(folder.glob(glob))
        parameters = PinpointJobParameters(
            folder_path=str(folder),
            glob=glob,
            catalog=catalog,
            catalog_path=catalog_path,
            ra=ra,
            dec=dec,
            arcsec_per_pixel=arcsec_per_pixel,
        )
        job = PinpointJob(
            job_id=str(uuid4()),
            parameters=parameters,
            files=files,
        )

        with self._lock:
            self._prune_finished_jobs()
            self._jobs[job.job_id] = job

        try:
            self._executor.submit(self._run_job, job.job_id)
        except Exception:
            with self._lock:
                self._jobs.pop(job.job_id, None)
            raise

        return self.get(job.job_id)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return self._snapshot(job)

    def shutdown(self, *, wait: bool = False) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=True)

    def _run_job(self, job_id: str) -> None:
        try:
            with self._lock:
                job = self._jobs[job_id]
                job.status = "running"
                job.started_at = _utc_now()

            for fits_file in job.files:
                with self._lock:
                    job.current_file = str(fits_file)

                solve_started = time.perf_counter()
                try:
                    result = self._solver(
                        fits_path=fits_file,
                        catalog=job.parameters.catalog,
                        catalog_path=job.parameters.catalog_path,
                        ra=job.parameters.ra,
                        dec=job.parameters.dec,
                        arcsec_per_pixel=job.parameters.arcsec_per_pixel,
                    )
                except Exception as exc:
                    duration = time.perf_counter() - solve_started
                    logger.error("PinPoint failed for %s: %s", fits_file, exc)
                    with self._lock:
                        job.failed_files += 1
                        job.processed_files += 1
                        job.total_solve_time_seconds += duration
                        job.errors.append({"file": str(fits_file), "error": str(exc)})
                else:
                    duration = time.perf_counter() - solve_started
                    logger.info("PinPoint result for %s: %s", fits_file, result)
                    with self._lock:
                        job.successful_files += 1
                        job.processed_files += 1
                        job.total_solve_time_seconds += duration
                        job.results.append({"file": str(fits_file), "result": result})

            with self._lock:
                job.current_file = None
                job.finished_at = _utc_now()
                job.status = (
                    "completed_with_errors" if job.failed_files else "completed"
                )
        except Exception as exc:
            logger.exception("PinPoint job %s failed", job_id)
            with self._lock:
                job = self._jobs[job_id]
                job.status = "failed"
                job.error = str(exc)
                job.current_file = None
                job.finished_at = _utc_now()

    def _snapshot(self, job: PinpointJob) -> dict[str, Any]:
        total_files = len(job.files)
        remaining_files = max(total_files - job.processed_files, 0)
        average_solve_time = (
            job.total_solve_time_seconds / job.processed_files
            if job.processed_files
            else None
        )
        estimated_remaining = (
            average_solve_time * remaining_files
            if job.status == "running" and average_solve_time is not None
            else (0.0 if job.status.startswith("completed") else None)
        )
        estimated_completion = (
            _utc_now() + timedelta(seconds=estimated_remaining)
            if estimated_remaining is not None and job.status == "running"
            else job.finished_at
        )

        return {
            "job_id": job.job_id,
            "status": job.status,
            "folder_path": job.parameters.folder_path,
            "glob": job.parameters.glob,
            "total_files": total_files,
            "processed_files": job.processed_files,
            "successful_files": job.successful_files,
            "failed_files": job.failed_files,
            "remaining_files": remaining_files,
            "current_file": job.current_file,
            "average_solve_time_seconds": average_solve_time,
            "estimated_remaining_seconds": estimated_remaining,
            "estimated_completion_at": estimated_completion,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "results": copy.deepcopy(job.results),
            "errors": copy.deepcopy(job.errors),
            "error": job.error,
        }

    def _prune_finished_jobs(self) -> None:
        overflow = len(self._jobs) - self._max_retained_jobs + 1
        if overflow <= 0:
            return

        finished = sorted(
            (job for job in self._jobs.values() if job.finished_at is not None),
            key=lambda job: job.finished_at,
        )
        for job in finished[:overflow]:
            self._jobs.pop(job.job_id, None)


pinpoint_job_manager = PinpointJobManager()

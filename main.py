from observatory.logging_setup import configure_logging, install_asyncio_exception_handler

configure_logging()

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from observatory.observatory import Observatory
from observatory.error_handler import handle_error, set_error_loop

# import routers
from routes.dome import router as dome_router
from routes.telescope import router as telescope_router
from routes.camera import router as camera_router
from routes.cover import router as cover_router
from routes.filterwheel import router as filterwheel_router
from routes.switch import router as switch_router
from routes.observing_conditions import router as observing_conditions_router
from routes.safety_monitor import router as safety_monitor_router
from routes.observatory import router as observatory_router
from routes.sequences import router as sequences_router
from routes.status import router as status_router
from routes.preview import router as preview_router
from routes.astro import router as astro_router
from routes.focuser import router as focuser_router
from routes.logs import router as logs_router


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up observatory")
    loop = asyncio.get_running_loop()
    set_error_loop(loop)
    install_asyncio_exception_handler(loop)
    try:
        observatory = Observatory()
        observatory.startup()
        app.state.observatory = observatory
    except Exception as e:
        handle_error(e, "Error during observatory startup", level="error")
        raise

    try:
        yield
    finally:
        logger.info("Shutting down observatory")
        try:
            await observatory.shutdown()
        except Exception as e:
            handle_error(e, "Error during observatory shutdown", level="error")
        finally:
            app.state.observatory = None


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(dome_router)
app.include_router(telescope_router)
app.include_router(camera_router)
app.include_router(cover_router)
app.include_router(filterwheel_router)
app.include_router(switch_router)
app.include_router(observing_conditions_router)
app.include_router(safety_monitor_router)
app.include_router(observatory_router)
app.include_router(sequences_router)
app.include_router(status_router)
app.include_router(preview_router)
app.include_router(astro_router)
app.include_router(focuser_router)
app.include_router(logs_router)

"""Observatory application package.

FastAPI dependencies live in :mod:`routes`; keeping package initialization
side-effect free allows logging to be configured before application imports.
"""

from collections.abc import AsyncGenerator
from typing import Any


async def get_observatory(request: Any) -> AsyncGenerator[Any, None]:
    """Backward-compatible dependency without eager application imports."""
    from observatory.safety import reset_current_observatory, set_current_observatory

    observatory = request.app.state.observatory
    token = set_current_observatory(observatory)
    try:
        yield observatory
    finally:
        reset_current_observatory(token)

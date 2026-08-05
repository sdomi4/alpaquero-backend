from typing import TYPE_CHECKING
import asyncio
import logging

if TYPE_CHECKING:
    from observatory.observatory import Observatory
    from observatory.state import StateManager

logger = logging.getLogger(__name__)

async def observatory_loop(state: "StateManager", observatory: "Observatory"):
    # dumb way to have all safety monitors concur for at least 5 unsafe readings sort of
    safety_threshold = 5 * observatory.safety_monitors.__len__() if observatory.safety_monitors else 5
    safety_counter = 0
    shutdown_triggered = False
    while True:
        if shutdown_triggered:
            await asyncio.sleep(1)
            pass
        # check safety condituions
        for safety_id, safety_monitor in observatory.safety_monitors.items():
            try:
                state_device = state.get_device(safety_id)
                if hasattr(state_device, 'safe'):
                    if state_device.safe is False:
                        logger.warning(
                            "Safety monitor %s reports unsafe conditions (count=%s)",
                            safety_id,
                            safety_counter,
                        )
                        safety_counter += 1
                        logger.info(
                            "Safety counter %s/%s",
                            safety_counter,
                            safety_threshold,
                        )
                    else:
                        safety_counter -= 1 if safety_counter > 0 else 0
            except ValueError:
                pass

        if safety_counter >= safety_threshold and not shutdown_triggered:
            shutdown_triggered = True
            logger.critical("Safety conditions triggered emergency shutdown")
            observatory.emergency_shutdown()
        await asyncio.sleep(1)

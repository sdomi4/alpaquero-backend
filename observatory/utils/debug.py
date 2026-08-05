from observatory.action_registry import ActionRegistry
import logging
import time

logger = logging.getLogger(__name__)

@ActionRegistry.register("debug_print", observatory_arg=False, action_type="debug")
def debug_print(message: str):
    logger.info("[DEBUG] %s", message)


@ActionRegistry.register("debug_sleep", observatory_arg=False, action_type="debug")
def debug_sleep(seconds: float):
    logger.info("[DEBUG] Sleeping for %s seconds", seconds)
    time.sleep(seconds)
    logger.info("[DEBUG] Done sleeping")

@ActionRegistry.register("debug_timestamp", observatory_arg=False, action_type="debug")
def debug_timestamp():
    # human readable timestamp
    logger.info(
        "[DEBUG] Current timestamp: %s",
        time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
    )

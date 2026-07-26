from typing import TYPE_CHECKING, Tuple
from observatory.condition_registry import ConditionRegistry

if TYPE_CHECKING:
    from observatory.observatory import Observatory


@ConditionRegistry.register("weather_is_safe")
async def weather_is_safe(observatory: "Observatory") -> Tuple[bool, str]:
    if not observatory.safety_monitors:
        return False, "No safety monitor configured"
    
    for safety_id, safety_monitor in observatory.safety_monitors.items():
        try:
            state_device = observatory.state.get_device(safety_id)
            if hasattr(state_device, 'safe'):
                if state_device.safe is True:
                    return True, ""
                else:
                    return False, f"Safety monitor {safety_id} reports unsafe conditions"
            else:
                return False, f"Safety monitor {safety_id} state unavailable"
        except ValueError:
            return False, f"Safety monitor {safety_id} not found in state"
    
    return False, "No safety monitor data available"


@ConditionRegistry.register("dome_is_open")
async def dome_is_open(observatory: "Observatory", dome_id: str = None) -> Tuple[bool, str]:
    if not observatory.domes:
        return False, "No dome configured"
    
    if dome_id is None:
        dome_id = next(iter(observatory.domes.keys()))
    
    if dome_id not in observatory.domes:
        return False, f"Dome {dome_id} not found"
    
    try:
        state_device = observatory.state.get_device(dome_id)
        if hasattr(state_device, 'shutter_status'):
            if state_device.shutter_status == 0:
                return True, ""
            else:
                return False, f"Dome {dome_id} is not open (status: {state_device.shutter_status})"
        else:
            return False, f"Dome {dome_id} shutter status unavailable"
    except ValueError:
        return False, f"Dome {dome_id} not found in state"
    
@ConditionRegistry.register("telescope_is_parked")
async def telescope_is_parked(observatory: "Observatory", telescope_id: str = None) -> Tuple[bool, str]:
    if not observatory.telescopes:
        return False, "No telescope configured"
    
    if telescope_id is None:
        telescope_id = next(iter(observatory.telescopes.keys()))
    
    if telescope_id not in observatory.telescopes:
        return False, f"Telescope {telescope_id} not found"
    
    try:
        state_device = observatory.state.get_device(telescope_id)
        if hasattr(state_device, 'parked'):
            if state_device.parked is True:
                return True, ""
            else:
                return False, f"Telescope {telescope_id} is not parked"
        else:
            return False, f"Telescope {telescope_id} parked status unavailable"
    except ValueError:
        return False, f"Telescope {telescope_id} not found in state"
    
@ConditionRegistry.register("covers_are_closed")
async def covers_are_closed(observatory: "Observatory", cover_ids: list = None) -> Tuple[bool, str]:
    if not observatory.covers:
        return False, "No covers configured"
    
    if cover_ids is None:
        cover_ids = list(observatory.covers.keys())
    
    for cover_id in cover_ids:
        if cover_id not in observatory.covers:
            return False, f"Cover {cover_id} not found"
        
        try:
            state_device = observatory.state.get_device(cover_id)
            if state_device.cover_status == 0:
                continue
            else:
                return False, f"Cover {cover_id} is not closed"

        except ValueError:
            return False, f"Cover {cover_id} not found in state"
    
    return True, ""

@ConditionRegistry.register("is_dark")
async def is_dark(observatory: "Observatory", conditions_id: str = None) -> Tuple[bool, str]:
    if not observatory.observing_conditions:
        return False, "No observing conditions monitor configured"
    
    if conditions_id is None:
        conditions_id = next(iter(observatory.observing_conditions.keys()))
    
    if conditions_id not in observatory.observing_conditions:
        return False, f"Observing conditions monitor {conditions_id} not found"
    
    try:
        state_device = observatory.state.get_device(conditions_id)
        if hasattr(state_device, 'daylight'):
            if state_device.daylight is not None and state_device.daylight > 50:  # Lux threshold for darkness
                return True, ""
            else:
                return False, f"Conditions monitor {conditions_id} reports it is not dark (daylight: {state_device.daylight} lux)"
        else:
            return False, f"Conditions monitor {conditions_id} daylight level unavailable"
    except ValueError:
        return False, f"Observing conditions monitor {conditions_id} not found in state"
    
async def must_override():
    return False, "Override required to proceed"

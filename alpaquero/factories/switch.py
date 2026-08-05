import logging
from alpaca import switch
from time import sleep

from observatory.state import StateManager, SwitchControlState, SwitchState, ToggleControl, RangeControl

logger = logging.getLogger(__name__)

class SwitchConnectionError(RuntimeError):
    pass


def _is_toggle_range(min_value: float, max_value: float, step: float) -> bool:
    return min_value == 0 and max_value == 1 and step == 1


def _call_optional(alpaca_switch: switch.Switch, method_name: str, switch_id: int, default):
    method = getattr(alpaca_switch, method_name, None)
    if method is None:
        return default
    try:
        return method(switch_id)
    except Exception:
        return default


def _control_key(controls: dict[str, SwitchControlState], switch_id: int, label: str | None) -> str:
    key = label or f"Switch {switch_id}"
    if key not in controls:
        return key

    suffix = 2
    while f"{key} ({suffix})" in controls:
        suffix += 1
    return f"{key} ({suffix})"


def enumerate_switch_controls(alpaca_switch: switch.Switch) -> dict[str, SwitchControlState]:
    controls: dict[str, SwitchControlState] = {}

    for switch_id in range(alpaca_switch.MaxSwitch):
        switch_name = _call_optional(alpaca_switch, "GetSwitchName", switch_id, f"Switch {switch_id}")
        description = _call_optional(alpaca_switch, "GetSwitchDescription", switch_id, None)
        can_write = _call_optional(alpaca_switch, "CanWrite", switch_id, False)
        can_async = _call_optional(alpaca_switch, "CanAsync", switch_id, False)
        min_value = _call_optional(alpaca_switch, "MinSwitchValue", switch_id, 0.0)
        max_value = _call_optional(alpaca_switch, "MaxSwitchValue", switch_id, 1.0)
        step = _call_optional(alpaca_switch, "SwitchStep", switch_id, 1.0)

        if _is_toggle_range(min_value, max_value, step):
            value = _call_optional(alpaca_switch, "GetSwitch", switch_id, False)
            control = ToggleControl(
                id=switch_id,
                label=switch_name,
                description=description,
                writeable=can_write,
                can_async=can_async,
                value=bool(value),
            )
        else:
            value = _call_optional(alpaca_switch, "GetSwitchValue", switch_id, min_value)
            control = RangeControl(
                id=switch_id,
                label=switch_name,
                description=description,
                writeable=can_write,
                can_async=can_async,
                min_value=min_value,
                max_value=max_value,
                step=step,
                value=value,
            )

        controls[_control_key(controls, switch_id, switch_name)] = control

    return controls


def switch_factory(
        address: str,
        id: str,
        device_number: int = 0,
        state: "StateManager" = None,
    ) -> switch.Switch:
    try:
        logger.info("Connecting to switch %s at %s", id, address)
        s = switch.Switch(address, device_number)
        timeout = 0
        s.Connect()
        while s.Connecting:
                timeout += 1
                if timeout > 10:
                    raise SwitchConnectionError("Switch connection timed out")
                sleep(1)
        
        controls = enumerate_switch_controls(s)
        
        state.add_device(SwitchState(id=id, connected=True, controls=controls))
        return s
    except Exception as e:
        logger.exception("Error connecting to switch %s", id)
        raise SwitchConnectionError(f"Error connecting to switch: {e}") from e

"""sensor_msgs converters."""

from fluxvla_data_collection.registry import register_converter


@register_converter("joint_state_named")
def joint_state_named(msg, spec, context):  # noqa: ARG001
    params = spec.get("params", {})
    joint_names = params.get("joint_names") or list(msg.name)
    outputs = spec.get("outputs") or {}
    result = {}

    field_map = {
        "qpos": "position",
        "position": "position",
        "qvel": "velocity",
        "velocity": "velocity",
        "effort": "effort",
    }
    for key, field_name in field_map.items():
        if key not in outputs:
            continue
        values = getattr(msg, field_name)
        result[outputs[key]] = [
            float(values[msg.name.index(joint_name)])
            for joint_name in joint_names
            if joint_name in msg.name and msg.name.index(joint_name) < len(values)
        ]

    if "output" in spec and not result:
        values = getattr(msg, params.get("field", "position"))
        result[spec["output"]] = [float(value) for value in values]
    return result


@register_converter("joy_fixed")
def joy_fixed(msg, spec, context):  # noqa: ARG001
    params = spec.get("params", {})
    button_count = int(params.get("button_count", len(msg.buttons)))
    axis_count = int(params.get("axis_count", len(msg.axes)))
    buttons = list(msg.buttons[:button_count])
    axes = list(msg.axes[:axis_count])
    if len(buttons) < button_count:
        buttons.extend([0] * (button_count - len(buttons)))
    if len(axes) < axis_count:
        axes.extend([0.0] * (axis_count - len(axes)))
    return {spec["output"]: [float(value) for value in buttons + axes]}

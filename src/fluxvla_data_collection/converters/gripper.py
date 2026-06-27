"""Gripper converters."""

from fluxvla_data_collection.registry import register_converter


@register_converter("gripper_joint_width")
def gripper_joint_width(msg, spec, context):  # noqa: ARG001
    if not msg.position:
        width = 0.0
    elif len(msg.position) >= 2:
        width = float(msg.position[0] + msg.position[1])
    else:
        width = float(msg.position[0])
    value = [width]
    if "output" in spec:
        return {spec["output"]: value}
    return {output: value for output in (spec.get("outputs") or {}).values()}


@register_converter("gripper_goal_width")
def gripper_goal_width(msg, spec, context):  # noqa: ARG001
    value = [float(msg.goal.width)]
    if "output" in spec:
        return {spec["output"]: value}
    return {output: value for output in (spec.get("outputs") or {}).values()}

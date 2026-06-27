"""Optional Franka converters."""

from fluxvla_data_collection.registry import register_converter


@register_converter("franka_state")
def franka_state(msg, spec, context):  # noqa: ARG001
    import numpy as np
    from tf.transformations import quaternion_from_matrix

    outputs = spec.get("outputs") or {}
    transform = np.array(msg.O_T_EE, dtype=np.float64).reshape((4, 4), order="F")
    quat = quaternion_from_matrix(transform)
    values = {
        "qpos": [float(value) for value in msg.q],
        "qvel": [float(value) for value in msg.dq],
        "effort": [float(value) for value in msg.tau_J],
        "eepose": [
            float(transform[0, 3]),
            float(transform[1, 3]),
            float(transform[2, 3]),
            float(quat[0]),
            float(quat[1]),
            float(quat[2]),
            float(quat[3]),
        ],
        "robot_mode": int(msg.robot_mode),
        "control_command_success_rate": float(msg.control_command_success_rate),
    }
    return {output: values[key] for key, output in outputs.items() if key in values}

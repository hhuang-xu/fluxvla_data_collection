"""Geometry message converters."""

from fluxvla_data_collection.registry import register_converter


@register_converter("pose_stamped_7d")
def pose_stamped_7d(msg, spec, context):  # noqa: ARG001
    return {
        spec["output"]: [
            float(msg.pose.position.x),
            float(msg.pose.position.y),
            float(msg.pose.position.z),
            float(msg.pose.orientation.x),
            float(msg.pose.orientation.y),
            float(msg.pose.orientation.z),
            float(msg.pose.orientation.w),
        ]
    }

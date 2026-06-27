"""Raw ROS message converter."""

import json

from fluxvla_data_collection.registry import register_converter
from fluxvla_data_collection.ros_types import ros_msg_to_dict


@register_converter("raw_rosmsg_json")
def raw_rosmsg_json(msg, spec, context):  # noqa: ARG001
    return {spec["output"]: json.dumps(ros_msg_to_dict(msg), ensure_ascii=False)}

"""std_msgs converters."""

from fluxvla_data_collection.registry import register_converter


@register_converter("float32")
def float32(msg, spec, context):  # noqa: ARG001
    return {spec["output"]: [float(msg.data)]}


@register_converter("string")
def string(msg, spec, context):  # noqa: ARG001
    return {spec["output"]: str(msg.data)}

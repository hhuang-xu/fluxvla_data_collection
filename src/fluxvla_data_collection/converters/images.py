"""Image converters."""

from fluxvla_data_collection.registry import register_converter


@register_converter("image_png")
def image_png(msg, spec, context):
    import cv2

    encoding = spec.get("encoding", "passthrough")
    image = context.bridge.imgmsg_to_cv2(msg, desired_encoding=encoding)
    ok, buffer = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("failed to encode image topic {} as PNG".format(spec["topic"]))
    return {spec["output"]: buffer.tobytes()}

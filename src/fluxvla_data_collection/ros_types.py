"""ROS message type helpers."""

import importlib


class RosTypeError(RuntimeError):
    pass


def resolve_msg_type(type_name):
    """Resolve 'sensor_msgs/Image' or 'sensor_msgs.msg.Image' to a class."""
    if not type_name:
        raise RosTypeError("empty ROS message type")

    if "/" in type_name:
        package, class_name = type_name.split("/", 1)
        module_name = "{}.msg".format(package)
    else:
        parts = type_name.split(".")
        if len(parts) < 2:
            raise RosTypeError("invalid ROS message type '{}'".format(type_name))
        module_name = ".".join(parts[:-1])
        class_name = parts[-1]

    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise RosTypeError("failed to import {}: {}".format(module_name, exc))

    try:
        return getattr(module, class_name)
    except AttributeError:
        raise RosTypeError("message class {} not found in {}".format(class_name, module_name))


def get_stamp(msg, fallback_time=None):
    header = getattr(msg, "header", None)
    stamp = getattr(header, "stamp", None)
    if stamp is not None:
        value = stamp.to_sec()
        if value > 0.0:
            return value
    if fallback_time is not None:
        return float(fallback_time)
    return None


def ros_msg_to_dict(value):
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [ros_msg_to_dict(item) for item in value]
    if hasattr(value, "to_sec"):
        return value.to_sec()
    slots = getattr(value, "__slots__", None)
    if slots:
        return {slot: ros_msg_to_dict(getattr(value, slot)) for slot in slots}
    return str(value)

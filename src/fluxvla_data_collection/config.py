"""YAML configuration loading and validation."""

import copy
import os

import yaml

from fluxvla_data_collection.registry import ConverterError, get_converter
from fluxvla_data_collection.ros_types import resolve_msg_type


class ConfigError(RuntimeError):
    pass


VALID_SYNC_MODES = {"required", "latest_before"}


def load_config(path):
    with open(path, "r", encoding="utf-8") as file_obj:
        config = yaml.safe_load(file_obj) or {}
    config["_config_path"] = os.path.abspath(path)
    return normalize_config(config)


def normalize_config(config):
    normalized = copy.deepcopy(config)
    normalized.setdefault("dataset", {})
    normalized.setdefault("sync", {})
    normalized.setdefault("control", {})
    normalized.setdefault("topics", [])
    normalized.setdefault("computed_columns", [])

    dataset = normalized["dataset"]
    dataset.setdefault("dataset_dir", "/tmp/fluxvla_data_collection")
    dataset.setdefault("task_name", "ros_topic_collection")
    dataset.setdefault("task_description", "")
    dataset.setdefault("station_idx", "default")
    dataset.setdefault("episode_idx", -1)
    dataset.setdefault("frame_rate", 30)
    dataset.setdefault("max_timesteps", 50000)
    dataset.setdefault("flush_every_n", 100)
    dataset.setdefault("drop_warning_factor", 1.5)
    dataset.setdefault("no_frame_warning_timeout", 1.0)
    dataset.setdefault("no_frame_warning_interval", 5.0)
    dataset.setdefault("camera_info_timeout", 5.0)

    sync = normalized["sync"]
    sync.setdefault("slop", 0.05)
    sync.setdefault("queue_size", 100)
    sync.setdefault("frame_queue_size", 2000)
    sync.setdefault("latest_buffer_size", 20000)

    control = normalized["control"]
    control.setdefault("command_topic", "/data_collection/record_cmd")
    control.setdefault("command_type", "std_msgs/String")

    return normalized


def validate_config(config):
    topics = config.get("topics", [])
    if not topics:
        raise ConfigError("config must define at least one topic")

    names = set()
    outputs = {}
    required_count = 0
    for spec in topics:
        validate_topic_spec(spec)
        if spec["name"] in names:
            raise ConfigError("duplicate topic name '{}'".format(spec["name"]))
        names.add(spec["name"])
        if spec["sync"] == "required":
            required_count += 1
        for output in iter_spec_outputs(spec):
            if output in outputs:
                raise ConfigError(
                    "output '{}' is produced by both '{}' and '{}'".format(
                        output, outputs[output], spec["name"]
                    )
                )
            outputs[output] = spec["name"]

    if required_count == 0:
        raise ConfigError("at least one topic must use sync: required")

    for spec in config.get("computed_columns", []):
        validate_computed_spec(spec, outputs)

    control = config.get("control", {})
    if control.get("command_type") != "std_msgs/String":
        raise ConfigError("control.command_type must be std_msgs/String")


def validate_topic_spec(spec):
    for key in ("name", "topic", "type", "sync", "converter"):
        if key not in spec:
            raise ConfigError("topic spec missing required key '{}'".format(key))
    if spec["sync"] not in VALID_SYNC_MODES:
        raise ConfigError(
            "topic '{}' has invalid sync mode '{}'".format(spec["name"], spec["sync"])
        )
    if "output" not in spec and "outputs" not in spec:
        raise ConfigError("topic '{}' must define output or outputs".format(spec["name"]))

    try:
        resolve_msg_type(spec["type"])
    except Exception as exc:
        raise ConfigError(
            "topic '{}' has invalid type '{}': {}".format(
                spec["name"], spec["type"], exc
            )
        )
    try:
        get_converter(spec["converter"])
    except ConverterError as exc:
        raise ConfigError(
            "topic '{}' has invalid converter '{}': {}".format(
                spec["name"], spec["converter"], exc
            )
        )


def validate_computed_spec(spec, existing_outputs):
    for key in ("output", "converter", "inputs"):
        if key not in spec:
            raise ConfigError("computed column missing required key '{}'".format(key))
    if spec["output"] in existing_outputs:
        raise ConfigError("computed output '{}' conflicts with a topic output".format(spec["output"]))
    try:
        get_converter(spec["converter"])
    except ConverterError as exc:
        raise ConfigError(
            "computed output '{}' has invalid converter '{}': {}".format(
                spec["output"], spec["converter"], exc
            )
        )


def iter_spec_outputs(spec):
    if "output" in spec:
        yield spec["output"]
    outputs = spec.get("outputs") or {}
    if isinstance(outputs, dict):
        for value in outputs.values():
            yield value
    elif isinstance(outputs, list):
        for value in outputs:
            yield value

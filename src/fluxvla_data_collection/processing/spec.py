"""Processing spec loading and validation."""

from __future__ import print_function

import os

import yaml


class SpecError(RuntimeError):
    pass


def load_processing_spec(path):
    with open(path, "r", encoding="utf-8") as file_obj:
        spec = yaml.safe_load(file_obj) or {}
    spec["_spec_path"] = os.path.abspath(path)
    return normalize_processing_spec(spec)


def normalize_processing_spec(spec):
    spec.setdefault("robot", {})
    spec.setdefault("features", [])
    spec.setdefault("cameras", [])

    robot = spec["robot"]
    robot.setdefault("robot_type", "generic_robot")
    robot.setdefault("fps", 30)

    for feature in spec["features"]:
        feature.setdefault("dtype", "float32")
        feature.setdefault("required", False)
        feature.setdefault("sources", [])
        feature.setdefault("names", [])

    for camera in spec["cameras"]:
        camera.setdefault("required", False)
        camera.setdefault("dtype", "video")

    validate_processing_spec(spec)
    return spec


def validate_processing_spec(spec):
    if not spec.get("features") and not spec.get("cameras"):
        raise SpecError("processing spec must define at least one feature or camera")

    output_paths = {}
    lerobot_keys = {}

    for feature in spec.get("features", []):
        _require_keys(feature, ("name", "output", "sources"), "feature")
        if not feature["sources"]:
            raise SpecError("feature '{}' must define at least one source".format(feature["name"]))
        for source in feature["sources"]:
            _require_keys(source, ("column",), "source for feature '{}'".format(feature["name"]))
        _check_unique(output_paths, feature["output"], "feature '{}'".format(feature["name"]))
        if feature.get("lerobot_key"):
            if not feature.get("names"):
                raise SpecError(
                    "feature '{}' with lerobot_key must define names".format(feature["name"])
                )
            _check_unique(
                lerobot_keys,
                feature["lerobot_key"],
                "feature '{}'".format(feature["name"]),
            )

    for camera in spec.get("cameras", []):
        _require_keys(camera, ("name", "column", "output", "shape"), "camera")
        shape = camera["shape"]
        if not isinstance(shape, list) or len(shape) != 2:
            raise SpecError("camera '{}' shape must be [height, width]".format(camera["name"]))
        _check_unique(output_paths, camera["output"], "camera '{}'".format(camera["name"]))
        if camera.get("lerobot_key"):
            _check_unique(
                lerobot_keys,
                camera["lerobot_key"],
                "camera '{}'".format(camera["name"]),
            )

    if not any(feature.get("required", False) for feature in spec.get("features", [])):
        if not any(camera.get("required", False) for camera in spec.get("cameras", [])):
            raise SpecError("at least one feature or camera must be required")


def primary_video_name(spec):
    required = [camera for camera in spec.get("cameras", []) if camera.get("required", False)]
    cameras = required or spec.get("cameras", [])
    if not cameras:
        return "rgb.mp4"
    return cameras[0]["output"]


def lerobot_feature_specs(spec):
    entries = []
    for feature in spec.get("features", []):
        if feature.get("lerobot_key"):
            entries.append(("feature", feature))
    for camera in spec.get("cameras", []):
        if camera.get("lerobot_key"):
            entries.append(("camera", camera))
    return entries


def _require_keys(mapping, keys, label):
    for key in keys:
        if key not in mapping:
            raise SpecError("{} missing required key '{}'".format(label, key))


def _check_unique(seen, value, owner):
    if value in seen:
        raise SpecError("'{}' is used by both {} and {}".format(value, seen[value], owner))
    seen[value] = owner

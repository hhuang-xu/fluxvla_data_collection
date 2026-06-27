"""Build Parquet rows from synchronized ROS frames."""

import rospy

from fluxvla_data_collection.registry import get_converter


class RowContext:
    def __init__(self, frame, bridge=None):
        self.frame = frame
        self.bridge = bridge
        self.frame_min = frame["frame_min"]
        self.frame_max = frame["frame_max"]
        self.stamps = frame["stamps"]
        self.logger = rospy


class RowBuilder:
    def __init__(self, config, bridge=None):
        self.config = config
        self.topics = list(config["topics"])
        self.computed_columns = list(config.get("computed_columns", []))
        self.bridge = bridge

    def build_row(self, frame):
        context = RowContext(frame, bridge=self.bridge)
        row = {
            "/timestamps/frame_min": float(frame["frame_min"]),
            "/timestamps/frame_max": float(frame["frame_max"]),
            "/timestamps/sync_span": float(frame["frame_max"] - frame["frame_min"]),
        }
        for name, stamp in frame["stamps"].items():
            row["/timestamps/{}".format(name)] = float(stamp)

        for spec in self.topics:
            msg = self._get_msg(frame, spec)
            if msg is None:
                row.update(self._default_outputs(spec))
                continue
            converter = get_converter(spec["converter"])
            row.update(converter(msg, spec, context))

        for spec in self.computed_columns:
            converter = get_converter(spec["converter"])
            values = [row.get(input_name) for input_name in spec.get("inputs", [])]
            row.update(converter(values, spec, context))

        return row

    @staticmethod
    def _get_msg(frame, spec):
        if spec["sync"] == "required":
            return frame["required"].get(spec["name"])
        return frame["latest"].get(spec["name"])

    @staticmethod
    def _default_outputs(spec):
        if "default" not in spec:
            return {}
        default = spec["default"]
        if "output" in spec:
            return {spec["output"]: default}
        outputs = spec.get("outputs") or {}
        if isinstance(default, dict):
            return {
                output_name: default[key]
                for key, output_name in outputs.items()
                if key in default
            }
        return {output_name: default for output_name in outputs.values()}

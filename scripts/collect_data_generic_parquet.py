#!/usr/bin/env python3

import argparse
import os
import sys
import time

import rospy
from cv_bridge import CvBridge

PACKAGE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PACKAGE_SRC = os.path.join(PACKAGE_ROOT, "src")
if PACKAGE_SRC not in sys.path:
    sys.path.insert(0, PACKAGE_SRC)

import fluxvla_data_collection.converters  # noqa: F401
from fluxvla_data_collection.config import ConfigError, load_config, validate_config
from fluxvla_data_collection.control import RecordCommandController
from fluxvla_data_collection.row_builder import RowBuilder
from fluxvla_data_collection.sync import TopicSynchronizer
from fluxvla_data_collection.writer import EpisodeWriter


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generic ROS topic recorder with message_filters sync and Parquet output."
    )
    parser.add_argument("--config", required=True, help="Path to collection YAML config.")
    parser.add_argument(
        "--task-description",
        "--task_description",
        default=None,
        help="Per-run task description saved in episode metadata.",
    )
    parser.add_argument(
        "--validate_config",
        action="store_true",
        help="Validate config and exit without subscribing or recording.",
    )
    return parser.parse_args(rospy.myargv(argv=sys.argv)[1:])


def finish_recording(syncer, row_builder, writer, reason):
    drained = 0
    for frame in syncer.drain_frames():
        writer.append_row(row_builder.build_row(frame))
        drained += 1
    if drained:
        rospy.loginfo("Drained %d synchronized frames before finishing", drained)
    return writer.finish(reason)


def main():
    args = parse_args()
    config = load_config(args.config)
    if args.task_description is not None:
        config["dataset"]["task_description"] = args.task_description
    try:
        validate_config(config)
    except ConfigError as exc:
        print("Invalid config: {}".format(exc), file=sys.stderr)
        return 2

    if args.validate_config:
        print("Config OK: {}".format(args.config))
        return 0

    rospy.init_node("collect_data_generic_parquet", anonymous=True)
    bridge = CvBridge()
    syncer = TopicSynchronizer(config)
    row_builder = RowBuilder(config, bridge=bridge)
    writer = EpisodeWriter(config)
    controller = RecordCommandController(config["control"]["command_topic"])
    rate = rospy.Rate(float(config["dataset"]["frame_rate"]))
    recording = False
    last_frame_wall_time = None
    last_no_frame_warning_time = None
    no_frame_warning_timeout = float(config["dataset"].get("no_frame_warning_timeout", 1.0))
    no_frame_warning_interval = float(config["dataset"].get("no_frame_warning_interval", 5.0))

    rospy.loginfo(
        "fluxvla_data_collection ready. Publish std_msgs/String start/stop/cancel to %s",
        config["control"]["command_topic"],
    )

    while not rospy.is_shutdown():
        command = controller.pop_command()
        if command == "start":
            if recording:
                rospy.logwarn("Ignoring start command because recording is already active")
            else:
                syncer.reset_runtime()
                camera_info = syncer.wait_for_camera_infos(
                    float(config["dataset"].get("camera_info_timeout", 5.0))
                )
                writer.start_episode(
                    topic_meta=syncer.build_topic_meta(),
                    camera_info=camera_info,
                )
                recording = True
                last_frame_wall_time = time.monotonic()
                last_no_frame_warning_time = None
                rospy.loginfo("Recording started")

        elif command == "stop":
            if not recording:
                rospy.logwarn("Ignoring stop command because no recording is active")
            else:
                finish_recording(syncer, row_builder, writer, "record_cmd_stop")
                recording = False
                last_frame_wall_time = None
                last_no_frame_warning_time = None

        elif command == "cancel":
            if not recording:
                rospy.logwarn("Ignoring cancel command because no recording is active")
            else:
                writer.cancel()
                syncer.reset_runtime()
                recording = False
                last_frame_wall_time = None
                last_no_frame_warning_time = None
                rospy.loginfo("Recording cancelled")

        if recording:
            if writer.frame_count >= int(config["dataset"]["max_timesteps"]):
                finish_recording(syncer, row_builder, writer, "max_timesteps")
                recording = False
                last_frame_wall_time = None
                last_no_frame_warning_time = None
            else:
                frame = syncer.pop_frame()
                if frame is not None:
                    row = row_builder.build_row(frame)
                    writer.append_row(row)
                    last_frame_wall_time = time.monotonic()
                    last_no_frame_warning_time = None
                elif no_frame_warning_timeout > 0.0:
                    now = time.monotonic()
                    if last_frame_wall_time is None:
                        last_frame_wall_time = now
                    idle_time = now - last_frame_wall_time
                    should_warn = idle_time >= no_frame_warning_timeout and (
                        last_no_frame_warning_time is None
                        or now - last_no_frame_warning_time >= no_frame_warning_interval
                    )
                    if should_warn:
                        rospy.logwarn(
                            "No synchronized frames for %.2fs while recording; "
                            "required topics may be missing or stalled: %s",
                            idle_time,
                            syncer.required_names,
                        )
                        last_no_frame_warning_time = now

        rate.sleep()

    if recording:
        finish_recording(syncer, row_builder, writer, "ros_shutdown")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

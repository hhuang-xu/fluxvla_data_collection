"""ROS topic synchronization and latest-before buffering."""

import threading
from collections import deque

import message_filters
import rospy
from sensor_msgs.msg import CameraInfo

from fluxvla_data_collection.ros_types import get_stamp, resolve_msg_type


def replace_last_segment(input_string, new_segment="camera_info"):
    last_slash_index = input_string.rfind("/")
    if last_slash_index != -1:
        return input_string[: last_slash_index + 1] + new_segment
    return new_segment


class LatestBeforeBuffer:
    def __init__(self, maxlen):
        self._items = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def append(self, stamp, msg):
        with self._lock:
            self._items.append((float(stamp), msg))

    def latest_before(self, stamp):
        with self._lock:
            if not self._items:
                return None
            while len(self._items) > 1 and self._items[1][0] <= stamp:
                self._items.popleft()
            if self._items[0][0] <= stamp:
                return self._items[0]
            return None

    def clear(self):
        with self._lock:
            self._items.clear()


class TopicSynchronizer:
    def __init__(self, config):
        self.config = config
        self.sync_config = config["sync"]
        self.topics = list(config["topics"])
        self.required_specs = [spec for spec in self.topics if spec["sync"] == "required"]
        self.latest_specs = [spec for spec in self.topics if spec["sync"] == "latest_before"]
        self.required_names = [spec["name"] for spec in self.required_specs]
        self.msg_types = {spec["name"]: resolve_msg_type(spec["type"]) for spec in self.topics}
        self._frames = deque(maxlen=int(self.sync_config.get("frame_queue_size", 2000)))
        self._lock = threading.Lock()
        self._last_frame_max = 0.0
        self._latest_buffers = {
            spec["name"]: LatestBeforeBuffer(int(self.sync_config.get("latest_buffer_size", 20000)))
            for spec in self.latest_specs
        }
        self._required_subscribers = []
        self._latest_subscribers = []
        self._sync = None
        self._build_subscribers()

    def _build_subscribers(self):
        for spec in self.required_specs:
            self._required_subscribers.append(
                message_filters.Subscriber(
                    spec["topic"],
                    self.msg_types[spec["name"]],
                    queue_size=1000,
                    tcp_nodelay=True,
                )
            )

        for spec in self.latest_specs:
            subscriber = rospy.Subscriber(
                spec["topic"],
                self.msg_types[spec["name"]],
                self._make_latest_callback(spec),
                queue_size=1000,
                tcp_nodelay=True,
            )
            self._latest_subscribers.append(subscriber)

        self._sync = message_filters.ApproximateTimeSynchronizer(
            self._required_subscribers,
            queue_size=int(self.sync_config.get("queue_size", 100)),
            slop=float(self.sync_config.get("slop", 0.05)),
            allow_headerless=False,
        )
        self._sync.registerCallback(self._sync_callback)
        rospy.loginfo(
            "Configured ApproximateTimeSynchronizer: required=%s slop=%.3f queue=%d latest_before=%s",
            self.required_names,
            float(self.sync_config.get("slop", 0.05)),
            int(self.sync_config.get("queue_size", 100)),
            [spec["name"] for spec in self.latest_specs],
        )

    def reset_runtime(self):
        with self._lock:
            self._frames.clear()
            self._last_frame_max = 0.0
        for buffer_obj in self._latest_buffers.values():
            buffer_obj.clear()
        self._clear_message_filter_queues()

    def _clear_message_filter_queues(self):
        for queue in getattr(self._sync, "queues", []):
            if hasattr(queue, "clear"):
                queue.clear()

    def _make_latest_callback(self, spec):
        name = spec["name"]
        buffer_obj = self._latest_buffers[name]

        def callback(msg):
            stamp = get_stamp(msg, fallback_time=rospy.Time.now().to_sec())
            buffer_obj.append(stamp, msg)

        return callback

    def _sync_callback(self, *msgs):
        stamps = {}
        required = {}
        frame_min = float("inf")
        frame_max = 0.0
        for spec, msg in zip(self.required_specs, msgs):
            stamp = get_stamp(msg)
            if stamp is None:
                rospy.logwarn("Required topic %s has no usable header.stamp", spec["name"])
                return
            required[spec["name"]] = msg
            stamps[spec["name"]] = stamp
            frame_min = min(frame_min, stamp)
            frame_max = max(frame_max, stamp)

        latest = {}
        for spec in self.latest_specs:
            item = self._latest_buffers[spec["name"]].latest_before(frame_max)
            if item is None:
                latest[spec["name"]] = None
                continue
            stamps[spec["name"]] = item[0]
            latest[spec["name"]] = item[1]

        with self._lock:
            self._frames.append(
                {
                    "frame_min": frame_min,
                    "frame_max": frame_max,
                    "required": required,
                    "latest": latest,
                    "stamps": stamps,
                }
            )

    def pop_frame(self):
        with self._lock:
            while self._frames:
                frame = self._frames.popleft()
                if frame["frame_max"] > self._last_frame_max:
                    self._last_frame_max = frame["frame_max"]
                    return frame
        return None

    def drain_frames(self):
        drained = []
        while True:
            frame = self.pop_frame()
            if frame is None:
                break
            drained.append(frame)
        return drained

    def build_topic_meta(self):
        return {
            spec["name"]: {
                "topic": spec["topic"],
                "type": spec["type"],
                "sync": spec["sync"],
                "converter": spec["converter"],
            }
            for spec in self.topics
        }

    def wait_for_camera_infos(self, timeout):
        infos = {}
        image_specs = [
            spec for spec in self.topics if self.msg_types[spec["name"]].__name__ == "Image"
        ]
        for spec in image_specs:
            info_topic = spec.get("camera_info_topic") or replace_last_segment(spec["topic"])
            try:
                msg = rospy.wait_for_message(info_topic, CameraInfo, timeout=timeout)
            except rospy.ROSException:
                rospy.logwarn("Timed out waiting for camera_info topic %s", info_topic)
                continue
            infos[info_topic] = {
                "rostopic": info_topic,
                "height": msg.height,
                "width": msg.width,
                "distortion_model": msg.distortion_model,
                "D": list(msg.D),
                "K": list(msg.K),
                "R": list(msg.R),
                "P": list(msg.P),
                "binning_x": msg.binning_x,
                "binning_y": msg.binning_y,
            }
        return infos

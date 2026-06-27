"""Streaming Parquet episode writer."""

import json
import os
import re
import sys
import time
from datetime import datetime

import rospy


ANSI_RESET = "\033[0m"
ANSI_BOLD_CYAN = "\033[1;36m"
ANSI_BOLD_GREEN = "\033[1;32m"
ANSI_BOLD_YELLOW = "\033[1;33m"


def highlight(text, color):
    return "{}{}{}".format(color, text, ANSI_RESET)


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def find_max_episode_number(target_folder):
    if not os.path.exists(target_folder):
        return -1
    max_number = -1
    for filename in os.listdir(target_folder):
        match = re.match(r"episode_(\d+)\.parquet$", filename)
        if match:
            max_number = max(max_number, int(match.group(1)))
    return max_number


def save_json(data, path):
    with open(path, "w", encoding="utf-8") as file_obj:
        json.dump(data, file_obj, indent=2, ensure_ascii=False)


class EpisodeWriter:
    def __init__(self, config):
        self.config = config
        self.dataset = config["dataset"]
        self.writer = None
        self.schema = None
        self.rows = []
        self.frame_count = 0
        self.started_wall_time = None
        self.dataset_dir = None
        self.parquet_path = None
        self.meta_path = None
        self.episode_idx = None
        self.first_frame_data_time = None
        self.last_frame_data_time = None
        self.task_description = ""

    def start_episode(self, topic_meta=None, camera_info=None):
        current_date = datetime.now().strftime("%Y%m%d")
        self.dataset_dir = os.path.join(
            self.dataset["dataset_dir"],
            current_date,
            "{}_{}".format(self.dataset["task_name"], self.dataset["station_idx"]),
        )
        ensure_dir(self.dataset_dir)
        configured_idx = int(self.dataset.get("episode_idx", -1))
        self.episode_idx = (
            find_max_episode_number(self.dataset_dir) + 1
            if configured_idx == -1
            else configured_idx
        )
        dataset_path = os.path.join(self.dataset_dir, "episode_{}".format(self.episode_idx))
        self.parquet_path = dataset_path + ".parquet"
        self.meta_path = dataset_path + ".meta.json"
        self.writer = None
        self.schema = None
        self.rows = []
        self.frame_count = 0
        self.started_wall_time = time.time()
        self.first_frame_data_time = None
        self.last_frame_data_time = None
        self.topic_meta = topic_meta or {}
        self.camera_info = camera_info or {}
        self.task_description = str(self.dataset.get("task_description", "") or "")
        if self.camera_info:
            save_json(self.camera_info, os.path.join(self.dataset_dir, "camera_info.json"))
        rospy.loginfo(
            highlight("🎬 Recording episode: {}".format(self.parquet_path), ANSI_BOLD_CYAN)
        )

    def append_row(self, row):
        self.rows.append(row)
        self.frame_count += 1
        self._check_frame_drop(row)
        if len(self.rows) >= int(self.dataset.get("flush_every_n", 100)):
            self.flush()

    def flush(self):
        if not self.rows:
            return
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ModuleNotFoundError as exc:
            if exc.name != "pyarrow":
                raise
            raise RuntimeError(
                "pyarrow is required to write Parquet files, but it is not "
                "installed for the Python executable currently running this "
                "recorder: {}. Install pyarrow into that environment, or run "
                "the recorder with the Python environment that already has "
                "pyarrow.".format(sys.executable)
            ) from exc

        if self.schema is None:
            table = pa.Table.from_pylist(self.rows)
            self.schema = table.schema.with_metadata(self._build_parquet_metadata())
            self.writer = pq.ParquetWriter(self.parquet_path, self.schema, compression="snappy")
        else:
            table = pa.Table.from_pylist(self.rows, schema=self.schema)
        self.writer.write_table(table)
        self.rows = []

    def finish(self, reason):
        if self.frame_count == 0:
            rospy.logwarn(highlight("⚠️ No frames collected, skipping save", ANSI_BOLD_YELLOW))
            self.cancel()
            return None
        self.flush()
        if self.writer is not None:
            self.writer.close()
        duration = time.time() - self.started_wall_time if self.started_wall_time else 0.0
        meta = {
            "episode_idx": self.episode_idx,
            "n_frames": self.frame_count,
            "dataset_path": self.parquet_path,
            "task_description": self.task_description,
            "reason": reason,
            "duration_sec": duration,
            "created_at": datetime.now().isoformat(),
            "config_path": self.config.get("_config_path"),
            "dataset": self.dataset,
            "sync": self.config.get("sync", {}),
            "control": self.config.get("control", {}),
            "topics": self.config.get("topics", []),
            "computed_columns": self.config.get("computed_columns", []),
            "topic_meta": self.topic_meta,
        }
        save_json(meta, self.meta_path)
        path = self.parquet_path
        rospy.loginfo(
            highlight("✅ Saved {} frames to {}".format(self.frame_count, path), ANSI_BOLD_GREEN)
        )
        self._reset_runtime()
        return path

    def cancel(self):
        if self.writer is not None:
            self.writer.close()
        for path in (self.parquet_path, self.meta_path):
            if path and os.path.exists(path):
                os.remove(path)
        self._reset_runtime()

    def _reset_runtime(self):
        self.writer = None
        self.schema = None
        self.rows = []
        self.frame_count = 0
        self.started_wall_time = None
        self.first_frame_data_time = None
        self.last_frame_data_time = None
        self.task_description = ""

    def _build_parquet_metadata(self):
        metadata = {}
        for key, value in (
            ("fluxvla.task_name", self.dataset.get("task_name", "")),
            ("fluxvla.station_idx", self.dataset.get("station_idx", "")),
            ("fluxvla.episode_idx", self.episode_idx),
            ("fluxvla.task_description", self.task_description),
            ("fluxvla.config_path", self.config.get("_config_path", "")),
        ):
            metadata[str(key).encode("utf-8")] = str(value).encode("utf-8")
        return metadata

    def _check_frame_drop(self, row):
        frame_time = row.get("/timestamps/frame_max")
        if frame_time is None:
            return
        frame_time = float(frame_time)
        if self.first_frame_data_time is None:
            self.first_frame_data_time = frame_time
            self.last_frame_data_time = frame_time
            return

        previous_frame_time = self.last_frame_data_time
        self.last_frame_data_time = frame_time
        if previous_frame_time is None:
            return

        frame_rate = float(self.dataset.get("frame_rate", 0.0))
        if frame_rate <= 0.0:
            return
        expected_dt = 1.0 / frame_rate
        warning_factor = float(self.dataset.get("drop_warning_factor", 1.5))
        warning_dt = expected_dt * warning_factor
        actual_dt = frame_time - previous_frame_time
        if actual_dt <= warning_dt:
            return

        estimated_missed_frames = max(1, int(round(actual_dt / expected_dt)) - 1)
        rospy.logwarn(
            "Possible frame drop: gap=%.4fs expected=%.4fs threshold=%.4fs "
            "estimated_missed_frames=%d frame_index=%d prev_ts=%.6f curr_ts=%.6f",
            actual_dt,
            expected_dt,
            warning_dt,
            estimated_missed_frames,
            self.frame_count - 1,
            previous_frame_time,
            frame_time,
        )

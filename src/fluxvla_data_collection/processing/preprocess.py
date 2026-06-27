"""Parquet to processed NPY/MP4 conversion."""

from __future__ import print_function

import json
import os
import re

import numpy as np

from fluxvla_data_collection.processing.array_builder import (
    MissingRequiredColumn,
    OptionalFeatureMissing,
    build_feature_array,
)
from fluxvla_data_collection.processing.parquet_io import (
    read_episode_parquet,
    task_description_for_episode,
)
from fluxvla_data_collection.processing.spec import primary_video_name
from fluxvla_data_collection.processing.video_writer import (
    video_is_readable,
    write_image_bytes_video,
)


def discover_task_dirs(raw_root, subfolder=None):
    if not os.path.isdir(raw_root):
        raise FileNotFoundError("raw root does not exist: {}".format(raw_root))
    date_dirs = _date_dirs(raw_root, subfolder)
    task_dirs = []
    for date_dir in date_dirs:
        for name in sorted(os.listdir(date_dir)):
            path = os.path.join(date_dir, name)
            if not os.path.isdir(path):
                continue
            if list_episode_parquets(path):
                task_dirs.append((os.path.basename(date_dir), name, path))
    return task_dirs


def list_episode_parquets(task_dir):
    return [
        os.path.join(task_dir, name)
        for name in sorted(os.listdir(task_dir), key=_episode_sort_key)
        if name.endswith(".parquet")
    ]


def preprocess_dataset(
    raw_root,
    output_root,
    output_prefix,
    spec,
    subfolder=None,
    overwrite=False,
    skip_bad_episodes=True,
    dry_run=False,
    video_codec="mp4v",
    task=None,
):
    results = []
    for date_part, task_folder, task_dir in discover_task_dirs(raw_root, subfolder):
        output_name = "{}_{}_{}".format(output_prefix.rstrip("_"), date_part, task_folder)
        output_dir = os.path.join(output_root, output_name)
        for parquet_path in list_episode_parquets(task_dir):
            episode_number = _episode_number(parquet_path)
            episode_output_dir = os.path.join(output_dir, "episode_{}".format(episode_number))
            if dry_run:
                print("would process {} -> {}".format(parquet_path, episode_output_dir))
                results.append({"source": parquet_path, "output": episode_output_dir, "status": "dry_run"})
                continue
            try:
                status = preprocess_episode(
                    parquet_path,
                    episode_output_dir,
                    spec,
                    task_folder=task_folder,
                    overwrite=overwrite,
                    video_codec=video_codec,
                    task=task,
                )
                results.append(status)
            except Exception as exc:
                if not skip_bad_episodes:
                    raise
                print("warning: skipping {}: {}".format(parquet_path, exc))
                results.append({"source": parquet_path, "output": episode_output_dir, "status": "error", "error": str(exc)})
    return results


def preprocess_episode(
    parquet_path,
    output_dir,
    spec,
    task_folder="",
    overwrite=False,
    video_codec="mp4v",
    task=None,
):
    primary_video = primary_video_name(spec)
    primary_video_path = os.path.join(output_dir, primary_video)
    if not overwrite and video_is_readable(primary_video_path):
        print("skipping existing processed episode: {}".format(output_dir))
        return {"source": parquet_path, "output": output_dir, "status": "skipped"}

    os.makedirs(output_dir, exist_ok=True)
    episode = read_episode_parquet(parquet_path)

    arrays = {}
    frame_count = None
    for feature in spec.get("features", []):
        try:
            array = build_feature_array(episode, feature)
        except OptionalFeatureMissing as exc:
            print("warning: {}".format(exc))
            continue
        except MissingRequiredColumn:
            raise
        arrays[feature["name"]] = {
            "output": feature["output"],
            "shape": list(array.shape),
            "names": feature.get("names", []),
            "lerobot_key": feature.get("lerobot_key"),
        }
        if frame_count is None:
            frame_count = array.shape[0]
        elif array.shape[0] != frame_count:
            raise ValueError(
                "feature '{}' row count {} does not match expected {}".format(
                    feature["name"], array.shape[0], frame_count
                )
            )
        np.save(os.path.join(output_dir, feature["output"]), array)

    cameras = {}
    fps = spec.get("robot", {}).get("fps", 30)
    for camera in spec.get("cameras", []):
        column = camera["column"]
        if not episode.has_column(column):
            message = "camera '{}' missing column {}".format(camera["name"], column)
            if camera.get("required", False):
                raise MissingRequiredColumn(message)
            print("warning: {}".format(message))
            continue
        values = episode.column_values(column)
        if frame_count is None:
            frame_count = len(values)
        video_path = os.path.join(output_dir, camera["output"])
        video_info = write_image_bytes_video(
            video_path,
            values,
            fps=fps,
            codec=video_codec,
            expected_frames=frame_count,
        )
        cameras[camera["name"]] = {
            "output": camera["output"],
            "path": video_path,
            "frames": video_info["frames"],
            "width": video_info["width"],
            "height": video_info["height"],
            "lerobot_key": camera.get("lerobot_key"),
            "shape": camera.get("shape"),
        }

    if frame_count is None:
        raise ValueError("no feature or camera data was generated for {}".format(parquet_path))

    task_description = task_description_for_episode(episode, cli_task=task, fallback=task_folder)
    info = {
        "id": "{}_{}".format(task_folder, _episode_number(parquet_path)),
        "robot_type": spec.get("robot", {}).get("robot_type", "generic_robot"),
        "task_name": episode.meta.get("dataset", {}).get("task_name", task_folder),
        "station_idx": episode.meta.get("dataset", {}).get("station_idx", ""),
        "task_description": task_description,
        "text": task_description,
        "fps": fps,
        "frames": int(frame_count),
        "source_parquet": parquet_path,
        "source_meta": parquet_path[:-8] + ".meta.json" if parquet_path.endswith(".parquet") else "",
        "primary_video": primary_video,
        "features": arrays,
        "cameras": cameras,
        "spec_path": spec.get("_spec_path"),
    }
    with open(os.path.join(output_dir, "info.json"), "w", encoding="utf-8") as file_obj:
        json.dump(info, file_obj, indent=2, ensure_ascii=False)

    print("processed {} -> {}".format(parquet_path, output_dir))
    return {"source": parquet_path, "output": output_dir, "status": "processed", "frames": int(frame_count)}


def _date_dirs(raw_root, subfolder):
    if subfolder:
        path = subfolder if os.path.isabs(subfolder) else os.path.join(raw_root, subfolder)
        if not os.path.isdir(path):
            raise FileNotFoundError("subfolder does not exist: {}".format(path))
        return [path]
    return [
        os.path.join(raw_root, name)
        for name in sorted(os.listdir(raw_root))
        if os.path.isdir(os.path.join(raw_root, name))
    ]


def _episode_number(path):
    match = re.search(r"episode_(\d+)\.parquet$", os.path.basename(path))
    if not match:
        return os.path.splitext(os.path.basename(path))[0]
    return int(match.group(1))


def _episode_sort_key(name):
    match = re.search(r"episode_(\d+)\.parquet$", name)
    if match:
        return (0, int(match.group(1)))
    return (1, name)

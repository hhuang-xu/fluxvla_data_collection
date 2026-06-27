"""Export processed FluxVLA episodes to LeRobot format."""

from __future__ import print_function

import json
import os
import re
import shutil

import cv2
import numpy as np

from fluxvla_data_collection.processing.annotation import load_annotation_map


def convert_to_lerobot(
    repo_id,
    annotation_json,
    spec,
    output_root,
    mode="video",
    fps=None,
    video_codec="h264",
    debug=False,
    start_date=None,
    end_date=None,
):
    _patch_lerobot_video_codec(video_codec)

    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    annotation_map = load_annotation_map(annotation_json)
    video_paths = _filter_video_paths(sorted(annotation_map.keys()), start_date, end_date)
    if debug:
        video_paths = video_paths[:2]
    if not video_paths:
        raise RuntimeError("no videos selected from {}".format(annotation_json))

    active_features, active_cameras = _active_specs_for_paths(video_paths, spec)
    dataset_root = os.path.join(os.path.expanduser(output_root), repo_id)
    if os.path.exists(dataset_root):
        shutil.rmtree(dataset_root)

    dataset = LeRobotDataset.create(
        repo_id=repo_id,
        fps=int(fps or spec.get("robot", {}).get("fps", 30)),
        features=_build_lerobot_features(active_features, active_cameras, mode),
        root=dataset_root,
        robot_type=spec.get("robot", {}).get("robot_type", "generic_robot"),
        use_videos=(mode == "video"),
        video_backend=None,
    )

    for video_path in video_paths:
        episode_dir = os.path.dirname(video_path)
        arrays = _load_feature_arrays(episode_dir, active_features)
        videos = _load_camera_videos(episode_dir, active_cameras)
        frame_count = _infer_frame_count(arrays, videos)
        tasks = _tasks_for_frames(annotation_map.get(video_path, []), frame_count)
        if all(task == "empty" for task in tasks):
            print("warning: skipping {}, annotation text is empty".format(episode_dir))
            continue

        for index in range(frame_count):
            frame = {}
            for feature in active_features:
                frame[feature["lerobot_key"]] = _torch_tensor(arrays[feature["name"]][index], feature)
            for camera in active_cameras:
                frame[camera["lerobot_key"]] = videos[camera["name"]][index]
            dataset.add_frame(frame, tasks[index])
        dataset.save_episode()
        print("saved LeRobot episode from {}".format(episode_dir))

    print("LeRobot dataset written to {}".format(dataset_root))
    return dataset_root


def _build_lerobot_features(features, cameras, mode):
    result = {}
    for feature in features:
        names = feature.get("names") or _default_names(feature["name"], _feature_dim(feature))
        result[feature["lerobot_key"]] = {
            "dtype": feature.get("dtype", "float32"),
            "shape": (len(names),),
            "names": [names],
        }
    for camera in cameras:
        height, width = camera["shape"]
        result[camera["lerobot_key"]] = {
            "dtype": mode,
            "shape": (3, int(height), int(width)),
            "names": ["channels", "height", "width"],
        }
    return result


def _active_specs_for_paths(video_paths, spec):
    episode_dirs = [os.path.dirname(path) for path in video_paths]
    active_features = []
    active_cameras = []

    for feature in spec.get("features", []):
        if not feature.get("lerobot_key"):
            continue
        missing = [
            episode_dir
            for episode_dir in episode_dirs
            if not os.path.exists(os.path.join(episode_dir, feature["output"]))
        ]
        if missing and feature.get("required", False):
            raise FileNotFoundError(
                "required feature '{}' missing {} in {} episodes".format(
                    feature["name"], feature["output"], len(missing)
                )
            )
        if missing:
            print(
                "warning: optional feature '{}' missing in {} episodes; excluding from LeRobot export".format(
                    feature["name"], len(missing)
                )
            )
            continue
        active_features.append(feature)

    for camera in spec.get("cameras", []):
        if not camera.get("lerobot_key"):
            continue
        missing = [
            episode_dir
            for episode_dir in episode_dirs
            if not os.path.exists(os.path.join(episode_dir, camera["output"]))
        ]
        if missing and camera.get("required", False):
            raise FileNotFoundError(
                "required camera '{}' missing {} in {} episodes".format(
                    camera["name"], camera["output"], len(missing)
                )
            )
        if missing:
            print(
                "warning: optional camera '{}' missing in {} episodes; excluding from LeRobot export".format(
                    camera["name"], len(missing)
                )
            )
            continue
        active_cameras.append(camera)

    if not active_features:
        raise RuntimeError("no active vector features available for LeRobot export")
    return active_features, active_cameras


def _load_feature_arrays(episode_dir, features):
    arrays = {}
    for feature in features:
        path = os.path.join(episode_dir, feature["output"])
        array = np.load(path, allow_pickle=True)
        if array.ndim == 1:
            array = array.reshape(-1, 1)
        names = feature.get("names") or _default_names(feature["name"], array.shape[1])
        if len(names) != array.shape[1]:
            raise ValueError(
                "{} dimension {} does not match names length {}".format(
                    path, array.shape[1], len(names)
                )
            )
        arrays[feature["name"]] = array
    return arrays


def _load_camera_videos(episode_dir, cameras):
    videos = {}
    for camera in cameras:
        path = os.path.join(episode_dir, camera["output"])
        frames = _read_video_frames(path)
        videos[camera["name"]] = frames
    return videos


def _read_video_frames(path):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError("failed to open video: {}".format(path))
    frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    cap.release()
    if not frames:
        raise RuntimeError("video contains no frames: {}".format(path))
    return np.asarray(frames)


def _infer_frame_count(arrays, videos):
    counts = []
    for array in arrays.values():
        counts.append(array.shape[0])
    for frames in videos.values():
        counts.append(frames.shape[0])
    if not counts:
        raise RuntimeError("episode has no arrays or videos")
    expected = counts[0]
    for count in counts:
        if count != expected:
            raise ValueError("episode frame count mismatch: {}".format(counts))
    return expected


def _tasks_for_frames(segments, frame_count):
    tasks = ["empty"] * frame_count
    for segment in segments:
        text = segment.get("text") or "empty"
        start = max(0, int(segment.get("start_frame_id", 0)))
        end = min(frame_count, int(segment.get("end_frame_id", frame_count)))
        if end > start:
            tasks[start:end] = [text] * (end - start)
    return tasks


def _filter_video_paths(paths, start_date, end_date):
    if not start_date and not end_date:
        return paths
    selected = []
    for path in paths:
        match = re.search(r"(\d{8})", path)
        if not match:
            continue
        date = match.group(1)
        if start_date and date < start_date:
            continue
        if end_date and date > end_date:
            continue
        selected.append(path)
    return selected


def _torch_tensor(value, feature):
    import torch

    dtype = feature.get("dtype", "float32")
    tensor = torch.from_numpy(np.asarray(value))
    if dtype.startswith("float"):
        return tensor.float()
    if dtype.startswith("int"):
        return tensor.long()
    return tensor


def _feature_dim(feature):
    return len(feature.get("names") or [])


def _default_names(prefix, count):
    return ["{}_{}".format(prefix, index) for index in range(count)]


def _patch_lerobot_video_codec(vcodec):
    try:
        from lerobot.datasets import video_utils
    except Exception:
        return

    func = getattr(video_utils, "encode_video_frames", None)
    if func is None or not getattr(func, "__defaults__", None):
        return
    func.__defaults__ = tuple(
        vcodec if default == "libsvtav1" else default
        for default in func.__defaults__
    )


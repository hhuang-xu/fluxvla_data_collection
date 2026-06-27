"""Generate LeRobot-style annotation json from processed episodes."""

from __future__ import print_function

import glob
import json
import os
import re


def generate_annotations(
    processed_root,
    folder_pattern,
    output,
    task=None,
    video_name=None,
):
    entries = []
    task_dirs = sorted(glob.glob(os.path.join(processed_root, folder_pattern)))
    if not task_dirs:
        raise RuntimeError("no processed folders matched: {}".format(os.path.join(processed_root, folder_pattern)))

    for task_dir in task_dirs:
        if not os.path.isdir(task_dir):
            continue
        episode_dirs = [
            os.path.join(task_dir, name)
            for name in sorted(os.listdir(task_dir), key=_episode_sort_key)
            if os.path.isdir(os.path.join(task_dir, name))
        ]
        for episode_dir in episode_dirs:
            info = _read_info(episode_dir)
            selected_video = video_name or info.get("primary_video") or "rgb.mp4"
            video_path = os.path.join(episode_dir, selected_video)
            if not os.path.exists(video_path):
                print("warning: skipping {}, missing video {}".format(episode_dir, selected_video))
                continue
            frames = int(info.get("frames", 0))
            if frames <= 0:
                frames = 10**9
            entries.append(
                {
                    "path": video_path,
                    "start_frame_id": 0,
                    "end_frame_id": frames,
                    "text": _task_text(task, info, task_dir),
                }
            )

    output_dir = os.path.dirname(output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(output, "w", encoding="utf-8") as file_obj:
        json.dump(entries, file_obj, indent=2, ensure_ascii=False)
    print("wrote {} annotations to {}".format(len(entries), output))
    return entries


def load_annotation_map(annotation_json):
    with open(annotation_json, "r", encoding="utf-8") as file_obj:
        entries = json.load(file_obj)
    mapping = {}
    for entry in entries:
        mapping.setdefault(entry["path"], []).append({k: v for k, v in entry.items() if k != "path"})
    return mapping


def _read_info(episode_dir):
    path = os.path.join(episode_dir, "info.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as file_obj:
        return json.load(file_obj)


def _task_text(cli_task, info, task_dir):
    if cli_task:
        return cli_task
    for key in ("task_description", "text"):
        value = info.get(key)
        if value:
            return value
    return os.path.basename(task_dir)


def _episode_sort_key(name):
    match = re.search(r"episode_(\d+)$", name)
    if match:
        return (0, int(match.group(1)))
    return (1, name)

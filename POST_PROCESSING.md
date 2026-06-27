# FluxVLA Data Post-Processing

This document describes how to convert raw FluxVLA Parquet episodes into
processed `NPY + MP4` folders, generate task annotations, and export the result
to a LeRobot dataset.

The post-processing pipeline is platform-independent. Robot-specific layout is
defined in a YAML processing spec, such as:

- `config/processing_dual_franka.yaml`
- `config/processing_ur3.yaml`

For a new robot, add a new `processing_<robot>.yaml` file. The Python scripts do
not need to know the robot kinematics, number of arms, number of joints, or
camera names.

## Pipeline Overview

The full pipeline has three steps:

```text
raw Parquet episodes
  -> preprocess_fluxvla_parquet.py
processed NPY/MP4 episodes
  -> generate_fluxvla_annotations.py
annotation JSON
  -> convert_fluxvla_to_lerobot.py
LeRobot dataset
```

The expected raw data layout is:

```text
<raw-root>/<YYYYMMDD>/<task_name>_<station_idx>/
  episode_0.parquet
  episode_0.meta.json
  episode_1.parquet
  episode_1.meta.json
```

For example:

```text
/home/franka/Data/raw_data/20260627/dual_franka_teleop_franka_dual/
  episode_0.parquet
  episode_0.meta.json
```

## Environment

For Parquet preprocessing:

```bash
conda activate franka
cd /home/franka/franka/src/fluxvla_data_collection
```

Required Python packages:

- `numpy`
- `pyarrow`
- `opencv-python` or system OpenCV Python bindings
- `pyyaml`

For LeRobot export:

```bash
conda activate lerobot
cd /home/franka/franka/src/fluxvla_data_collection
```

Required additional packages:

- `lerobot`
- `torch`

All scripts can be run directly with `python` from the package root because they
add `src/` to `PYTHONPATH` internally.

## Step 1: Parquet to Processed NPY/MP4

Dual Franka example:

```bash
python scripts/preprocess_fluxvla_parquet.py \
  --raw-root /home/franka/Data/raw_data \
  --subfolder 20260627 \
  --spec config/processing_dual_franka.yaml \
  --output-root /home/franka/Data/processed_data \
  --output-prefix RealRobot_DualFranka \
  --video-codec mp4v
```

UR3 example:

```bash
python scripts/preprocess_fluxvla_parquet.py \
  --raw-root /home/franka/Data/raw_data \
  --subfolder 20260627 \
  --spec config/processing_ur3.yaml \
  --output-root /home/franka/Data/processed_data \
  --output-prefix RealRobot_UR3 \
  --video-codec mp4v
```

Useful options:

- `--subfolder 20260627`: process only one date folder.
- `--overwrite`: regenerate processed episodes even if output videos exist.
- `--dry-run`: print what would be processed without writing files.
- `--fail-fast`: stop at the first bad episode.
- `--task "..."`: fallback task text if raw metadata has no task description.
- `--video-codec mp4v`: fast and OpenCV-friendly processed videos.
- `--video-codec h264`: smaller files if the local OpenCV build supports it.

Example dry run:

```bash
python scripts/preprocess_fluxvla_parquet.py \
  --raw-root /home/franka/Data/raw_data \
  --subfolder 20260627 \
  --spec config/processing_dual_franka.yaml \
  --output-root /home/franka/Data/processed_data \
  --output-prefix RealRobot_DualFranka \
  --dry-run
```

The processed output layout is:

```text
<output-root>/<output-prefix>_<YYYYMMDD>_<task_name>_<station_idx>/
  episode_0/
    qpos.npy
    eepose.npy
    gripper.npy
    action.npy
    rgb.mp4
    rgb_wrist_left.mp4
    rgb_wrist_right.mp4
    info.json
```

For dual Franka, the default processed arrays are:

```text
qpos.npy     (N, 16)  left 7 joints + left gripper + right 7 joints + right gripper
eepose.npy   (N, 16)  left 7D pose + left gripper + right 7D pose + right gripper
gripper.npy  (N, 2)   left gripper + right gripper
action.npy   (N, 14)  left action eepose + right action eepose
```

`action.npy` is 14D for the current dual Franka config because only commanded
end-effector poses are recorded as actions; action gripper values are not
recorded.

## Step 2: Generate Annotation JSON

Generate annotations from processed episodes:

```bash
python scripts/generate_fluxvla_annotations.py \
  --processed-root /home/franka/Data/processed_data \
  --folder-pattern "RealRobot_DualFranka_20260627*" \
  --output /home/franka/Data/processed_data/franka_dual_annotations.json
```

Override the task text manually:

```bash
python scripts/generate_fluxvla_annotations.py \
  --processed-root /home/franka/Data/processed_data \
  --folder-pattern "RealRobot_DualFranka_20260627*" \
  --task "The robot picks up the cup and places it on the tray." \
  --output /home/franka/Data/processed_data/franka_dual_annotations.json
```

Task text priority:

1. `--task`
2. `info.json.task_description`
3. `info.json.text`
4. processed folder name

The output format is:

```json
[
  {
    "path": "/home/franka/Data/processed_data/.../episode_0/rgb.mp4",
    "start_frame_id": 0,
    "end_frame_id": 1697,
    "text": "The robot picks up the cup and places it on the tray."
  }
]
```

By default, the anchor video is `info.json.primary_video`. You can override it:

```bash
python scripts/generate_fluxvla_annotations.py \
  --processed-root /home/franka/Data/processed_data \
  --folder-pattern "RealRobot_DualFranka_20260627*" \
  --video-name rgb.mp4 \
  --output /home/franka/Data/processed_data/franka_dual_annotations.json
```

## Step 3: Export to LeRobot

Run this step in the LeRobot environment:

```bash
conda activate lerobot
cd /home/franka/franka/src/fluxvla_data_collection
```

Export dual Franka:

```bash
python scripts/convert_fluxvla_to_lerobot.py \
  --repo-id franka_dual/20260627_dual_franka_teleop \
  --annotation-json /home/franka/Data/processed_data/franka_dual_annotations.json \
  --spec config/processing_dual_franka.yaml \
  --output-root /home/franka/Data/lerobot \
  --mode video \
  --fps 30 \
  --video-codec h264
```

Export UR3:

```bash
python scripts/convert_fluxvla_to_lerobot.py \
  --repo-id ur3/20260627_ur3_teleop \
  --annotation-json /home/franka/Data/processed_data/ur3_annotations.json \
  --spec config/processing_ur3.yaml \
  --output-root /home/franka/Data/lerobot \
  --mode video \
  --fps 30 \
  --video-codec h264
```

Useful options:

- `--debug`: convert only the first two episodes.
- `--start-date 20260627`: include episodes whose paths contain dates at or after this date.
- `--end-date 20260628`: include episodes whose paths contain dates at or before this date.
- `--video-codec h264`: good compatibility with common players.
- `--video-codec libsvtav1`: LeRobot's default AV1 codec.

Recommended codec policy:

- Use `mp4v` or `h264` for processed MP4 files because they are easy to preview.
- Use `h264` for LeRobot if you want broad player compatibility.
- Use `libsvtav1` for LeRobot if you want to follow LeRobot's default codec and
  smaller files.

Note: processed MP4 files are not directly copied into the LeRobot dataset.
LeRobot reads frames and encodes dataset videos again during export.

## Processing Spec Reference

A processing spec has three main sections:

```yaml
robot:
  robot_type: franka_dual
  fps: 30

features:
  - name: state
    output: qpos.npy
    lerobot_key: observation.state
    dtype: float32
    required: true
    sources:
      - column: /observations/left/qpos
      - column: /observations/left/gripper_position
    names:
      - left_panda_joint1
      - left_gripper

cameras:
  - name: front
    column: /observations/images/cam_front
    output: rgb.mp4
    lerobot_key: observation.images.cam_front
    shape: [480, 640]
    required: true
```

### `robot`

- `robot_type`: stored in LeRobot metadata.
- `fps`: default FPS used for processed videos and LeRobot export.

`robot_type` does not determine feature dimensions. Dimensions come from
`features[*].names` and `cameras[*].shape`.

### `features`

Each feature describes one processed NPY array.

- `name`: internal feature name.
- `output`: NPY filename written into each processed episode folder.
- `lerobot_key`: optional LeRobot feature name. If omitted, the NPY is generated
  but not exported to LeRobot.
- `dtype`: numpy and LeRobot dtype, usually `float32`.
- `required`: if `true`, missing columns make the episode fail.
- `sources`: parquet columns concatenated in order.
- `names`: semantic names for each output vector dimension.

The output is always a 2D array:

```text
(num_frames, feature_dim)
```

`len(names)` must match `feature_dim`.

### `cameras`

Each camera describes one image column and one processed MP4.

- `name`: internal camera name.
- `column`: parquet column containing encoded image bytes.
- `output`: MP4 filename in the processed episode folder.
- `lerobot_key`: optional LeRobot image key.
- `shape`: `[height, width]` expected by LeRobot.
- `required`: if `true`, missing camera data makes the episode fail.

## Adding a New Robot

To support a new robot:

1. Create a new spec:

```bash
cp config/processing_dual_franka.yaml config/processing_my_robot.yaml
```

2. Update `robot.robot_type` and `robot.fps`.
3. Define one or more `features`.
4. Define camera columns and output video names.
5. Run a dry run:

```bash
python scripts/preprocess_fluxvla_parquet.py \
  --raw-root /home/franka/Data/raw_data \
  --subfolder 20260627 \
  --spec config/processing_my_robot.yaml \
  --output-root /home/franka/Data/processed_data \
  --output-prefix RealRobot_MyRobot \
  --dry-run
```

6. Process one date folder and inspect `info.json`, NPY shapes, and MP4 frame counts.

## Inspection Commands

Check processed array shapes:

```bash
python - <<'PY'
import os
import numpy as np

ep = "/home/franka/Data/processed_data/RealRobot_DualFranka_20260627_dual_franka_teleop_franka_dual/episode_0"
for name in ["qpos.npy", "eepose.npy", "gripper.npy", "action.npy"]:
    path = os.path.join(ep, name)
    if os.path.exists(path):
        print(name, np.load(path).shape)
PY
```

Check whether a video is readable:

```bash
python - <<'PY'
import cv2

path = "/home/franka/Data/processed_data/RealRobot_DualFranka_20260627_dual_franka_teleop_franka_dual/episode_0/rgb.mp4"
cap = cv2.VideoCapture(path)
print("opened:", cap.isOpened())
print("frames:", int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
ok, frame = cap.read()
print("first frame:", ok, None if frame is None else frame.shape)
cap.release()
PY
```

## Common Issues

### `ModuleNotFoundError: pyarrow`

The Python environment running preprocessing does not have `pyarrow`.

Use the conda environment that has it:

```bash
conda activate franka
python -c "import pyarrow; print(pyarrow.__version__)"
```

### `ModuleNotFoundError: lerobot`

Run LeRobot export in the `lerobot` environment:

```bash
conda activate lerobot
python -c "import lerobot"
```

### VLC cannot open videos under `/tmp`

If VLC is installed through snap, it may not be able to access the system `/tmp`
path. Copy the file to `/home/franka` or write LeRobot output directly under:

```text
/home/franka/Data/lerobot
```

### Optional feature is missing

If a feature has:

```yaml
required: false
```

missing columns only produce a warning. The feature is skipped for that episode.
For LeRobot export, optional features missing in any selected episode are
excluded from the exported dataset.

### `names length does not match output dimension`

The concatenated feature dimension does not match `len(names)`.

Check the source columns in the raw parquet and update the spec. For example,
dual Franka state uses:

```text
left qpos 7 + left gripper 1 + right qpos 7 + right gripper 1 = 16
```


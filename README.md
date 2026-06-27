# fluxvla_data_collection

Generic ROS topic recorder for robot data collection. The package records any
number of configured ROS topics, aligns the required streams with
`message_filters.ApproximateTimeSynchronizer`, attaches auxiliary streams with a
latest-before lookup, and writes one Parquet file per episode.

It is intended to be a small open-source replacement for robot-specific data
collection scripts: the recorder core is generic, while robot and device details
live in YAML config files and converter functions.

## Features

- Config-driven recording for arbitrary ROS topics.
- Approximate timestamp alignment for required streams.
- Latest-before lookup for asynchronous auxiliary streams.
- Streaming Parquet writer with one row per synchronized frame.
- `std_msgs/String` command topic for start, stop, and cancel.
- Converter registry for built-in and custom message-to-column conversion.
- Example configs for dual Franka and UR3-style single-arm collection.

## Dependencies

ROS dependencies are declared in `package.xml`:

- `rospy`
- `std_msgs`
- `sensor_msgs`
- `geometry_msgs`
- `message_filters`
- `cv_bridge`

Python runtime dependencies:

- `pyyaml`
- `numpy`
- `opencv-python` or system OpenCV Python bindings
- `pyarrow`

Optional converters require their own message packages to be installed and
sourced. For example, the `franka_state` converter requires `franka_msgs`.

## Build

Place this package in a catkin workspace and build it:

```bash
cd /path/to/catkin_ws
catkin_make --pkg fluxvla_data_collection
source devel/setup.bash
```

If your workspace uses `CATKIN_WHITELIST_PACKAGES`, include
`fluxvla_data_collection` in that list before building.

## Quick Start

Validate a config without subscribing to topics:

```bash
rosrun fluxvla_data_collection collect_data_generic_parquet.py \
  --config $(rospack find fluxvla_data_collection)/config/dual_franka_collection.yaml \
  --validate_config
```

Start the recorder:

```bash
rosrun fluxvla_data_collection collect_data_generic_parquet.py \
  --config $(rospack find fluxvla_data_collection)/config/dual_franka_collection.yaml
```

Add a per-run task description:

```bash
rosrun fluxvla_data_collection collect_data_generic_parquet.py \
  --config $(rospack find fluxvla_data_collection)/config/dual_franka_collection.yaml \
  --task-description "pick up the cup and place it on the tray"
```

The description is saved in `episode_<N>.meta.json` as `task_description` and
also embedded in the Parquet file metadata as `fluxvla.task_description`.

Recording is controlled by a `std_msgs/String` topic:

```bash
rostopic pub /data_collection/record_cmd std_msgs/String "data: 'start'"
rostopic pub /data_collection/record_cmd std_msgs/String "data: 'stop'"
rostopic pub /data_collection/record_cmd std_msgs/String "data: 'cancel'"
```

External joystick, keyboard, or UI nodes should translate their own interaction
logic into these three commands.

Command semantics:

- `start`: create a new episode and begin writing synchronized frames.
- `stop`: finish the current episode and save `.parquet` plus `.meta.json`.
- `cancel`: discard the current episode and delete incomplete output.

## YAML Structure

A collection config has five main sections:

```yaml
dataset:
  dataset_dir: /home/franka/Data/raw_data
  task_name: dual_franka_teleop
  task_description: ""
  station_idx: franka_dual
  frame_rate: 30
  max_timesteps: 50000
  flush_every_n: 100
  drop_warning_factor: 1.5
  no_frame_warning_timeout: 1.0
  no_frame_warning_interval: 5.0

sync:
  slop: 0.05
  queue_size: 60
  frame_queue_size: 300
  latest_buffer_size: 1000

control:
  command_topic: /data_collection/record_cmd
  command_type: std_msgs/String

topics:
  - name: cam_front_rgb
    topic: /cam_front/color/image_raw
    type: sensor_msgs/Image
    sync: required
    converter: image_png
    encoding: bgr8
    output: /observations/images/cam_front

computed_columns: []
```

### Dataset

- `dataset_dir`: root output directory.
- `task_name`: task name used in the output directory.
- `task_description`: optional default description saved with each episode;
  `--task-description` overrides it for the current recorder process.
- `station_idx`: robot or station id used in the output directory.
- `episode_idx`: optional fixed episode number; omit or set `-1` to auto-increment.
- `frame_rate`: main loop rate. This does not resample data; synchronized frames
  are still produced by incoming ROS timestamps.
- `max_timesteps`: maximum frames per episode.
- `flush_every_n`: rows buffered before writing a Parquet batch.
- `drop_warning_factor`: warn when adjacent saved frame timestamps exceed
  `drop_warning_factor / frame_rate` seconds.
- `no_frame_warning_timeout`: warn when recording is active but no synchronized
  frame has been written for this many wall-clock seconds.
- `no_frame_warning_interval`: minimum wall-clock seconds between repeated
  no-frame warnings.
- `camera_info_timeout`: seconds to wait for `camera_info` per image topic.

### Sync

- `slop`: maximum allowed timestamp span among `required` topics.
- `queue_size`: ROS message_filters queue size for each required topic.
- `frame_queue_size`: maximum synchronized frames waiting to be written.
- `latest_buffer_size`: maximum buffered messages per `latest_before` topic.

Reasonable 30 Hz defaults:

```yaml
sync:
  slop: 0.05
  queue_size: 60
  frame_queue_size: 300
  latest_buffer_size: 1000
```

Avoid putting image topics in `latest_before`; large image buffers can consume a
lot of memory. Images should usually be `required`.

### Control

The recorder only understands one control interface:

```yaml
control:
  command_topic: /data_collection/record_cmd
  command_type: std_msgs/String
```

Button handling, keyboard shortcuts, web UI events, or robot-specific state
machines should be implemented outside this package and converted into
`start`, `stop`, or `cancel` messages.

## Topic Specs

Each topic must declare:

- `name`: unique stream name.
- `topic`: ROS topic name.
- `type`: ROS message type, such as `sensor_msgs/Image`.
- `sync`: `required` or `latest_before`.
- `converter`: registered converter name or `module:function`.
- `output` or `outputs`: Parquet column name(s).

`sync: required` topics define when a frame exists. They are synchronized
together by ROS message filters. Use this for camera images and robot state.

`sync: latest_before` topics are buffered separately. After a required frame is
created, the recorder attaches the newest message with `stamp <= frame_max`.
Use this for commands, teleop sensors, gripper commands, and lower-rate signals.

Example robot observation:

```yaml
- name: left_state
  topic: /left_arm/franka_state_controller/franka_states
  type: franka_msgs/FrankaState
  sync: required
  converter: franka_state
  outputs:
    qpos: /observations/left/qpos
    qvel: /observations/left/qvel
    effort: /observations/left/effort
    eepose: /observations/left/eepose
```

Example command/action stream:

```yaml
- name: left_action_eepose
  topic: /left_arm/cartesian_impedance_controller/equilibrium_pose
  type: geometry_msgs/PoseStamped
  sync: latest_before
  converter: pose_stamped_7d
  output: /action/left/eepose
  default: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
```

Example teleoperation device stream:

```yaml
- name: right_joy
  topic: /controller/right/joy
  type: sensor_msgs/Joy
  sync: latest_before
  converter: joy_fixed
  output: /device/right/joy
  params:
    button_count: 5
    axis_count: 3
  default: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
```

Recommended column namespaces:

- `/observations/...`: robot state and sensor observations.
- `/action/...`: commands sent to the robot, such as target eepose.
- `/device/...`: raw teleoperation device signals, such as joy buttons/axes.
- `/timestamps/...`: recorder-generated timestamps.

## Built-in Converters

- `image_png`
- `pose_stamped_7d`
- `joint_state_named`
- `joy_fixed`
- `franka_state`
- `gripper_joint_width`
- `gripper_goal_width`
- `float32`
- `string`
- `raw_rosmsg_json`
- `concat`

Converter behavior:

- `image_png`: converts `sensor_msgs/Image` to PNG bytes.
- `pose_stamped_7d`: stores `[x, y, z, qx, qy, qz, qw]`.
- `joint_state_named`: extracts `position`, `velocity`, and `effort` in a
  configured joint order.
- `joy_fixed`: stores a fixed-length buttons-plus-axes vector.
- `franka_state`: extracts Franka `q`, `dq`, `tau_J`, and end-effector pose.
- `gripper_joint_width`: sums one or two gripper joint positions into width.
- `gripper_goal_width`: extracts `goal.width` from Franka gripper action goals.
- `float32`: stores `[msg.data]`.
- `string`: stores `msg.data`.
- `raw_rosmsg_json`: stores a JSON string for debugging or unsupported messages.
- `concat`: builds a computed column by concatenating existing row values.

Custom converters can be referenced from YAML:

```yaml
converter: my_package.my_module:my_converter
```

The converter signature is:

```python
def my_converter(msg_or_values, spec, context):
    return {"/parquet/column": value}
```

Or registered inside Python:

```python
from fluxvla_data_collection.registry import register_converter


@register_converter("my_pose_converter")
def my_pose_converter(msg, spec, context):
    return {spec["output"]: [msg.x, msg.y, msg.z]}
```

For custom message packages, install/source that ROS package before starting the
recorder, then use its normal type string in YAML, for example
`robotiq/StampedFloat32`.

## Output

Episodes are stored under:

```text
<dataset_dir>/<YYYYMMDD>/<task_name>_<station_idx>/episode_<N>.parquet
```

Each row includes:

- `/timestamps/frame_min`
- `/timestamps/frame_max`
- `/timestamps/sync_span`
- `/timestamps/<topic_name>`
- converter-generated observation/action columns

Parquet uses a wide-table layout:

- one synchronized frame is one row;
- each configured output is one column;
- images are stored as PNG bytes;
- vector values are stored as list columns;
- scalar values are stored as scalar columns.

The package also writes `episode_<N>.meta.json` and, when image streams are
configured, `camera_info.json`.

`episode_<N>.meta.json` includes run-level metadata such as `task_description`,
config path, topic list, sync settings, and frame count. The Parquet footer also
contains `fluxvla.task_description`, so the description remains attached when
only the `.parquet` file is copied.

## Post-Processing

The package also includes a schema-driven post-processing chain. Robot-specific
layout lives in `config/processing_*.yaml`; the Python code only follows the
declared feature and camera columns.

Convert raw Parquet episodes to processed `NPY + MP4 + info.json` folders:

```bash
rosrun fluxvla_data_collection preprocess_fluxvla_parquet.py \
  --raw-root /home/franka/Data/raw_data \
  --subfolder 20260627 \
  --spec $(rospack find fluxvla_data_collection)/config/processing_dual_franka.yaml \
  --output-root /home/franka/Data/processed_data \
  --output-prefix RealRobot_DualFranka \
  --video-codec mp4v
```

Generate LeRobot annotation JSON. If `--task` is omitted, the script uses the
`task_description` stored during recording:

```bash
rosrun fluxvla_data_collection generate_fluxvla_annotations.py \
  --processed-root /home/franka/Data/processed_data \
  --folder-pattern "RealRobot_DualFranka_20260627*" \
  --output /home/franka/Data/processed_data/franka_dual_annotations.json
```

Export to LeRobot:

```bash
rosrun fluxvla_data_collection convert_fluxvla_to_lerobot.py \
  --repo-id franka_dual/20260627_dual_franka_teleop \
  --annotation-json /home/franka/Data/processed_data/franka_dual_annotations.json \
  --spec $(rospack find fluxvla_data_collection)/config/processing_dual_franka.yaml \
  --output-root /home/franka/Data/lerobot \
  --mode video \
  --fps 30 \
  --video-codec h264
```

Processing specs use generic `features` and `cameras` sections:

- `features[*].sources`: Parquet columns to concatenate in order.
- `features[*].names`: semantic names for the resulting vector dimensions.
- `features[*].output`: processed NPY file name.
- `features[*].lerobot_key`: optional LeRobot feature key.
- `cameras[*].column`: Parquet image column containing encoded image bytes.
- `cameras[*].output`: processed MP4 file name.
- `cameras[*].lerobot_key`: optional LeRobot image feature key.

Add a new robot platform by adding a new `processing_<robot>.yaml`; no Python
code changes are required if the recorded Parquet columns already exist.

## Example Schemas

### Dual Franka

The dual Franka example records:

- RGB images:
  - `/observations/images/cam_front`
  - `/observations/images/cam_wrist_left`
  - `/observations/images/cam_wrist_right`
- left/right robot observations:
  - `/observations/<side>/qpos`
  - `/observations/<side>/qvel`
  - `/observations/<side>/effort`
  - `/observations/<side>/eepose`
  - `/observations/<side>/gripper_position`
- left/right commanded eepose:
  - `/action/left/eepose`
  - `/action/right/eepose`
- teleoperation devices:
  - `/device/left/joy`
  - `/device/right/joy`

### UR3

The UR3 example records:

- RGB images:
  - `/observations/images/cam_high`
  - `/observations/images/cam_wrist`
- robot observations:
  - `/observations/qpos`
  - `/observations/qvel`
  - `/observations/effort`
  - `/observations/eepose`
  - `/observations/gripper_position`
- command/action:
  - `/action/eepose`
- teleoperation device:
  - `/device/joy`

## Troubleshooting

- `unknown converter`: import `fluxvla_data_collection.converters` before
  validation, or check the converter name in YAML.
- `failed to import <package>.msg`: source the workspace that provides the
  message package, or install the missing ROS package.
- no frames written: check that every `required` topic publishes messages with
  valid `header.stamp`, and increase `sync.slop` if streams are timestamped
  slightly apart.
- `No synchronized frames` warnings: at least one `required` topic is probably
  stopped, missing, or no longer timestamp-aligned with the others. This catches
  cases where synchronization stops producing frames entirely.
- possible frame drop warnings: inspect the reported timestamp gap. Warnings are
  based on `/timestamps/frame_max`, not writer wall-clock throughput.
- high memory usage: reduce `frame_queue_size` and `latest_buffer_size`, and
  avoid using images as `latest_before` topics.
- `ModuleNotFoundError: pyarrow`: install `pyarrow` in the Python environment
  used by ROS.
